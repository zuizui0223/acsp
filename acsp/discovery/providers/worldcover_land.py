"""Lightweight land-mask sampling from a frozen WorldCover crop."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer

from .worldcover import WORLD_COVER_2021_CLASS_NAMES


@dataclass(frozen=True)
class WorldCoverLandMaskAudit:
    candidate_rows_input: int
    land_rows_retained: int
    water_rows_removed: int
    invalid_or_outside_rows_removed: int
    field_outcomes_used: bool = False
    human_access_used: bool = False


def retain_worldcover_land_candidates(
    candidate_frame: pd.DataFrame,
    worldcover_crop: Path,
) -> tuple[pd.DataFrame, WorldCoverLandMaskAudit]:
    """Retain valid non-water WorldCover cells without structural scoring."""
    if candidate_frame is None or candidate_frame.empty:
        raise ValueError("candidate_frame cannot be empty")
    if not {"latitude", "longitude"}.issubset(candidate_frame.columns):
        raise ValueError("candidate_frame requires latitude/longitude")
    lat = pd.to_numeric(candidate_frame["latitude"], errors="coerce").to_numpy(float)
    lon = pd.to_numeric(candidate_frame["longitude"], errors="coerce").to_numpy(float)
    if not np.isfinite(lat).all() or not np.isfinite(lon).all():
        raise ValueError("candidate coordinates must be complete and finite")

    with rasterio.open(Path(worldcover_crop)) as src:
        if src.crs is None:
            raise ValueError("WorldCover crop has no CRS")
        transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        x, y = transformer.transform(lon, lat)
        rows, cols = rasterio.transform.rowcol(src.transform, x, y)
        rows = np.asarray(rows, dtype=int)
        cols = np.asarray(cols, dtype=int)
        inside = (rows >= 0) & (rows < src.height) & (cols >= 0) & (cols < src.width)
        cover = src.read(1)
        sampled = np.zeros(len(candidate_frame), dtype=np.int16)
        valid_indices = np.flatnonzero(inside)
        if len(valid_indices):
            sampled[valid_indices] = cover[rows[valid_indices], cols[valid_indices]].astype(np.int16)

    valid_codes = np.array(sorted(WORLD_COVER_2021_CLASS_NAMES), dtype=np.int16)
    valid = inside & np.isin(sampled, valid_codes)
    water = valid & (sampled == 80)
    land = valid & ~water
    retained = candidate_frame.loc[land].copy().reset_index(drop=True)
    if retained.empty:
        raise ValueError("WORLDCOVER_PROVIDER_FAILURE:no land candidate cells retained")
    return retained, WorldCoverLandMaskAudit(
        candidate_rows_input=int(len(candidate_frame)),
        land_rows_retained=int(land.sum()),
        water_rows_removed=int(water.sum()),
        invalid_or_outside_rows_removed=int((~valid).sum()),
    )
