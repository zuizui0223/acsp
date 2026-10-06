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


def _integral_window_counts(
    binary: np.ndarray,
    r0: np.ndarray,
    c0: np.ndarray,
    r1: np.ndarray,
    c1: np.ndarray,
) -> np.ndarray:
    """Return rectangular sums using a uint32 summed-area table."""
    values = np.asarray(binary, dtype=np.uint32)
    prefix = np.zeros((values.shape[0] + 1, values.shape[1] + 1), dtype=np.uint32)
    prefix[1:, 1:] = values.cumsum(axis=0, dtype=np.uint32).cumsum(axis=1, dtype=np.uint32)
    return (
        prefix[r1, c1].astype(np.int64)
        - prefix[r0, c1].astype(np.int64)
        - prefix[r1, c0].astype(np.int64)
        + prefix[r0, c0].astype(np.int64)
    )


def attach_worldcover_neighbourhood_fractions_blocked(
    candidate_frame: pd.DataFrame,
    *,
    radius_m: float = 250.0,
    block_pixels: int = 2048,
    dataset_opener: Callable[[str], Any] | None = None,
) -> tuple[pd.DataFrame, WorldCoverNeighbourhoodPointAudit]:
    """Attach the frozen neighbourhood fractions with block-reused raster reads.

    This is an exact computational acceleration of
    :func:`attach_worldcover_neighbourhood_fractions`. Candidate windows retain
    the same per-point pixel radius, valid-class denominator, official 3-degree
    source-tile boundary rule, feature formulas and output digest. The only
    difference is that nearby candidate windows share one raster read and use
    summed-area tables for class counts.
    """
    if candidate_frame is None or candidate_frame.empty:
        raise ValueError("candidate_frame cannot be empty")
    if float(radius_m) <= 0:
        raise ValueError("radius_m must be positive")
    if int(block_pixels) < 1:
        raise ValueError("block_pixels must be positive")
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
    output_code_to_col = {10: 0, 30: 1, 60: 2, 80: 3, 90: 4}

    for tile_id in source_tile_ids:
        positions = np.flatnonzero(tile_ids == tile_id)
        with opener(url_by_tile[tile_id]) as src:
            if src.crs is None:
                raise ValueError(f"WorldCover source has no CRS: {tile_id}")
            transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
            xs, ys = transformer.transform(lon[positions], lat[positions])
            rows, cols = rasterio.transform.rowcol(src.transform, xs, ys)
            rows = np.asarray(rows, dtype=np.int64)
            cols = np.asarray(cols, dtype=np.int64)

            half = np.asarray(
                [
                    max(
                        1,
                        int(
                            math.ceil(
                                float(radius_m)
                                / max(1e-6, max(_pixel_size_m(src, float(lat[target]))))
                            )
                        ),
                    )
                    for target in positions
                ],
                dtype=np.int64,
            )
            r0 = rows - half
            r1 = rows + half + 1
            c0 = cols - half
            c1 = cols + half + 1
            boundary = (r0 < 0) | (c0 < 0) | (r1 > int(src.height)) | (c1 > int(src.width))
            tile_boundary_removed += int(boundary.sum())
            valid_local = np.flatnonzero(~boundary)
            if valid_local.size == 0:
                continue

            block_keys = np.column_stack(
                (
                    rows[valid_local] // int(block_pixels),
                    cols[valid_local] // int(block_pixels),
                )
            )
            unique_keys = sorted(set(map(tuple, block_keys.tolist())))
            for key in unique_keys:
                choose = valid_local[
                    (block_keys[:, 0] == key[0]) & (block_keys[:, 1] == key[1])
                ]
                crop_r0 = int(r0[choose].min())
                crop_r1 = int(r1[choose].max())
                crop_c0 = int(c0[choose].min())
                crop_c1 = int(c1[choose].max())
                array = np.ma.asarray(
                    src.read(
                        1,
                        window=Window(
                            crop_c0,
                            crop_r0,
                            crop_c1 - crop_c0,
                            crop_r1 - crop_r0,
                        ),
                        masked=True,
                    )
                )
                data = np.asarray(array.data, dtype=np.int16)
                mask = np.ma.getmaskarray(array)
                valid_pixels = (~mask) & np.isin(data, valid_codes)

                local_r0 = (r0[choose] - crop_r0).astype(np.int64)
                local_r1 = (r1[choose] - crop_r0).astype(np.int64)
                local_c0 = (c0[choose] - crop_c0).astype(np.int64)
                local_c1 = (c1[choose] - crop_c0).astype(np.int64)
                denominator = _integral_window_counts(
                    valid_pixels, local_r0, local_c0, local_r1, local_c1
                )
                usable = denominator > 0
                invalid_removed += int((~usable).sum())
                if not np.any(usable):
                    continue

                block_features = np.zeros((len(choose), len(FEATURE_COLUMNS)), dtype=float)
                sum_sq = np.zeros(len(choose), dtype=float)
                for code in valid_codes.tolist():
                    counts = _integral_window_counts(
                        valid_pixels & (data == int(code)),
                        local_r0,
                        local_c0,
                        local_r1,
                        local_c1,
                    )
                    frac = np.zeros(len(choose), dtype=float)
                    frac[usable] = counts[usable].astype(float) / denominator[usable].astype(float)
                    sum_sq[usable] += np.square(frac[usable])
                    if int(code) in output_code_to_col:
                        block_features[:, output_code_to_col[int(code)]] = frac
                block_features[:, 5] = np.clip(1.0 - sum_sq, 0.0, 1.0)
                targets = positions[choose[usable]]
                features[targets, :] = block_features[usable, :]

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
