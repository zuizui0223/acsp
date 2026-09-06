"""Lightweight ESA WorldCover point sampling for broad discovery frames.

This provider samples the official WorldCover 2021 v200 COG only at already
frozen candidate coordinates. It is intended for regional broad-frame ceiling
work where creating a native-10 m raster crop would be unnecessarily large.
It does not construct connected components, rank candidates, use outcomes, or
read human-access variables.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from typing import Any, Callable

import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer

from .worldcover import (
    WORLD_COVER_2021_CLASS_NAMES,
    worldcover_2021_map_url,
    worldcover_tile_id,
)


@dataclass(frozen=True)
class WorldCoverPointSampleAudit:
    provider_id: str
    release_id: str
    candidate_rows_input: int
    sampled_rows: int
    land_rows_retained: int
    water_rows_removed: int
    invalid_or_nodata_rows_removed: int
    source_tile_ids: tuple[str, ...]
    source_urls: tuple[str, ...]
    sample_classification_sha256: str
    field_outcomes_used: bool = False
    human_access_used: bool = False
    component_segmentation_used: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _classification_digest(frame: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    columns = ["candidate_cell_id", "worldcover_tile_id", "worldcover_class"]
    for row in frame[columns].sort_values("candidate_cell_id", kind="mergesort").itertuples(index=False, name=None):
        digest.update(("\t".join(map(str, row)) + "\n").encode("utf-8"))
    return digest.hexdigest()


def retain_worldcover_land_points(
    candidate_frame: pd.DataFrame,
    *,
    dataset_opener: Callable[[str], Any] | None = None,
) -> tuple[pd.DataFrame, WorldCoverPointSampleAudit]:
    """Retain candidate points whose sampled WorldCover class is valid non-water.

    Candidate coordinates and IDs must already be frozen. Points are grouped by
    official 3-degree tile and sampled in stable input order. The returned digest
    hashes the sampled candidate classification table; it is not presented as a
    byte-level checksum of the remote ESA source asset.
    """
    if candidate_frame is None or candidate_frame.empty:
        raise ValueError("candidate_frame cannot be empty")
    required = {"candidate_cell_id", "latitude", "longitude"}
    missing = sorted(required.difference(candidate_frame.columns))
    if missing:
        raise ValueError(f"candidate frame missing required columns: {missing}")

    work = candidate_frame.copy().reset_index(drop=True)
    if work["candidate_cell_id"].astype(str).duplicated().any():
        raise ValueError("candidate_cell_id must be unique")
    latitude = pd.to_numeric(work["latitude"], errors="coerce").to_numpy(float)
    longitude = pd.to_numeric(work["longitude"], errors="coerce").to_numpy(float)
    if not np.isfinite(latitude).all() or not np.isfinite(longitude).all():
        raise ValueError("candidate coordinates must be complete and finite")

    tile_ids = np.asarray(
        [worldcover_tile_id(lat, lon) for lat, lon in zip(latitude, longitude)],
        dtype=object,
    )
    work["worldcover_tile_id"] = tile_ids
    sampled = np.full(len(work), -1, dtype=np.int16)
    opener = dataset_opener or rasterio.open

    source_tile_ids = tuple(sorted(set(str(value) for value in tile_ids)))
    source_urls = tuple(worldcover_2021_map_url(tile_id) for tile_id in source_tile_ids)
    url_by_tile = dict(zip(source_tile_ids, source_urls))

    for tile_id in source_tile_ids:
        positions = np.flatnonzero(tile_ids == tile_id)
        url = url_by_tile[tile_id]
        with opener(url) as src:
            if src.crs is None:
                raise ValueError(f"WorldCover source has no CRS: {tile_id}")
            lon = longitude[positions]
            lat = latitude[positions]
            if str(src.crs).upper() not in {"EPSG:4326", "OGC:CRS84"}:
                transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
                x, y = transformer.transform(lon, lat)
            else:
                x, y = lon, lat
            values = list(src.sample(list(zip(x, y)), indexes=1, masked=True))
            if len(values) != len(positions):
                raise RuntimeError("WorldCover point sampler returned an unexpected sample count")
            for target, value in zip(positions, values):
                array = np.ma.asarray(value)
                if array.size != 1 or bool(np.ma.getmaskarray(array).reshape(-1)[0]):
                    continue
                try:
                    sampled[int(target)] = int(array.reshape(-1)[0])
                except (TypeError, ValueError, OverflowError):
                    continue

    work["worldcover_class"] = sampled.astype(int)
    valid_codes = set(int(code) for code in WORLD_COVER_2021_CLASS_NAMES)
    valid = work["worldcover_class"].isin(valid_codes)
    water = valid & work["worldcover_class"].eq(80)
    land = valid & ~water
    retained = work.loc[land].copy().reset_index(drop=True)

    audit = WorldCoverPointSampleAudit(
        provider_id="ESA_WORLDCOVER",
        release_id="2021_v200",
        candidate_rows_input=int(len(work)),
        sampled_rows=int(valid.sum()),
        land_rows_retained=int(land.sum()),
        water_rows_removed=int(water.sum()),
        invalid_or_nodata_rows_removed=int((~valid).sum()),
        source_tile_ids=source_tile_ids,
        source_urls=source_urls,
        sample_classification_sha256=_classification_digest(work),
    )
    return retained, audit
