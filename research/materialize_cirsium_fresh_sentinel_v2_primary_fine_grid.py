#!/usr/bin/env python3
"""Materialize the frozen fresh-SENTINEL v2 primary 2-km / 100-m fine grid.

The geometry rule is not reimplemented here. It reuses the exact cell-generation
semantics from the already-frozen local-refinement size audit, then materializes
the unioned cells as one shared integer grid per unit. Coordinate-bearing outputs
must remain outside the public repository.

No ecological source, structural score, access, budget or field outcome is read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pyproj import CRS, Transformer

from acsp.global_geometry import fetch_geoboundaries_country_geometry
from research.audit_cirsium_fresh_sentinel_v2_local_refinement_size import (
    GRID_M,
    PROJ_STRING,
    READY,
    SUPPORT_FRACTION,
    _cell_set_for_center,
)
from research.build_cirsium_fresh_sentinel_public_broad_frame_v2 import (
    build_fresh_sentinel_v2_outer_frame,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_v2_primary_fine_grid_v1.json"
SIZE_RESULT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_v2_local_refinement_size_audit_result_v1.json"
UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
EXPECTED_CANDIDATES = 39200
PRIMARY_RADIUS_KM = 2.0


def _inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT.resolve())
        return True
    except ValueError:
        return False


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _load_contracts() -> tuple[dict[str, Any], dict[str, Any]]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    size_result = json.loads(SIZE_RESULT.read_text(encoding="utf-8"))
    if contract.get("status") != "FROZEN_BEFORE_PRIMARY_FINE_GRID_MATERIALIZATION":
        raise ValueError("primary fine-grid contract is not frozen")
    if size_result.get("status") != "PRIMARY_2KM_LOCAL_REFINEMENT_GEOMETRY_FEASIBLE":
        raise ValueError("local-refinement size result is not frozen as feasible")
    if float(contract["coarse_center_rule"]["support_fraction"]) != SUPPORT_FRACTION:
        raise ValueError("support fraction drifted")
    if float(contract["fine_grid"]["radius_km"]) != PRIMARY_RADIUS_KM:
        raise ValueError("primary radius drifted")
    if float(contract["fine_grid"]["grid_spacing_m"]) != GRID_M:
        raise ValueError("grid spacing drifted")
    if contract["fine_grid"]["proj_string"] != PROJ_STRING:
        raise ValueError("projection drifted")
    return contract, size_result


def _transformers() -> tuple[Transformer, Transformer]:
    crs = CRS.from_proj4(PROJ_STRING)
    return (
        Transformer.from_crs("EPSG:4326", crs, always_xy=True),
        Transformer.from_crs(crs, "EPSG:4326", always_xy=True),
    )


def _restore_centers(order: pd.DataFrame, outer: pd.DataFrame, unit: str) -> pd.DataFrame:
    if len(order) != EXPECTED_CANDIDATES:
        raise ValueError(f"{unit} production coarse order must contain 39,200 rows")
    if len(outer) != EXPECTED_CANDIDATES:
        raise ValueError("frozen Japan outer frame must contain 39,200 rows")

    ready = order.loc[order["source_state"].astype(str).eq(READY)].copy()
    ready["coarse_evidence_rank"] = pd.to_numeric(
        ready["coarse_evidence_rank"], errors="raise"
    ).astype(int)
    ready = ready.sort_values("coarse_evidence_rank", kind="mergesort").reset_index(drop=True)
    if ready["coarse_evidence_rank"].tolist() != list(range(1, len(ready) + 1)):
        raise ValueError(f"{unit} source-ready coarse order is not complete")

    retain_n = int(math.ceil(SUPPORT_FRACTION * len(ready)))
    retained = ready.iloc[:retain_n].copy()
    coords = outer.set_index(outer["candidate_cell_id"].astype(str))[
        ["latitude", "longitude"]
    ]
    retained.index = retained["candidate_cell_id"].astype(str)
    retained = retained.join(coords, how="left").reset_index(drop=True)
    if retained[["latitude", "longitude"]].isna().any().any():
        raise ValueError(f"{unit} failed to restore frozen coarse-center coordinates")
    return retained


def materialize_unit_primary_fine_grid(
    order: pd.DataFrame,
    outer: pd.DataFrame,
    unit: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    contract, size_result = _load_contracts()
    if unit not in UNITS:
        raise ValueError(f"unknown fresh-SENTINEL v2 unit: {unit}")

    centers = _restore_centers(order, outer, unit)
    forward, inverse = _transformers()
    xs, ys = forward.transform(
        pd.to_numeric(centers["longitude"], errors="raise").to_numpy(float),
        pd.to_numeric(centers["latitude"], errors="raise").to_numpy(float),
    )

    union: set[tuple[int, int]] = set()
    raw_memberships = 0
    radius_m = PRIMARY_RADIUS_KM * 1000.0
    for x, y in zip(xs, ys):
        cells = _cell_set_for_center(float(x), float(y), radius_m)
        raw_memberships += len(cells)
        union.update(cells)

    ordered = sorted(union)
    rows = np.asarray([row for row, _ in ordered], dtype=np.int64)
    cols = np.asarray([col for _, col in ordered], dtype=np.int64)
    center_x = (cols.astype(float) + 0.5) * GRID_M
    center_y = (rows.astype(float) + 0.5) * GRID_M
    longitude, latitude = inverse.transform(center_x, center_y)

    frame = pd.DataFrame(
        {
            "cohort_unit_id": unit,
            "grid_row": rows,
            "grid_col": cols,
            "projected_x_m": center_x,
            "projected_y_m": center_y,
            "longitude": np.asarray(longitude, dtype=float),
            "latitude": np.asarray(latitude, dtype=float),
        }
    )
    frame.insert(
        1,
        "candidate_cell_id",
        [f"{unit}_r{int(r)}_c{int(c)}" for r, c in zip(rows, cols)],
    )
    frame["primary_local_radius_km"] = PRIMARY_RADIUS_KM
    frame["grid_spacing_m"] = GRID_M
    frame["source_ready_coarse_center_fraction"] = SUPPORT_FRACTION

    if frame["candidate_cell_id"].duplicated().any():
        raise AssertionError("candidate_cell_id must be unique")
    if frame[["grid_row", "grid_col"]].duplicated().any():
        raise AssertionError("grid_row/grid_col pairs must be unique")

    expected = int(contract["expected_unit_cell_counts_from_frozen_audit"][unit])
    frozen = int(
        size_result["unit_results"][unit]["primary_2km"]["unioned_100m_cells"]
    )
    if expected != frozen:
        raise ValueError(f"{unit} contract/result expected-cell count mismatch")
    if len(frame) != expected:
        raise ValueError(
            f"{unit} primary fine-grid row count drifted: expected {expected}, got {len(frame)}"
        )

    summary = {
        "schema_version": "cirsium-fresh-sentinel-v2-primary-fine-grid-unit-v1",
        "status": "PRIMARY_2KM_100M_FINE_GRID_MATERIALIZED_PRE_OUTCOME",
        "cohort_unit_id": unit,
        "source_ready_candidate_count": int(
            order["source_state"].astype(str).eq(READY).sum()
        ),
        "retained_coarse_center_count": int(len(centers)),
        "support_fraction": SUPPORT_FRACTION,
        "primary_radius_km": PRIMARY_RADIUS_KM,
        "grid_spacing_m": GRID_M,
        "fine_grid_cell_count": int(len(frame)),
        "raw_center_cell_memberships": int(raw_memberships),
        "overlap_memberships_removed": int(raw_memberships - len(frame)),
        "projection_identity": contract["fine_grid"]["projection_identity"],
        "source_indeterminate_included": False,
        "ecological_sources_attached": False,
        "structural_graph_computed": False,
        "candidate_ranking_computed": False,
        "field_outcomes_opened": False,
        "access_or_budget_used": False,
        "exact_coordinates_public": False,
        "next_gate": "Attach frozen family-specific public ecological primitives to this private fine grid before G_E_LOCAL_GRID_V1.",
    }
    return frame, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-id", choices=UNITS, required=True)
    parser.add_argument("--order-csv-gz", type=Path, required=True)
    parser.add_argument("--private-out-csv-gz", type=Path, required=True)
    parser.add_argument("--public-safe-summary-json", type=Path, required=True)
    args = parser.parse_args()

    if _inside_repo(args.private_out_csv_gz):
        raise SystemExit("refusing to write coordinate-bearing primary fine grid inside repository")
    if args.private_out_csv_gz.exists() or args.public_safe_summary_json.exists():
        raise SystemExit("refusing to overwrite primary fine-grid outputs")

    order = pd.read_csv(args.order_csv_gz, low_memory=False)
    geometry = fetch_geoboundaries_country_geometry("JP")
    outer, outer_summary = build_fresh_sentinel_v2_outer_frame(geometry)
    if int(outer_summary["candidate_count"]) != EXPECTED_CANDIDATES:
        raise ValueError("frozen Japan outer frame candidate count drifted")

    frame, summary = materialize_unit_primary_fine_grid(order, outer, args.unit_id)
    args.private_out_csv_gz.parent.mkdir(parents=True, exist_ok=True)
    args.public_safe_summary_json.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(
        args.private_out_csv_gz,
        index=False,
        compression={"method": "gzip", "mtime": 0},
    )
    summary["private_grid_sha256"] = _sha256(args.private_out_csv_gz)
    args.public_safe_summary_json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
