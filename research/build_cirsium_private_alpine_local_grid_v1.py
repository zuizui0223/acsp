#!/usr/bin/env python3
"""Build a private 100 m LOCAL_CONTINUATION terrain grid for frozen alpine Cirsium units.

This is an execution adapter, not a new ecological model. It implements the
already-frozen candidate-frame geometry (0.5--2.0 km annuli around eligible
primary anchors, clipped to the declared range sector) and reuses the pinned GSI
DEM terrain semantics from Campanula development. Coordinate-bearing outputs are
refused inside the public repository.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from pyproj import CRS, Transformer
from rasterio.transform import rowcol
from shapely.geometry import Point, shape
from shapely.ops import transform as shapely_transform, unary_union

from research.campanula_microterrain_discovery import FEATURES, surface_vector, terrain_surface

REPO_ROOT = Path(__file__).resolve().parents[1]
GRID_SPACING_M = 100.0
INNER_EXCLUSION_M = 500.0
OUTER_RADIUS_M = 2000.0
ALPINE_REQUIRED = ("elev", "slope100", "tpi300", "rough300")


def _inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPO_ROOT.resolve())
        return True
    except ValueError:
        return False


def _load_geojson_geometry(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    kind = payload.get("type")
    if kind == "FeatureCollection":
        geometries = [shape(feature["geometry"]) for feature in payload.get("features", []) if feature.get("geometry")]
        if not geometries:
            raise ValueError("range-sector FeatureCollection contains no geometry")
        geometry = unary_union(geometries)
    elif kind == "Feature":
        geometry = shape(payload["geometry"])
    else:
        geometry = shape(payload)
    if geometry.is_empty:
        raise ValueError("range-sector geometry is empty")
    return geometry


def _utm_crs(lon: float, lat: float) -> CRS:
    zone = int(math.floor((float(lon) + 180.0) / 6.0) + 1)
    zone = max(1, min(60, zone))
    epsg = (32600 if lat >= 0 else 32700) + zone
    return CRS.from_epsg(epsg)


def _require_anchor_table(frame: pd.DataFrame) -> pd.DataFrame:
    missing = sorted({"latitude", "longitude"}.difference(frame.columns))
    if missing:
        raise ValueError(f"primary-anchor table missing columns: {missing}")
    out = frame.copy()
    for column in ("latitude", "longitude"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    if out[["latitude", "longitude"]].isna().any().any() or out.empty:
        raise ValueError("primary-anchor coordinates must be complete and non-empty")
    if ((out["latitude"] < -90) | (out["latitude"] > 90)).any():
        raise ValueError("invalid anchor latitude")
    if ((out["longitude"] < -180) | (out["longitude"] > 180)).any():
        raise ValueError("invalid anchor longitude")
    return out


def _candidate_geometry(range_sector, anchors: pd.DataFrame) -> tuple[pd.DataFrame, CRS]:
    centroid = range_sector.centroid
    metric = _utm_crs(float(centroid.x), float(centroid.y))
    to_metric = Transformer.from_crs("EPSG:4326", metric, always_xy=True)
    to_wgs84 = Transformer.from_crs(metric, "EPSG:4326", always_xy=True)
    sector_m = shapely_transform(to_metric.transform, range_sector)
    anchor_xy = np.column_stack(
        to_metric.transform(anchors["longitude"].to_numpy(float), anchors["latitude"].to_numpy(float))
    )

    minx, miny, maxx, maxy = sector_m.bounds
    x0 = math.floor(minx / GRID_SPACING_M) * GRID_SPACING_M
    y0 = math.floor(miny / GRID_SPACING_M) * GRID_SPACING_M
    x1 = math.ceil(maxx / GRID_SPACING_M) * GRID_SPACING_M
    y1 = math.ceil(maxy / GRID_SPACING_M) * GRID_SPACING_M
    cols = np.arange(0, int(round((x1 - x0) / GRID_SPACING_M)) + 1, dtype=int)
    rows = np.arange(0, int(round((y1 - y0) / GRID_SPACING_M)) + 1, dtype=int)

    records: list[dict[str, object]] = []
    for grid_row in rows:
        y = y0 + grid_row * GRID_SPACING_M
        for grid_col in cols:
            x = x0 + grid_col * GRID_SPACING_M
            point = Point(float(x), float(y))
            if not sector_m.covers(point):
                continue
            distances = np.sqrt((anchor_xy[:, 0] - x) ** 2 + (anchor_xy[:, 1] - y) ** 2)
            nearest = float(np.min(distances))
            if nearest < INNER_EXCLUSION_M - 1e-9 or nearest > OUTER_RADIUS_M + 1e-9:
                continue
            lon, lat = to_wgs84.transform(x, y)
            records.append(
                {
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "grid_row": int(grid_row),
                    "grid_col": int(grid_col),
                    "nearest_anchor_km": nearest / 1000.0,
                }
            )
    result = pd.DataFrame(records)
    if result.empty:
        raise ValueError("frozen 0.5-2.0 km annulus does not intersect the declared range sector")
    return result, metric


def _sample_terrain(candidates: pd.DataFrame, dem_path: Path) -> pd.DataFrame:
    surface = terrain_surface(dem_path, target_res=25.0)
    if surface["crs"] is None:
        raise ValueError("GSI DEM snapshot must declare a CRS")
    to_dem = Transformer.from_crs("EPSG:4326", surface["crs"], always_xy=True)
    xs, ys = to_dem.transform(candidates["longitude"].to_numpy(float), candidates["latitude"].to_numpy(float))
    rr, cc = rowcol(surface["transform"], xs, ys)
    rows: list[dict[str, float] | None] = []
    height, width = surface["arr"].shape
    for r, c in zip(rr, cc):
        r = int(r)
        c = int(c)
        if not (0 <= r < height and 0 <= c < width):
            rows.append(None)
            continue
        vector = surface_vector(surface, r, c)
        if not np.isfinite(vector).all():
            rows.append(None)
            continue
        rows.append({name: float(value) for name, value in zip(FEATURES, vector)})

    keep = [value is not None for value in rows]
    out = candidates.loc[keep].copy().reset_index(drop=True)
    valid_rows = [value for value in rows if value is not None]
    if out.empty:
        raise ValueError("no annular candidate cell has complete terrain support in the GSI DEM snapshot")
    terrain = pd.DataFrame(valid_rows)
    for column in terrain.columns:
        out[column] = terrain[column].to_numpy(float)
    missing = [column for column in ALPINE_REQUIRED if column not in out.columns]
    if missing:
        raise AssertionError(f"terrain extraction missing frozen alpine columns: {missing}")
    return out


def build_alpine_local_raw_grid(
    range_sector_geojson: Path,
    primary_anchor_csv: Path,
    gsi_dem: Path,
    *,
    unit_id: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    sector = _load_geojson_geometry(range_sector_geojson)
    anchors = _require_anchor_table(pd.read_csv(primary_anchor_csv))
    candidates, metric = _candidate_geometry(sector, anchors)
    candidates = _sample_terrain(candidates, gsi_dem)
    candidates.insert(
        0,
        "candidate_cell_id",
        [f"{unit_id}_r{int(r)}_c{int(c)}" for r, c in zip(candidates["grid_row"], candidates["grid_col"])],
    )
    if candidates["candidate_cell_id"].duplicated().any():
        raise AssertionError("candidate_cell_id must be unique")
    summary = {
        "schema_version": "cirsium-private-alpine-local-grid-v1",
        "status": "PRIVATE_RAW_GRID_BUILT_PRE_FIELD",
        "cohort_unit_id": str(unit_id),
        "feature_family": "ALPINE_TOPOGRAPHIC_STRUCTURE",
        "grid_spacing_m": GRID_SPACING_M,
        "known_point_exclusion_km": INNER_EXCLUSION_M / 1000.0,
        "outer_radius_km": OUTER_RADIUS_M / 1000.0,
        "candidate_rows": int(len(candidates)),
        "metric_crs": metric.to_string(),
        "terrain_columns": list(FEATURES),
        "field_outcomes_used": False,
        "human_access_used": False,
        "exact_coordinates_public": False,
        "next_gate": "Hash this raw grid and private sources into the frozen private source manifest, then run prepare_cirsium_private_candidate_frame_v1.py.",
    }
    return candidates, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-id", required=True)
    parser.add_argument("--range-sector-geojson", type=Path, required=True)
    parser.add_argument("--primary-anchor-csv", type=Path, required=True)
    parser.add_argument("--gsi-dem", type=Path, required=True)
    parser.add_argument("--private-out-csv", type=Path, required=True)
    parser.add_argument("--private-summary-json", type=Path, required=True)
    args = parser.parse_args()

    if _inside_repo(args.private_out_csv) or _inside_repo(args.private_summary_json):
        raise SystemExit("refusing to write coordinate-bearing private raw-grid outputs inside the git repository")
    for path in (args.range_sector_geojson, args.primary_anchor_csv, args.gsi_dem):
        if not path.is_file():
            raise SystemExit(f"missing private source file: {path}")

    frame, summary = build_alpine_local_raw_grid(
        args.range_sector_geojson,
        args.primary_anchor_csv,
        args.gsi_dem,
        unit_id=args.unit_id,
    )
    args.private_out_csv.parent.mkdir(parents=True, exist_ok=True)
    args.private_summary_json.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.private_out_csv, index=False)
    args.private_summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
