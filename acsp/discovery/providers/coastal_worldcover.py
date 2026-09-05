"""Portable coastal/island primitives derived from ESA WorldCover.

This provider turns one frozen WorldCover crop into the raw inputs required by
``COASTAL_ISLAND_STRUCTURE``. It uses no field outcomes, roads, access, or fitted
thresholds. The historical population medoids must identify one unambiguous land
component before structural ranking is allowed.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from scipy.ndimage import distance_transform_edt, label, uniform_filter

from .worldcover import WORLD_COVER_2021_CLASS_NAMES


@dataclass(frozen=True)
class CoastalWorldCoverAudit:
    candidate_rows_input: int
    candidate_land_rows_retained: int
    historical_anchor_count: int
    historical_anchor_component_count: int
    target_component_id: str
    land_component_count_in_crop: int
    pixel_size_x_m: float
    pixel_size_y_m: float
    neighbourhood_half_width_m: float
    field_outcomes_used: bool = False
    human_access_used: bool = False
    fitted_thresholds: bool = False


def _pixel_size_m(src: rasterio.io.DatasetReader, reference_latitude: float) -> tuple[float, float]:
    x_size = abs(float(src.transform.a))
    y_size = abs(float(src.transform.e))
    if src.crs and src.crs.is_geographic:
        return (
            x_size * 111_320.0 * max(0.05, math.cos(math.radians(float(reference_latitude)))),
            y_size * 111_320.0,
        )
    factor = 1.0
    try:
        units = src.crs.linear_units_factor if src.crs else None
        factor = float(units[1] if isinstance(units, tuple) else units or 1.0)
    except Exception:
        factor = 1.0
    return x_size * factor, y_size * factor


def _indices_for_points(
    src: rasterio.io.DatasetReader,
    frame: pd.DataFrame,
    *,
    latitude_col: str = "latitude",
    longitude_col: str = "longitude",
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    required = {latitude_col, longitude_col}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"point table missing coordinates: {missing}")
    lat = pd.to_numeric(frame[latitude_col], errors="coerce").to_numpy(float)
    lon = pd.to_numeric(frame[longitude_col], errors="coerce").to_numpy(float)
    if not np.isfinite(lat).all() or not np.isfinite(lon).all():
        raise ValueError("point coordinates must be complete and finite")
    if src.crs is None:
        raise ValueError("WorldCover crop has no CRS")
    transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
    x, y = transformer.transform(lon, lat)
    rows, cols = rasterio.transform.rowcol(src.transform, x, y)
    rows = np.asarray(rows, dtype=int)
    cols = np.asarray(cols, dtype=int)
    inside = (rows >= 0) & (rows < src.height) & (cols >= 0) & (cols < src.width)
    return rows, cols, inside


def _sample_array(array: np.ndarray, rows: np.ndarray, cols: np.ndarray, inside: np.ndarray, *, fill=np.nan) -> np.ndarray:
    out = np.full(len(rows), fill, dtype=float if isinstance(fill, float) or np.isscalar(fill) else object)
    valid = np.flatnonzero(inside)
    if len(valid):
        out[valid] = array[rows[valid], cols[valid]]
    return out


def attach_worldcover_coastal_features(
    candidate_frame: pd.DataFrame,
    historical_anchors: pd.DataFrame,
    worldcover_crop: Path,
    *,
    neighbourhood_half_width_m: float = 250.0,
) -> tuple[pd.DataFrame, CoastalWorldCoverAudit]:
    """Attach coast distance, shore cover and one unambiguous land component.

    Candidate water cells are removed before ranking. Every historical anchor
    must resolve to the same positive WorldCover land component; otherwise the
    caller must abstain rather than choose a favorable component after outcomes.
    """
    if candidate_frame is None or candidate_frame.empty:
        raise ValueError("candidate_frame cannot be empty")
    if historical_anchors is None or historical_anchors.empty:
        raise ValueError("NO_STRICT_HISTORICAL_ANCHOR")
    if float(neighbourhood_half_width_m) <= 0:
        raise ValueError("neighbourhood_half_width_m must be positive")

    valid_codes = np.array(sorted(WORLD_COVER_2021_CLASS_NAMES), dtype=np.int16)
    path = Path(worldcover_crop)
    with rasterio.open(path) as src:
        cover = src.read(1)
        reference_lat = float(pd.to_numeric(candidate_frame["latitude"], errors="coerce").mean())
        pixel_x_m, pixel_y_m = _pixel_size_m(src, reference_lat)
        pixel_m = max(1e-6, max(pixel_x_m, pixel_y_m))
        valid_cover = np.isin(cover, valid_codes)
        water = cover == 80
        land = valid_cover & ~water
        if not bool(water.any()):
            raise ValueError("WORLDCOVER_PROVIDER_FAILURE:no permanent-water pixels inside declared crop")
        if not bool(land.any()):
            raise ValueError("WORLDCOVER_PROVIDER_FAILURE:no valid land pixels inside declared crop")

        components, component_count = label(land, structure=np.ones((3, 3), dtype=np.uint8))
        anchor_rows, anchor_cols, anchor_inside = _indices_for_points(src, historical_anchors)
        anchor_labels = _sample_array(components, anchor_rows, anchor_cols, anchor_inside, fill=0.0).astype(int)
        if np.any(anchor_labels <= 0):
            raise ValueError("ANCHOR_ON_NO_VALID_WORLDCOVER_LAND")
        anchor_components = sorted(set(int(value) for value in anchor_labels))
        if len(anchor_components) != 1:
            raise ValueError(
                "MULTIPLE_HISTORICAL_LAND_COMPONENTS:" + ",".join(map(str, anchor_components))
            )
        target_label = int(anchor_components[0])
        target_component_id = f"WORLDCOVER_LAND_COMPONENT_{target_label}"

        cand_rows, cand_cols, cand_inside = _indices_for_points(src, candidate_frame)
        cand_labels = _sample_array(components, cand_rows, cand_cols, cand_inside, fill=0.0).astype(int)
        keep = cand_inside & (cand_labels > 0)
        retained = candidate_frame.loc[keep].copy().reset_index(drop=True)
        retained_labels = cand_labels[keep]
        retained["ecological_component_id"] = [
            f"WORLDCOVER_LAND_COMPONENT_{int(value)}" for value in retained_labels
        ]

        # Distance to permanent-water pixels. Invalid/no-data pixels are not
        # treated as coastline; only class 80 is the zero set.
        distance_to_water = distance_transform_edt(~water, sampling=(pixel_y_m, pixel_x_m))
        retained_rows = cand_rows[keep]
        retained_cols = cand_cols[keep]
        retained["coast_distance_m"] = distance_to_water[retained_rows, retained_cols].astype(float)

        half_pixels = max(1, int(math.ceil(float(neighbourhood_half_width_m) / pixel_m)))
        size = 2 * half_pixels + 1
        valid_mean = uniform_filter(valid_cover.astype(np.float32), size=size, mode="constant", cval=0.0)
        denominator = valid_mean[retained_rows, retained_cols]
        for code, column in ((30, "wc_grass_frac_250m"), (60, "wc_bare_frac_250m")):
            class_mean = uniform_filter((cover == code).astype(np.float32), size=size, mode="constant", cval=0.0)
            numerator = class_mean[retained_rows, retained_cols]
            values = np.divide(
                numerator,
                denominator,
                out=np.zeros_like(numerator, dtype=float),
                where=denominator > 1e-12,
            )
            retained[column] = np.clip(values, 0.0, 1.0)

    if retained.empty:
        raise ValueError("WORLDCOVER_PROVIDER_FAILURE:no land candidate cells retained")
    audit = CoastalWorldCoverAudit(
        candidate_rows_input=int(len(candidate_frame)),
        candidate_land_rows_retained=int(len(retained)),
        historical_anchor_count=int(len(historical_anchors)),
        historical_anchor_component_count=1,
        target_component_id=target_component_id,
        land_component_count_in_crop=int(component_count),
        pixel_size_x_m=float(pixel_x_m),
        pixel_size_y_m=float(pixel_y_m),
        neighbourhood_half_width_m=float(neighbourhood_half_width_m),
    )
    return retained, audit
