#!/usr/bin/env python3
"""Build a private frozen coastal/island LOCAL_CONTINUATION raw grid.

Execution-only adapter for units such as CIR08/CIR09. It uses the already frozen
0.5--2.0 km local annulus, ESA WorldCover 2021 250 m neighbourhood fractions,
a private derivative of the pinned GSI coastline snapshot, and a predeclared
ecological component geometry. It does not read field outcomes or access layers.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import transform as shapely_transform, unary_union

from research.build_cirsium_private_alpine_local_grid_v1 import (
    INNER_EXCLUSION_M,
    OUTER_RADIUS_M,
    GRID_SPACING_M,
    _candidate_geometry,
    _inside_repo,
    _load_geojson_geometry,
    _require_anchor_table,
)
from research.campanula_worldcover_discovery import neighborhood_features


def _load_coastline(path: Path):
    geometry = _load_geojson_geometry(path)
    if geometry.is_empty:
        raise ValueError("coastline geometry is empty")
    return geometry


def _load_components(path: Path, id_property: str) -> list[tuple[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("type") != "FeatureCollection":
        raise ValueError("ecological component definition must be a GeoJSON FeatureCollection")
    result: list[tuple[str, object]] = []
    for feature in payload.get("features", []):
        if not feature.get("geometry"):
            continue
        properties = feature.get("properties") or {}
        if id_property not in properties or not str(properties[id_property]).strip():
            raise ValueError(f"ecological component feature missing {id_property}")
        result.append((str(properties[id_property]), shape(feature["geometry"])))
    if not result:
        raise ValueError("ecological component definition contains no usable features")
    return result


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
        raise ValueError("WorldCover snapshot does not provide complete 250 m neighbourhoods for all candidates")
    return pd.concat([candidates.reset_index(drop=True), features.reset_index(drop=True)], axis=1)


def _add_coast_and_component(
    candidates: pd.DataFrame,
    *,
    coastline_geojson: Path,
    component_geojson: Path,
    target_component_id: str,
    component_id_property: str,
) -> pd.DataFrame:
    if not str(target_component_id).strip():
        raise ValueError("target_component_id is required")
    coast_wgs = _load_coastline(coastline_geojson)
    components = _load_components(component_geojson, component_id_property)

    centroid = _load_geojson_geometry(component_geojson).centroid
    # Reuse the local metric CRS implicit in _candidate_geometry via a transformer
    # selected from the target component centroid.
    from research.build_cirsium_private_alpine_local_grid_v1 import _utm_crs

    metric = _utm_crs(float(centroid.x), float(centroid.y))
    to_metric = Transformer.from_crs("EPSG:4326", metric, always_xy=True)
    coast_m = shapely_transform(to_metric.transform, coast_wgs)
    component_m = [
        (component_id, shapely_transform(to_metric.transform, geometry))
        for component_id, geometry in components
    ]

    xs, ys = to_metric.transform(
        candidates["longitude"].to_numpy(float),
        candidates["latitude"].to_numpy(float),
    )
    coast_distance = []
    component_ids = []
    for x, y in zip(xs, ys):
        point = Point(float(x), float(y))
        coast_distance.append(float(point.distance(coast_m)))
        hits = [component_id for component_id, geometry in component_m if geometry.covers(point)]
        if len(hits) > 1:
            raise ValueError("candidate belongs to multiple ecological components")
        component_ids.append(hits[0] if hits else "OUTSIDE_DECLARED_COMPONENT")

    out = candidates.copy()
    out["coast_distance_m"] = np.asarray(coast_distance, dtype=float)
    out["ecological_component_id"] = component_ids
    if str(target_component_id) not in set(out["ecological_component_id"]):
        raise ValueError("target ecological component has no candidate cells in the frozen local frame")
    return out


def build_coastal_local_raw_grid(
    range_sector_geojson: Path,
    primary_anchor_csv: Path,
    worldcover: Path,
    coastline_geojson: Path,
    component_geojson: Path,
    *,
    target_component_id: str,
    unit_id: str,
    component_id_property: str = "ecological_component_id",
) -> tuple[pd.DataFrame, dict[str, object]]:
    sector = _load_geojson_geometry(range_sector_geojson)
    anchors = _require_anchor_table(pd.read_csv(primary_anchor_csv))
    candidates, metric = _candidate_geometry(sector, anchors)
    candidates = _sample_worldcover(candidates, worldcover)
    candidates = _add_coast_and_component(
        candidates,
        coastline_geojson=coastline_geojson,
        component_geojson=component_geojson,
        target_component_id=target_component_id,
        component_id_property=component_id_property,
    )
    candidates.insert(
        0,
        "candidate_cell_id",
        [f"{unit_id}_r{int(r)}_c{int(c)}" for r, c in zip(candidates["grid_row"], candidates["grid_col"])],
    )
    summary = {
        "schema_version": "cirsium-private-coastal-local-grid-v1",
        "status": "PRIVATE_RAW_GRID_BUILT_PRE_FIELD",
        "cohort_unit_id": str(unit_id),
        "feature_family": "COASTAL_ISLAND_STRUCTURE",
        "grid_spacing_m": GRID_SPACING_M,
        "known_point_exclusion_km": INNER_EXCLUSION_M / 1000.0,
        "outer_radius_km": OUTER_RADIUS_M / 1000.0,
        "candidate_rows": int(len(candidates)),
        "metric_crs": metric.to_string(),
        "target_component_id": str(target_component_id),
        "worldcover_radius_m": 250,
        "coastline_semantics": "distance to private derivative of frozen GSI Fundamental Geospatial Data Basic Items coastline snapshot",
        "field_outcomes_used": False,
        "human_access_used": False,
        "exact_coordinates_public": False,
        "next_gate": "Hash raw grid and private sources into the source manifest, then run prepare_cirsium_private_candidate_frame_v1.py with the same target_component_id.",
    }
    return candidates, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-id", required=True)
    parser.add_argument("--range-sector-geojson", type=Path, required=True)
    parser.add_argument("--primary-anchor-csv", type=Path, required=True)
    parser.add_argument("--worldcover", type=Path, required=True)
    parser.add_argument("--gsi-coastline-geojson", type=Path, required=True)
    parser.add_argument("--component-geojson", type=Path, required=True)
    parser.add_argument("--target-component-id", required=True)
    parser.add_argument("--component-id-property", default="ecological_component_id")
    parser.add_argument("--private-out-csv", type=Path, required=True)
    parser.add_argument("--private-summary-json", type=Path, required=True)
    args = parser.parse_args()

    if _inside_repo(args.private_out_csv) or _inside_repo(args.private_summary_json):
        raise SystemExit("refusing to write coordinate-bearing private raw-grid outputs inside the git repository")
    for path in (
        args.range_sector_geojson,
        args.primary_anchor_csv,
        args.worldcover,
        args.gsi_coastline_geojson,
        args.component_geojson,
    ):
        if not path.is_file():
            raise SystemExit(f"missing private source file: {path}")

    frame, summary = build_coastal_local_raw_grid(
        args.range_sector_geojson,
        args.primary_anchor_csv,
        args.worldcover,
        args.gsi_coastline_geojson,
        args.component_geojson,
        target_component_id=args.target_component_id,
        unit_id=args.unit_id,
        component_id_property=args.component_id_property,
    )
    args.private_out_csv.parent.mkdir(parents=True, exist_ok=True)
    args.private_summary_json.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.private_out_csv, index=False)
    args.private_summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
