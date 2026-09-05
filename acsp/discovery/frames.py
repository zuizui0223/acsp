"""Generic candidate-frame construction for experimental N4 discovery."""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd
from pyproj import CRS, Transformer
from shapely import contains_xy
from shapely.geometry import Point, box
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


@dataclass(frozen=True)
class RectangularFrameAudit:
    candidate_count: int
    grid_spacing_m: float
    metric_crs: str
    bounds_wgs84: tuple[float, float, float, float]
    nominal_frame_area_km2: float
    human_access_used: bool = False
    field_outcomes_used: bool = False


def metric_crs_for_lonlat(longitude: float, latitude: float) -> CRS:
    zone = max(1, min(60, int(math.floor((float(longitude) + 180.0) / 6.0)) + 1))
    epsg = (32600 if float(latitude) >= 0 else 32700) + zone
    return CRS.from_epsg(epsg)


def build_rectangular_candidate_frame(
    bounds_wgs84: tuple[float, float, float, float],
    *,
    grid_spacing_m: float = 100.0,
    candidate_id_prefix: str = "candidate",
) -> tuple[pd.DataFrame, RectangularFrameAudit]:
    """Build one deterministic metric grid inside declared WGS84 bounds.

    This is a provider-neutral outer-frame primitive. It does not use occurrence
    outcomes, roads, access, or inferred range expansion. The metric grid is
    globally aligned within the selected UTM zone so a later annular frame built
    with the same spacing can be compared without changing cell resolution.
    """
    west, south, east, north = map(float, bounds_wgs84)
    if not (-180.0 <= west < east <= 180.0 and -90.0 <= south < north <= 90.0):
        raise ValueError("bounds_wgs84 must satisfy valid west < east and south < north")
    spacing = float(grid_spacing_m)
    if spacing <= 0:
        raise ValueError("grid_spacing_m must be positive")

    center_lon = (west + east) / 2.0
    center_lat = (south + north) / 2.0
    metric = metric_crs_for_lonlat(center_lon, center_lat)
    to_metric = Transformer.from_crs("EPSG:4326", metric, always_xy=True)
    to_wgs = Transformer.from_crs(metric, "EPSG:4326", always_xy=True)
    declared_wgs84 = box(west, south, east, north)
    declared_metric = shapely_transform(to_metric.transform, declared_wgs84)

    minx, miny, maxx, maxy = declared_metric.bounds
    x0 = math.floor(minx / spacing) * spacing
    y0 = math.floor(miny / spacing) * spacing
    x1 = math.ceil(maxx / spacing) * spacing
    y1 = math.ceil(maxy / spacing) * spacing
    xs = np.arange(x0, x1 + spacing * 0.5, spacing, dtype=float)
    ys = np.arange(y0, y1 + spacing * 0.5, spacing, dtype=float)
    xx, yy = np.meshgrid(xs, ys)
    flat_x = xx.ravel()
    flat_y = yy.ravel()
    inside = contains_xy(declared_metric, flat_x, flat_y)
    if not bool(np.any(inside)):
        raise ValueError("declared rectangular frame contains no grid cells")

    selected_x = flat_x[inside]
    selected_y = flat_y[inside]
    lon, lat = to_wgs.transform(selected_x, selected_y)
    global_cols = np.rint(selected_x / spacing).astype(np.int64)
    global_rows = np.rint(selected_y / spacing).astype(np.int64)
    frame = pd.DataFrame(
        {
            "candidate_cell_id": [
                f"{candidate_id_prefix}_r{int(row)}_c{int(col)}"
                for row, col in zip(global_rows, global_cols)
            ],
            "latitude": np.asarray(lat, dtype=float),
            "longitude": np.asarray(lon, dtype=float),
            "grid_row": global_rows,
            "grid_col": global_cols,
        }
    )
    if frame["candidate_cell_id"].duplicated().any():
        raise AssertionError("rectangular frame generated duplicate candidate IDs")
    audit = RectangularFrameAudit(
        candidate_count=int(len(frame)),
        grid_spacing_m=spacing,
        metric_crs=metric.to_string(),
        bounds_wgs84=(west, south, east, north),
        nominal_frame_area_km2=float(declared_metric.area / 1_000_000.0),
    )
    return frame, audit


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
