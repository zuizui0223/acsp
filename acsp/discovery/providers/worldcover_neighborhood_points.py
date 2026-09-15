"""Sparse ESA WorldCover neighbourhood fractions at frozen candidate points.

This provider avoids materialising a regional native-10 m crop. Candidate points
must already be frozen. Each official WorldCover 2021 v200 COG is opened once and
small local windows are read around the points assigned to that tile. The module
uses no occurrence outcomes, access variables, fitted thresholds, or ranking.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
from typing import Any, Callable

import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from rasterio.windows import Window

from .worldcover import (
    WORLD_COVER_2021_CLASS_NAMES,
    worldcover_2021_map_url,
    worldcover_tile_id,
)


@dataclass(frozen=True)
class WorldCoverNeighbourhoodPointAudit:
    provider_id: str
    release_id: str
    neighbourhood_radius_m: float
    candidate_rows_input: int
    complete_neighbourhood_rows: int
    tile_boundary_rows_removed: int
    invalid_or_nodata_rows_removed: int
    source_tile_ids: tuple[str, ...]
    source_urls: tuple[str, ...]
    feature_digest_sha256: str
    field_outcomes_used: bool = False
    human_access_used: bool = False
    fitted_thresholds: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


FEATURE_COLUMNS = (
    "wc_tree_frac_250m",
    "wc_grass_frac_250m",
    "wc_bare_frac_250m",
    "wc_water_frac_250m",
    "wc_wetland_frac_250m",
    "wc_edge_mix_250m",
)


def _pixel_size_m(src: Any, reference_latitude: float) -> tuple[float, float]:
    x_size = abs(float(src.transform.a))
    y_size = abs(float(src.transform.e))
    if src.crs is None:
        raise ValueError("WorldCover source has no CRS")
    if bool(getattr(src.crs, "is_geographic", False)):
        return (
            x_size * 111_320.0 * max(0.05, math.cos(math.radians(float(reference_latitude)))),
            y_size * 111_320.0,
        )
    factor = 1.0
    try:
        units = src.crs.linear_units_factor
        factor = float(units[1] if isinstance(units, tuple) else units or 1.0)
    except Exception:
        factor = 1.0
    return x_size * factor, y_size * factor


def _feature_digest(frame: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    columns = ["candidate_cell_id", "worldcover_neighbourhood_tile_id", *FEATURE_COLUMNS]
    for row in frame[columns].sort_values("candidate_cell_id", kind="mergesort").itertuples(index=False, name=None):
        values: list[str] = []
        for value in row:
            if isinstance(value, (float, np.floating)):
                values.append(f"{float(value):.8f}")
            else:
                values.append(str(value))
        digest.update(("\t".join(values) + "\n").encode("utf-8"))
    return digest.hexdigest()


def attach_worldcover_neighbourhood_fractions(
    candidate_frame: pd.DataFrame,
    *,
    radius_m: float = 250.0,
    dataset_opener: Callable[[str], Any] | None = None,
) -> tuple[pd.DataFrame, WorldCoverNeighbourhoodPointAudit]:
    """Attach frozen 250 m WorldCover class fractions to candidate points.

    Windows that would cross an official 3-degree source-tile edge are removed
    rather than silently clipping the neighbourhood. All downstream methods must
    use the same returned source-complete frame.
    """
    if candidate_frame is None or candidate_frame.empty:
        raise ValueError("candidate_frame cannot be empty")
    if float(radius_m) <= 0:
        raise ValueError("radius_m must be positive")
    required = {"candidate_cell_id", "latitude", "longitude"}
    missing = sorted(required.difference(candidate_frame.columns))
    if missing:
        raise ValueError(f"candidate frame missing required columns: {missing}")

    work = candidate_frame.copy().reset_index(drop=True)
    if work["candidate_cell_id"].astype(str).duplicated().any():
        raise ValueError("candidate_cell_id must be unique")
    lat = pd.to_numeric(work["latitude"], errors="coerce").to_numpy(float)
    lon = pd.to_numeric(work["longitude"], errors="coerce").to_numpy(float)
    if not np.isfinite(lat).all() or not np.isfinite(lon).all():
        raise ValueError("candidate coordinates must be complete and finite")

    tile_ids = np.asarray([worldcover_tile_id(a, b) for a, b in zip(lat, lon)], dtype=object)
    work["worldcover_neighbourhood_tile_id"] = tile_ids
    source_tile_ids = tuple(sorted(set(str(value) for value in tile_ids)))
    source_urls = tuple(worldcover_2021_map_url(tile_id) for tile_id in source_tile_ids)
    url_by_tile = dict(zip(source_tile_ids, source_urls))
    opener = dataset_opener or rasterio.open

    features = np.full((len(work), len(FEATURE_COLUMNS)), np.nan, dtype=float)
    tile_boundary_removed = 0
    invalid_removed = 0
    valid_codes = np.asarray(sorted(int(code) for code in WORLD_COVER_2021_CLASS_NAMES), dtype=np.int16)

    for tile_id in source_tile_ids:
        positions = np.flatnonzero(tile_ids == tile_id)
        with opener(url_by_tile[tile_id]) as src:
            if src.crs is None:
                raise ValueError(f"WorldCover source has no CRS: {tile_id}")
            transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
            xs, ys = transformer.transform(lon[positions], lat[positions])
            rows, cols = rasterio.transform.rowcol(src.transform, xs, ys)

            for local_i, target in enumerate(positions):
                row = int(rows[local_i])
                col = int(cols[local_i])
                pixel_x_m, pixel_y_m = _pixel_size_m(src, float(lat[target]))
                pixel_m = max(1e-6, max(pixel_x_m, pixel_y_m))
                half = max(1, int(math.ceil(float(radius_m) / pixel_m)))
                r0, r1 = row - half, row + half + 1
                c0, c1 = col - half, col + half + 1
                if r0 < 0 or c0 < 0 or r1 > int(src.height) or c1 > int(src.width):
                    tile_boundary_removed += 1
                    continue
                array = np.ma.asarray(
                    src.read(1, window=Window(c0, r0, c1 - c0, r1 - r0), masked=True)
                )
                values = np.asarray(array.compressed(), dtype=np.int16)
                values = values[np.isin(values, valid_codes)]
                if values.size == 0:
                    invalid_removed += 1
                    continue

                all_fractions = np.asarray([(values == code).mean() for code in valid_codes], dtype=float)
                lookup = {int(code): float(frac) for code, frac in zip(valid_codes, all_fractions)}
                edge_mix = float(1.0 - np.square(all_fractions).sum())
                features[int(target), :] = [
                    lookup.get(10, 0.0),
                    lookup.get(30, 0.0),
                    lookup.get(60, 0.0),
                    lookup.get(80, 0.0),
                    lookup.get(90, 0.0),
                    max(0.0, min(1.0, edge_mix)),
                ]

    complete = np.isfinite(features).all(axis=1)
    retained = work.loc[complete].copy().reset_index(drop=True)
    retained_features = features[complete]
    for index, column in enumerate(FEATURE_COLUMNS):
        retained[column] = retained_features[:, index]
    if retained.empty:
        raise ValueError("WORLDCOVER_NEIGHBOURHOOD_PROVIDER_FAILURE:no complete candidate neighbourhoods")

    audit = WorldCoverNeighbourhoodPointAudit(
        provider_id="ESA_WORLDCOVER",
        release_id="2021_v200",
        neighbourhood_radius_m=float(radius_m),
        candidate_rows_input=int(len(work)),
        complete_neighbourhood_rows=int(len(retained)),
        tile_boundary_rows_removed=int(tile_boundary_removed),
        invalid_or_nodata_rows_removed=int(invalid_removed),
        source_tile_ids=source_tile_ids,
        source_urls=source_urls,
        feature_digest_sha256=_feature_digest(retained),
    )
    return retained, audit
