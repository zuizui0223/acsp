#!/usr/bin/env python3
"""Build private raw grids for non-footprint fresh SENTINEL Cirsium units.

This adapter covers the two frozen fresh units whose SENTINEL regime supplies a
range-sector context but no known-point kernel: CIR06 (legacy alpine context) and
CIR13 (coarse grassland context). It consumes only the already-declared private
sector geometry plus public ecological rasters materialized before field outcomes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from build_cirsium_private_alpine_local_grid_v1 import _inside_repo, _load_geojson_geometry, _sample_terrain
from build_cirsium_private_uncertainty_sentinel_grid_v1 import _sample_worldcover, _sector_grid

SUPPORTED = {
    "CIR06": "ALPINE_TOPOGRAPHIC_STRUCTURE",
    "CIR13": "OPEN_GRASSLAND_STRUCTURE",
}


def expected_family(unit_id: str) -> str:
    try:
        return SUPPORTED[str(unit_id)]
    except KeyError as exc:
        raise ValueError(f"unit is not supported by the frozen sector-context adapter: {unit_id}") from exc


def build_sector_structural_raw_grid(
    range_sector_geojson: Path,
    gsi_dem: Path,
    *,
    unit_id: str,
    feature_family: str,
    worldcover: Path | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    expected = expected_family(unit_id)
    if str(feature_family) != expected:
        raise ValueError(f"frozen feature-family mismatch for {unit_id}: expected {expected}, got {feature_family}")
    if not range_sector_geojson.is_file() or not gsi_dem.is_file():
        raise ValueError("range-sector geometry and GSI DEM must both exist")

    sector = _load_geojson_geometry(range_sector_geojson)
    candidates, metric = _sector_grid(sector)
    raw = _sample_terrain(candidates, gsi_dem)

    if expected == "OPEN_GRASSLAND_STRUCTURE":
        if worldcover is None or not worldcover.is_file():
            raise ValueError("CIR13 open-grassland raw grid requires frozen ESA WorldCover 2021")
        raw = _sample_worldcover(raw, worldcover)
    elif worldcover is not None:
        raise ValueError("CIR06 alpine raw grid does not add an undeclared WorldCover dependency")

    raw.insert(
        0,
        "candidate_cell_id",
        [f"{unit_id}_r{int(r)}_c{int(c)}" for r, c in zip(raw["grid_row"], raw["grid_col"])],
    )
    if raw["candidate_cell_id"].duplicated().any():
        raise AssertionError("candidate_cell_id must be unique")

    summary = {
        "schema_version": "cirsium-private-sector-structural-grid-v1",
        "status": "PRIVATE_RAW_GRID_BUILT_PRE_FIELD",
        "cohort_unit_id": unit_id,
        "feature_family": expected,
        "grid_spacing_m": 100,
        "candidate_rows": int(len(raw)),
        "metric_crs": metric.to_string(),
        "gsi_dem_used": True,
        "worldcover_used": expected == "OPEN_GRASSLAND_STRUCTURE",
        "field_outcomes_used": False,
        "human_access_used": False,
        "known_point_kernel_used": False,
        "exact_coordinates_public": False,
        "next_gate": "Hash this raw grid and declared sources into the private source manifest, then run prepare_cirsium_private_candidate_frame_v1.py.",
    }
    return raw, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-id", choices=tuple(SUPPORTED), required=True)
    parser.add_argument("--feature-family", required=True)
    parser.add_argument("--range-sector-geojson", type=Path, required=True)
    parser.add_argument("--gsi-dem", type=Path, required=True)
    parser.add_argument("--worldcover", type=Path)
    parser.add_argument("--private-out-csv", type=Path, required=True)
    parser.add_argument("--private-summary-json", type=Path, required=True)
    args = parser.parse_args()

    if _inside_repo(args.private_out_csv) or _inside_repo(args.private_summary_json):
        raise SystemExit("refusing to write coordinate-bearing private raw-grid outputs inside the git repository")
    raw, summary = build_sector_structural_raw_grid(
        args.range_sector_geojson,
        args.gsi_dem,
        unit_id=args.unit_id,
        feature_family=args.feature_family,
        worldcover=args.worldcover,
    )
    args.private_out_csv.parent.mkdir(parents=True, exist_ok=True)
    args.private_summary_json.parent.mkdir(parents=True, exist_ok=True)
    raw.to_csv(args.private_out_csv, index=False)
    args.private_summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
