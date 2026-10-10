#!/usr/bin/env python3
"""Audit the size of local 100-m refinement around frozen 2.5% coarse centers.

This is geometry only. It restores coordinates for the highest-ranked 2.5% of
source-ready coarse candidates and counts the exact union of shared 100-m grid
cells inside the predeclared Cirsium 2-km primary and 5-km sensitivity radii.
No fine ecological score, patching, recovery, access or field outcome is read.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pyproj import CRS, Transformer

from acsp.global_geometry import fetch_geoboundaries_country_geometry
from research.build_cirsium_fresh_sentinel_public_broad_frame_v2 import build_fresh_sentinel_v2_outer_frame

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_v2_local_refinement_size_audit_v1.json"
FRAME_CONTRACT = ROOT / "validation" / "cirsium_candidate_frame_contract_v1.json"
UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
READY = "SOURCE_READY_FOR_FAMILY_COARSE_STAGE"
EXPECTED_CANDIDATES = 39200
SUPPORT_FRACTION = 0.025
GRID_M = 100.0
RADII_KM = (2.0, 5.0)
PROJ_STRING = "+proj=aeqd +lat_0=36 +lon_0=138 +datum=WGS84 +units=m +no_defs"


def _validate_contracts() -> None:
    c = json.loads(CONTRACT.read_text(encoding="utf-8"))
    f = json.loads(FRAME_CONTRACT.read_text(encoding="utf-8"))
    if c.get("status") != "FROZEN_BEFORE_LOCAL_REFINEMENT_SIZE_AUDIT":
        raise ValueError("local-refinement size audit contract is not frozen")
    if float(c["coarse_center_rule"]["support_fraction"]) != SUPPORT_FRACTION:
        raise ValueError("support fraction drifted")
    if float(c["fine_frame_constants"]["grid_spacing_m"]) != GRID_M:
        raise ValueError("grid spacing drifted")
    if tuple(float(x) for x in (c["fine_frame_constants"]["primary_radius_km"], c["fine_frame_constants"]["sensitivity_radius_km"])) != RADII_KM:
        raise ValueError("audit radii drifted")
    if float(f["grid"]["target_spacing_m"]) != GRID_M:
        raise ValueError("Cirsium frame contract grid spacing disagrees")
    if float(f["local_continuation"]["primary_outer_radius_km"]) != 2.0:
        raise ValueError("Cirsium primary radius disagrees")
    if float(f["local_continuation"]["sensitivity_outer_radius_km"]) != 5.0:
        raise ValueError("Cirsium sensitivity radius disagrees")


def _transformer() -> Transformer:
    return Transformer.from_crs("EPSG:4326", CRS.from_proj4(PROJ_STRING), always_xy=True)


def _cell_set_for_center(x: float, y: float, radius_m: float) -> set[tuple[int, int]]:
    min_col = math.floor((x - radius_m) / GRID_M)
    max_col = math.floor((x + radius_m) / GRID_M)
    min_row = math.floor((y - radius_m) / GRID_M)
    max_row = math.floor((y + radius_m) / GRID_M)
    r2 = radius_m * radius_m
    cells: set[tuple[int, int]] = set()
    for row in range(min_row, max_row + 1):
        cy = (row + 0.5) * GRID_M
        dy2 = (cy - y) ** 2
        if dy2 > r2:
            continue
        for col in range(min_col, max_col + 1):
            cx = (col + 0.5) * GRID_M
            if (cx - x) ** 2 + dy2 <= r2 + 1e-9:
                cells.add((row, col))
    return cells


def audit_unit(order: pd.DataFrame, outer: pd.DataFrame, unit: str) -> dict[str, Any]:
    if len(order) != EXPECTED_CANDIDATES:
        raise ValueError(f"{unit} production coarse order must contain 39,200 rows")
    ready = order.loc[order["source_state"].astype(str).eq(READY)].copy()
    ready["coarse_evidence_rank"] = pd.to_numeric(ready["coarse_evidence_rank"], errors="raise").astype(int)
    ready = ready.sort_values("coarse_evidence_rank", kind="mergesort").reset_index(drop=True)
    if ready["coarse_evidence_rank"].tolist() != list(range(1, len(ready) + 1)):
        raise ValueError(f"{unit} source-ready order is not complete")
    retain_n = int(math.ceil(SUPPORT_FRACTION * len(ready)))
    retained = ready.iloc[:retain_n].copy()

    coords = outer.set_index(outer["candidate_cell_id"].astype(str))[["latitude", "longitude"]]
    retained.index = retained["candidate_cell_id"].astype(str)
    retained = retained.join(coords, how="left").reset_index(drop=True)
    if retained[["latitude", "longitude"]].isna().any().any():
        raise ValueError(f"{unit} failed to restore frozen coordinates")

    transformer = _transformer()
    xs, ys = transformer.transform(
        pd.to_numeric(retained["longitude"], errors="raise").to_numpy(float),
        pd.to_numeric(retained["latitude"], errors="raise").to_numpy(float),
    )
    radius_results: dict[str, Any] = {}
    for radius_km in RADII_KM:
        radius_m = radius_km * 1000.0
        union: set[tuple[int, int]] = set()
        raw = 0
        for x, y in zip(xs, ys):
            cells = _cell_set_for_center(float(x), float(y), radius_m)
            raw += len(cells)
            union.update(cells)
        union_count = len(union)
        radius_results[f"{radius_km:g}km"] = {
            "radius_km": radius_km,
            "retained_coarse_center_count": retain_n,
            "raw_center_cell_memberships": int(raw),
            "unioned_100m_cell_count": int(union_count),
            "overlap_memberships_removed": int(raw - union_count),
            "overlap_fraction": float((raw - union_count) / raw) if raw else 0.0,
            "union_area_km2": float(union_count * GRID_M * GRID_M / 1_000_000.0),
            "cells_per_retained_center_after_union": float(union_count / retain_n) if retain_n else 0.0,
        }
    return {
        "cohort_unit_id": unit,
        "source_ready_candidate_count": int(len(ready)),
        "retained_coarse_center_count": retain_n,
        "support_fraction": SUPPORT_FRACTION,
        "radius_results": radius_results,
    }


def run_all(orders: dict[str, pd.DataFrame]) -> dict[str, Any]:
    _validate_contracts()
    if set(orders) != set(UNITS):
        raise ValueError("unit set drifted")
    geometry = fetch_geoboundaries_country_geometry("JP")
    outer, summary = build_fresh_sentinel_v2_outer_frame(geometry)
    if int(summary["candidate_count"]) != EXPECTED_CANDIDATES:
        raise ValueError("outer-frame candidate count drifted")
    unit_results = {unit: audit_unit(orders[unit], outer, unit) for unit in UNITS}
    return {
        "schema_version": "cirsium-fresh-sentinel-v2-local-refinement-size-audit-result-v1",
        "status": "LOCAL_REFINEMENT_SIZE_AUDIT_COMPLETE_PRE_OUTCOME",
        "support_fraction": SUPPORT_FRACTION,
        "grid_spacing_m": GRID_M,
        "primary_radius_km": 2.0,
        "sensitivity_radius_km": 5.0,
        "unit_results": unit_results,
        "source_indeterminate_included": False,
        "fine_ecological_score_computed": False,
        "patch_count_computed": False,
        "recovery_computed": False,
        "field_outcomes_opened": False,
        "access_or_budget_used": False,
        "promotion_gate": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order", action="append", required=True, help="UNIT=path.csv.gz")
    parser.add_argument("--out-json", type=Path, required=True)
    args = parser.parse_args()
    orders = {}
    for spec in args.order:
        unit, path = spec.split("=", 1)
        orders[unit] = pd.read_csv(path, low_memory=False)
    result = run_all(orders)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
