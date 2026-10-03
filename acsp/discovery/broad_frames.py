"""Broad-frame primitives for experimental N4 discovery.

These utilities encode a lesson from repeated local-discovery failures: ranking
cannot recover observations that are absent from the candidate universe.  A
source-backed broad frame can therefore be partitioned into the declared LOCAL
continuation zone and non-local DETACHED lanes before any ecological ranking.

No field outcomes, roads, access, route cost, or fitted habitat threshold are
used here.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely.geometry import Point, box
from shapely.ops import transform as shapely_transform

from .frames import metric_crs_for_lonlat


@dataclass(frozen=True)
class RectangularFrameAudit:
    candidate_count: int
    grid_spacing_m: float
    bounds_wgs84: tuple[float, float, float, float]
    metric_crs: str
    nominal_frame_area_km2: float
    field_outcomes_used: bool = False
    human_access_used: bool = False


@dataclass(frozen=True)
class DetachedPartitionAudit:
    candidate_count: int
    local_boundary_km: float
    local_count: int
    detached_count: int
    detached_same_component_count: int
    detached_other_component_count: int
    target_component_id: str
    field_outcomes_used: bool = False
    human_access_used: bool = False
    fitted_thresholds: bool = False


def build_rectangular_candidate_frame(
    bounds_wgs84: tuple[float, float, float, float],
    *,
    grid_spacing_m: float = 250.0,
    candidate_id_prefix: str = "broad",
) -> tuple[pd.DataFrame, RectangularFrameAudit]:
    """Build one deterministic regular grid inside declared WGS84 bounds."""
    west, south, east, north = map(float, bounds_wgs84)
    if not (-180.0 <= west < east <= 180.0 and -90.0 <= south < north <= 90.0):
        raise ValueError("bounds must satisfy valid west < east and south < north")
    spacing = float(grid_spacing_m)
    if spacing <= 0:
        raise ValueError("grid_spacing_m must be positive")

    center_lon = (west + east) / 2.0
    center_lat = (south + north) / 2.0
    metric = metric_crs_for_lonlat(center_lon, center_lat)
    to_metric = Transformer.from_crs("EPSG:4326", metric, always_xy=True)
    to_wgs = Transformer.from_crs(metric, "EPSG:4326", always_xy=True)
    polygon = shapely_transform(to_metric.transform, box(west, south, east, north))

    minx, miny, maxx, maxy = polygon.bounds
    x0 = math.floor(minx / spacing) * spacing
    y0 = math.floor(miny / spacing) * spacing
    x1 = math.ceil(maxx / spacing) * spacing
    y1 = math.ceil(maxy / spacing) * spacing
    first_col = int(round(x0 / spacing))
    first_row = int(round(y0 / spacing))
    ncol = int(round((x1 - x0) / spacing)) + 1
    nrow = int(round((y1 - y0) / spacing)) + 1

    rows: list[dict[str, object]] = []
    for local_row in range(nrow):
        y = y0 + local_row * spacing
        global_row = first_row + local_row
        for local_col in range(ncol):
            x = x0 + local_col * spacing
            if not polygon.covers(Point(float(x), float(y))):
                continue
            global_col = first_col + local_col
            lon, lat = to_wgs.transform(x, y)
            rows.append(
                {
                    "candidate_cell_id": f"{candidate_id_prefix}_r{global_row}_c{global_col}",
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "grid_row": int(global_row),
                    "grid_col": int(global_col),
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError("declared rectangular frame produced no candidate cells")
    return frame, RectangularFrameAudit(
        candidate_count=int(len(frame)),
        grid_spacing_m=spacing,
        bounds_wgs84=(west, south, east, north),
        metric_crs=metric.to_string(),
        nominal_frame_area_km2=float(polygon.area / 1_000_000.0),
    )


def attach_nearest_anchor_distance(
    candidate_frame: pd.DataFrame,
    anchors: pd.DataFrame,
    *,
    latitude_col: str = "latitude",
    longitude_col: str = "longitude",
) -> pd.DataFrame:
    """Attach direct nearest-population distance to a frozen candidate frame."""
    if candidate_frame is None or candidate_frame.empty:
        raise ValueError("candidate_frame cannot be empty")
    if anchors is None or anchors.empty:
        raise ValueError("at least one historical population anchor is required")
    required = {latitude_col, longitude_col}
    if not required.issubset(candidate_frame.columns) or not required.issubset(anchors.columns):
        raise ValueError("candidate frame and anchors require latitude/longitude")

    candidate = candidate_frame.copy().reset_index(drop=True)
    c_lat = pd.to_numeric(candidate[latitude_col], errors="coerce").to_numpy(float)
    c_lon = pd.to_numeric(candidate[longitude_col], errors="coerce").to_numpy(float)
    a_lat = pd.to_numeric(anchors[latitude_col], errors="coerce").to_numpy(float)
    a_lon = pd.to_numeric(anchors[longitude_col], errors="coerce").to_numpy(float)
    if not np.isfinite(np.r_[c_lat, c_lon, a_lat, a_lon]).all():
        raise ValueError("candidate and anchor coordinates must be complete and finite")

    center_lon = float(np.mean(a_lon))
    center_lat = float(np.mean(a_lat))
    metric = metric_crs_for_lonlat(center_lon, center_lat)
    transformer = Transformer.from_crs("EPSG:4326", metric, always_xy=True)
    cx, cy = transformer.transform(c_lon, c_lat)
    ax, ay = transformer.transform(a_lon, a_lat)
    anchor_xy = np.column_stack([ax, ay])
    nearest = np.full(len(candidate), np.inf, dtype=float)
    for x, y in anchor_xy:
        nearest = np.minimum(nearest, np.hypot(cx - float(x), cy - float(y)))
    candidate["nearest_anchor_km"] = nearest / 1000.0
    return candidate


def partition_local_and_detached(
    candidate_frame: pd.DataFrame,
    *,
    local_boundary_km: float,
    target_component_id: str = "",
    component_col: str = "ecological_component_id",
) -> tuple[pd.DataFrame, DetachedPartitionAudit]:
    """Label LOCAL versus DETACHED lanes without outcome-derived thresholds.

    DETACHED is defined as outside the already declared LOCAL boundary.  When a
    provider supplies component identities, non-local cells are additionally
    labeled as remote parts of the historical component or as other components.
    """
    if candidate_frame is None or candidate_frame.empty:
        raise ValueError("candidate_frame cannot be empty")
    boundary = float(local_boundary_km)
    if boundary <= 0:
        raise ValueError("local_boundary_km must be positive")
    if "nearest_anchor_km" not in candidate_frame.columns:
        raise ValueError("candidate frame requires nearest_anchor_km before partitioning")
    distance = pd.to_numeric(candidate_frame["nearest_anchor_km"], errors="coerce")
    if distance.isna().any() or (distance < 0).any():
        raise ValueError("nearest_anchor_km must be complete and non-negative")

    out = candidate_frame.copy().reset_index(drop=True)
    local = distance.le(boundary + 1e-12)
    out["discovery_lane"] = np.where(local, "LOCAL", "DETACHED_BROAD")
    target = str(target_component_id or "").strip()
    same_component = np.zeros(len(out), dtype=bool)
    if target:
        if component_col not in out.columns:
            raise ValueError(f"target_component_id supplied but candidate frame lacks {component_col}")
        same_component = out[component_col].astype(str).eq(target).to_numpy()
        detached = ~local.to_numpy()
        out.loc[detached & same_component, "discovery_lane"] = "DETACHED_SAME_COMPONENT"
        out.loc[detached & ~same_component, "discovery_lane"] = "DETACHED_OTHER_COMPONENT"

    values = out["discovery_lane"].astype(str)
    detached_mask = values.str.startswith("DETACHED")
    audit = DetachedPartitionAudit(
        candidate_count=int(len(out)),
        local_boundary_km=boundary,
        local_count=int((values == "LOCAL").sum()),
        detached_count=int(detached_mask.sum()),
        detached_same_component_count=int((values == "DETACHED_SAME_COMPONENT").sum()),
        detached_other_component_count=int((values == "DETACHED_OTHER_COMPONENT").sum()),
        target_component_id=target,
    )
    return out, audit
