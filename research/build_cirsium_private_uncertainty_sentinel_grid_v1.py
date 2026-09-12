#!/usr/bin/env python3
"""Build a private frozen UNCERTAINTY_FOOTPRINT sentinel raw grid.

Execution-only adapter for units such as CIR02/CIR12. It creates the frozen 100 m
range-sector grid, clips it to the union of declared coordinate-uncertainty
footprints (>1 km), then attaches GSI DEM terrain and ESA WorldCover 2021 250 m
neighbourhood primitives. It never invents an exact anchor, reads field outcomes,
or uses human-access layers.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from shapely.geometry import Point
from shapely.ops import transform as shapely_transform

from acsp.sentinel_support import LOCAL_ANCHOR_CEILING_M, clip_to_uncertainty_footprint_union
from research.build_cirsium_private_alpine_local_grid_v1 import (
    GRID_SPACING_M,
    _inside_repo,
    _load_geojson_geometry,
    _sample_terrain,
    _utm_crs,
)
from research.campanula_worldcover_discovery import neighborhood_features


def _sector_grid(range_sector) -> tuple[pd.DataFrame, object]:
    centroid = range_sector.centroid
    metric = _utm_crs(float(centroid.x), float(centroid.y))
    to_metric = Transformer.from_crs("EPSG:4326", metric, always_xy=True)
    to_wgs84 = Transformer.from_crs(metric, "EPSG:4326", always_xy=True)
    sector_m = shapely_transform(to_metric.transform, range_sector)

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
            lon, lat = to_wgs84.transform(x, y)
            records.append(
                {
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "grid_row": int(grid_row),
                    "grid_col": int(grid_col),
                }
            )
    frame = pd.DataFrame(records)
    if frame.empty:
        raise ValueError("declared range sector contains no 100 m candidate-grid cells")
    return frame, metric


def _validate_uncertainty_evidence(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"latitude", "longitude", "coordinate_uncertainty_m"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"sentinel uncertainty evidence missing columns: {missing}")
    out = frame.copy()
    for column in required:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    if out[list(required)].isna().any().any() or out.empty:
        raise ValueError("sentinel uncertainty evidence must be complete and non-empty")
    if (out["coordinate_uncertainty_m"] <= LOCAL_ANCHOR_CEILING_M).any():
        raise ValueError("UNCERTAINTY_FOOTPRINT evidence must be strictly above the frozen 1 km local-anchor ceiling")
    return out


def _sample_worldcover(candidates: pd.DataFrame, path: Path) -> pd.DataFrame:
    with rasterio.open(path) as src:
        features = neighborhood_features(
            src,
            candidates["longitude"].to_numpy(float),
            candidates["latitude"].to_numpy(float),
            radii_m=(250,),
        )
    needed = (
        "wc_tree_frac_250m",
        "wc_grass_frac_250m",
        "wc_bare_frac_250m",
        "wc_water_frac_250m",
        "wc_wetland_frac_250m",
        "wc_edge_mix_250m",
    )
    if features[list(needed)].isna().any().any():
        raise ValueError("WorldCover snapshot does not provide complete 250 m neighbourhoods for all sentinel candidates")
    return pd.concat([candidates.reset_index(drop=True), features.reset_index(drop=True)], axis=1)


def build_uncertainty_sentinel_raw_grid(
    range_sector_geojson: Path,
    sentinel_evidence_csv: Path,
    gsi_dem: Path,
    worldcover: Path,
    *,
    unit_id: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    sector = _load_geojson_geometry(range_sector_geojson)
    evidence = _validate_uncertainty_evidence(pd.read_csv(sentinel_evidence_csv))
    candidates, metric = _sector_grid(sector)
    before_clip = int(len(candidates))
    candidates, footprint_audit = clip_to_uncertainty_footprint_union(candidates, evidence)
    candidates = _sample_terrain(candidates, gsi_dem)
    candidates = _sample_worldcover(candidates, worldcover)
    candidates.insert(
        0,
        "candidate_cell_id",
        [f"{unit_id}_r{int(r)}_c{int(c)}" for r, c in zip(candidates["grid_row"], candidates["grid_col"])],
    )
    if candidates["candidate_cell_id"].duplicated().any():
        raise AssertionError("candidate_cell_id must be unique")
    if not candidates["broad_sentinel_support"].between(0.0, 1.0).all():
        raise AssertionError("uncertainty-footprint support must lie in [0,1]")

    summary = {
        "schema_version": "cirsium-private-uncertainty-sentinel-grid-v1",
        "status": "PRIVATE_RAW_GRID_BUILT_PRE_FIELD",
        "cohort_unit_id": str(unit_id),
        "occurrence_problem_class": "SENTINEL",
        "sentinel_subregime": "UNCERTAINTY_FOOTPRINT",
        "grid_spacing_m": GRID_SPACING_M,
        "range_sector_grid_rows_before_footprint_clip": before_clip,
        "candidate_rows_after_footprint_clip_and_source_support": int(len(candidates)),
        "metric_crs": metric.to_string(),
        "unique_uncertainty_footprints": int(footprint_audit.unique_footprint_count),
        "local_anchor_ceiling_m": float(LOCAL_ANCHOR_CEILING_M),
        "worldcover_radius_m": 250,
        "field_outcomes_used": False,
        "human_access_used": False,
        "distance_preference_inside_uncertainty_footprint": False,
        "exact_coordinates_public": False,
        "next_gate": "Hash raw grid and private sources into the source manifest, then run prepare_cirsium_private_candidate_frame_v1.py for the frozen structural family.",
    }
    return candidates, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-id", required=True)
    parser.add_argument("--range-sector-geojson", type=Path, required=True)
    parser.add_argument("--sentinel-evidence-csv", type=Path, required=True)
    parser.add_argument("--gsi-dem", type=Path, required=True)
    parser.add_argument("--worldcover", type=Path, required=True)
    parser.add_argument("--private-out-csv", type=Path, required=True)
    parser.add_argument("--private-summary-json", type=Path, required=True)
    args = parser.parse_args()

    if _inside_repo(args.private_out_csv) or _inside_repo(args.private_summary_json):
        raise SystemExit("refusing to write coordinate-bearing private sentinel outputs inside the git repository")
    for path in (args.range_sector_geojson, args.sentinel_evidence_csv, args.gsi_dem, args.worldcover):
        if not path.is_file():
            raise SystemExit(f"missing private source file: {path}")

    frame, summary = build_uncertainty_sentinel_raw_grid(
        args.range_sector_geojson,
        args.sentinel_evidence_csv,
        args.gsi_dem,
        args.worldcover,
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
