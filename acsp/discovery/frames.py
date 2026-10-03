"""Generic candidate-frame construction for experimental N4 discovery."""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd
from pyproj import CRS, Transformer
from shapely.geometry import Point
from shapely.ops import transform as shapely_transform, unary_union


@dataclass(frozen=True)
class AnnularFrameSpec:
    grid_spacing_m: float = 100.0
    known_exclusion_km: float = 0.5
    outer_radius_km: float = 2.0

    def validate(self) -> None:
        if float(self.grid_spacing_m) <= 0:
            raise ValueError("grid_spacing_m must be positive")
        if float(self.known_exclusion_km) < 0:
            raise ValueError("known_exclusion_km cannot be negative")
        if float(self.outer_radius_km) <= float(self.known_exclusion_km):
            raise ValueError("outer_radius_km must exceed known_exclusion_km")


@dataclass(frozen=True)
class AnnularFrameAudit:
    anchor_count: int
    candidate_count: int
    grid_spacing_m: float
    known_exclusion_km: float
    outer_radius_km: float
    metric_crs: str
    clipped_by_declared_sector: bool
    nominal_frame_area_km2: float
    human_access_used: bool = False
    field_outcomes_used: bool = False


def metric_crs_for_lonlat(longitude: float, latitude: float) -> CRS:
    zone = max(1, min(60, int(math.floor((float(longitude) + 180.0) / 6.0)) + 1))
    epsg = (32600 if float(latitude) >= 0 else 32700) + zone
    return CRS.from_epsg(epsg)


def build_annular_candidate_frame(
    anchors: pd.DataFrame,
    *,
    spec: AnnularFrameSpec | None = None,
    latitude_col: str = "latitude",
    longitude_col: str = "longitude",
    candidate_id_prefix: str = "candidate",
    clip_geometry_wgs84=None,
) -> tuple[pd.DataFrame, AnnularFrameAudit]:
    """Build a deterministic metric-grid annulus around population anchors.

    ``clip_geometry_wgs84`` may be a predeclared Shapely polygon/multipolygon.
    It is an outer geographic constraint only; this function never infers a
    range sector from held-out outcomes and never reads roads/access layers.
    """
    cfg = spec or AnnularFrameSpec()
    cfg.validate()
    required = {latitude_col, longitude_col}
    missing = sorted(required.difference(anchors.columns))
    if missing:
        raise ValueError(f"anchors missing columns: {missing}")
    work = anchors[[latitude_col, longitude_col]].copy()
    work[latitude_col] = pd.to_numeric(work[latitude_col], errors="coerce")
    work[longitude_col] = pd.to_numeric(work[longitude_col], errors="coerce")
    work = work.dropna().drop_duplicates().reset_index(drop=True)
    if work.empty:
        raise ValueError("at least one complete anchor is required")

    center_lat = float(work[latitude_col].mean())
    center_lon = float(work[longitude_col].mean())
    metric = metric_crs_for_lonlat(center_lon, center_lat)
    to_metric = Transformer.from_crs("EPSG:4326", metric, always_xy=True)
    to_wgs = Transformer.from_crs(metric, "EPSG:4326", always_xy=True)
    ax, ay = to_metric.transform(work[longitude_col].to_numpy(float), work[latitude_col].to_numpy(float))
    anchor_xy = np.column_stack([ax, ay])

    outer_m = float(cfg.outer_radius_km) * 1000.0
    inner_m = float(cfg.known_exclusion_km) * 1000.0
    outer = unary_union([Point(float(x), float(y)).buffer(outer_m) for x, y in anchor_xy])
    if inner_m > 0:
        inner = unary_union([Point(float(x), float(y)).buffer(inner_m) for x, y in anchor_xy])
        frame_geometry = outer.difference(inner)
    else:
        frame_geometry = outer

    clipped = clip_geometry_wgs84 is not None
    if clipped:
        if clip_geometry_wgs84.is_empty:
            raise ValueError("declared clip geometry is empty")
        clip_metric = shapely_transform(to_metric.transform, clip_geometry_wgs84)
        frame_geometry = frame_geometry.intersection(clip_metric)
    if frame_geometry.is_empty:
        raise ValueError("candidate-frame geometry is empty after clipping/exclusion")

    spacing = float(cfg.grid_spacing_m)
    minx, miny, maxx, maxy = frame_geometry.bounds
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
            if not frame_geometry.covers(Point(float(x), float(y))):
                continue
            global_col = first_col + local_col
            nearest_m = float(np.min(np.sqrt((anchor_xy[:, 0] - x) ** 2 + (anchor_xy[:, 1] - y) ** 2)))
            lon, lat = to_wgs.transform(x, y)
            rows.append(
                {
                    "candidate_cell_id": f"{candidate_id_prefix}_r{global_row}_c{global_col}",
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "grid_row": int(global_row),
                    "grid_col": int(global_col),
                    "nearest_anchor_km": nearest_m / 1000.0,
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError("candidate frame contains no grid cells")
    audit = AnnularFrameAudit(
        anchor_count=int(len(work)),
        candidate_count=int(len(frame)),
        grid_spacing_m=spacing,
        known_exclusion_km=float(cfg.known_exclusion_km),
        outer_radius_km=float(cfg.outer_radius_km),
        metric_crs=metric.to_string(),
        clipped_by_declared_sector=bool(clipped),
        nominal_frame_area_km2=float(frame_geometry.area / 1_000_000.0),
    )
    return frame, audit
