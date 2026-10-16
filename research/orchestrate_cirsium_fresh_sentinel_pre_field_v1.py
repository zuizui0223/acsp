#!/usr/bin/env python3
"""Run the frozen fresh-SENTINEL pre-field pipeline from one private geometry bundle.

This is an execution adapter only. It consumes the already-frozen four-unit
private range-sector bundle and advances each unit through:

private sector -> frozen public sources -> 100 m raw grid -> source manifest ->
private structural candidate frame -> 5 km coarse coverage cells -> three frozen
pre-field orders.

The three orders are:
1. COVERAGE_THEN_FINE_STRUCTURE_V1;
2. coverage-only round-robin with stable within-cell order;
3. MORTON_DYADIC_COVERAGE_ORDER_V1 on the full fine grid.

No field outcome, access, route, permission, day, budget, or post-outcome tuning is
read. Coordinate-bearing outputs are refused inside the git repository. If any
frozen unit fails, execution stops without replacement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from acsp.discovery.comparators import rank_morton_dyadic_spatial_balance
from acsp.discovery.scale_separated import rank_coverage_then_fine_structure
from research.build_cirsium_private_sector_structural_grid_v1 import build_sector_structural_raw_grid
from research.build_cirsium_private_source_manifest_v1 import build_manifest
from research.build_cirsium_private_uncertainty_sentinel_grid_v1 import build_uncertainty_sentinel_raw_grid
from research.materialize_cirsium_fresh_sentinel_public_sources_v1 import materialize_public_sources
from research.prepare_cirsium_private_candidate_frame_v1 import build_private_candidate_frame
from research.validate_cirsium_fresh_range_sector_bundle_v1 import EXPECTED_UNITS, split_private_bundle

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "validation" / "cirsium_private_frame_source_requirements_v1.csv"
COHORT = ROOT / "validation" / "cirsium_aza3_prospective_validation_cohort_v1.csv"
FINE_SPACING_M = 100
COARSE_COVERAGE_CELL_SIZE_M = 5000
GRAPH_RADIUS_CELLS = 1
UNCERTAINTY_UNITS = {"CIR02", "CIR12"}
COVERAGE_ONLY_METHOD = "COVERAGE_ONLY_STABLE_WITHIN_CELL_V1"


def _inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT.resolve())
        return True
    except ValueError:
        return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stable_hash(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def attach_frozen_coarse_coverage(
    frame: pd.DataFrame,
    *,
    fine_spacing_m: int = FINE_SPACING_M,
    coarse_cell_size_m: int = COARSE_COVERAGE_CELL_SIZE_M,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Attach outcome-blind 5-km cells and a Morton-dyadic cell order."""
    fine = int(fine_spacing_m)
    coarse = int(coarse_cell_size_m)
    if fine <= 0 or coarse <= 0 or coarse % fine != 0:
        raise ValueError("coarse coverage cell size must be a positive integer multiple of fine spacing")
    factor = coarse // fine
    required = {"candidate_cell_id", "latitude", "longitude", "grid_row", "grid_col", "structural_support"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"private candidate frame missing coverage columns: {missing}")

    work = frame.copy().reset_index(drop=True)
    for column in ("grid_row", "grid_col"):
        numeric = pd.to_numeric(work[column], errors="coerce").to_numpy(float)
        if not np.isfinite(numeric).all() or not np.allclose(numeric, np.rint(numeric)):
            raise ValueError(f"{column} must be complete and integer-valued")
        work[column] = np.rint(numeric).astype(np.int64)
    if (work[["grid_row", "grid_col"]] < 0).any().any():
        raise ValueError("fresh private grids must use non-negative local grid indices")

    work["coverage_grid_row"] = (work["grid_row"] // factor).astype(np.int64)
    work["coverage_grid_col"] = (work["grid_col"] // factor).astype(np.int64)
    work["coverage_cell_id"] = [
        f"cov_r{int(row)}_c{int(col)}"
        for row, col in zip(work["coverage_grid_row"], work["coverage_grid_col"])
    ]

    cells = (
        work.groupby("coverage_cell_id", as_index=False, sort=True)
        .agg(
            latitude=("latitude", "mean"),
            longitude=("longitude", "mean"),
            grid_row=("coverage_grid_row", "first"),
            grid_col=("coverage_grid_col", "first"),
        )
    )
    ranked_cells, cell_audit = rank_morton_dyadic_spatial_balance(
        cells,
        candidate_id_col="coverage_cell_id",
        grid_row_col=("grid_row", "grid_col"),
    )
    rank_map = dict(zip(ranked_cells["coverage_cell_id"].astype(str), ranked_cells["decision_rank"].astype(int)))
    work["coverage_rank"] = work["coverage_cell_id"].map(rank_map).astype(np.int64)
    if sorted(work.groupby("coverage_cell_id")["coverage_rank"].first().tolist()) != list(range(1, len(cells) + 1)):
        raise AssertionError("coverage-cell ranks are not a complete 1..N order")

    audit = {
        "method": "MORTON_DYADIC_COVERAGE_ORDER_V1",
        "fine_spacing_m": fine,
        "coarse_coverage_cell_size_m": coarse,
        "fine_cells_per_coarse_axis": factor,
        "candidate_count": int(len(work)),
        "coverage_cell_count": int(len(cells)),
        "cell_order_audit": cell_audit.__dict__,
        "field_outcomes_used": False,
        "human_access_used": False,
        "budget_used": False,
    }
    return work, audit


def rank_coverage_only_round_robin(frame: pd.DataFrame) -> pd.DataFrame:
    """Freeze the nonstructural within-cell comparator on the same coarse cells."""
    required = {"candidate_cell_id", "coverage_cell_id", "coverage_rank"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"coverage-only comparator missing columns: {missing}")
    work = frame.copy().reset_index(drop=True)
    if work["candidate_cell_id"].isna().any() or work["candidate_cell_id"].astype(str).duplicated().any():
        raise ValueError("candidate_cell_id must be complete and unique")
    work["_stable_hash"] = [_stable_hash(value) for value in work["candidate_cell_id"]]
    work = work.sort_values(["coverage_cell_id", "_stable_hash"], kind="mergesort")
    work["within_cell_nonstructural_rank"] = (
        work.groupby("coverage_cell_id", sort=False).cumcount() + 1
    ).astype(np.int64)
    ordered = (
        work.sort_values(
            ["within_cell_nonstructural_rank", "coverage_rank", "_stable_hash"],
            kind="mergesort",
        )
        .drop(columns="_stable_hash")
        .reset_index(drop=True)
    )
    ordered["decision_method"] = COVERAGE_ONLY_METHOD
    ordered["decision_rank"] = range(1, len(ordered) + 1)
    return ordered


def freeze_pre_field_orders(frame: pd.DataFrame) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    covered, coverage_audit = attach_frozen_coarse_coverage(frame)
    structural, structural_audit = rank_coverage_then_fine_structure(covered)
    coverage_only = rank_coverage_only_round_robin(covered)
    spatial, spatial_audit = rank_morton_dyadic_spatial_balance(covered)
    orders = {
        "coverage_then_fine_structure": structural,
        "coverage_only": coverage_only,
        "fine_spatial_balance": spatial,
    }
    audit = {
        "coverage": coverage_audit,
        "coverage_then_fine_structure": structural_audit.__dict__,
        "coverage_only_method": COVERAGE_ONLY_METHOD,
        "fine_spatial_balance": spatial_audit.__dict__,
        "same_candidate_frame": True,
        "field_outcomes_used": False,
        "fitted_weights_used": False,
        "budget_used": False,
        "human_access_used": False,
    }
    return orders, audit


def _path_from_materialization(summary: dict[str, Any], key: str) -> Path | None:
    record = summary.get("outputs", {}).get(key)
    if not record:
        return None
    return Path(str(record["path"]))


def run_private_pre_field_pipeline(bundle_geojson: Path, private_root: Path) -> dict[str, Any]:
    private_root = private_root.resolve()
    if _inside_repo(private_root):
        raise ValueError("private orchestration root must be outside the git repository")
    if private_root.exists():
        raise ValueError("private orchestration root must not already exist")
    private_root.mkdir(parents=True)

    requirements = pd.read_csv(REQUIREMENTS)
    cohort = pd.read_csv(COHORT)
    req = requirements.set_index("cohort_unit_id")
    coh = cohort.set_index("cohort_unit_id")
    if tuple(EXPECTED_UNITS) != ("CIR02", "CIR06", "CIR12", "CIR13"):
        raise AssertionError("fresh SENTINEL unit set drifted")
    if any(str(coh.loc[unit, "outcome_opened"]).strip().lower() != "false" for unit in EXPECTED_UNITS):
        raise ValueError("fresh SENTINEL field outcome is no longer unopened")

    sector_dir = private_root / "range-sectors"
    split = split_private_bundle(bundle_geojson, sector_dir)
    units: dict[str, Any] = {}
    try:
        for unit_id in EXPECTED_UNITS:
            unit_dir = private_root / unit_id
            source_dir = unit_dir / "sources"
            unit_dir.mkdir(parents=True, exist_ok=False)
            sector = sector_dir / f"{unit_id}_range_sector.geojson"
            family = str(req.loc[unit_id, "structural_feature_family"])

            materialization = materialize_public_sources(unit_id, sector, source_dir)
            dem = _path_from_materialization(materialization, "gsi_dem")
            wc = _path_from_materialization(materialization, "worldcover")
            sentinel = _path_from_materialization(materialization, "sentinel_evidence")
            if dem is None:
                raise RuntimeError(f"{unit_id} did not materialize required GSI DEM")

            raw_csv = unit_dir / "raw_grid.csv"
            raw_summary_json = unit_dir / "raw_grid_summary.json"
            if unit_id in UNCERTAINTY_UNITS:
                if sentinel is None or wc is None:
                    raise RuntimeError(f"{unit_id} uncertainty-footprint sources are incomplete")
                raw, raw_summary = build_uncertainty_sentinel_raw_grid(
                    sector,
                    sentinel,
                    dem,
                    wc,
                    unit_id=unit_id,
                )
            else:
                raw, raw_summary = build_sector_structural_raw_grid(
                    sector,
                    dem,
                    unit_id=unit_id,
                    feature_family=family,
                    worldcover=wc,
                )
            raw.to_csv(raw_csv, index=False)
            _write_json(raw_summary_json, raw_summary)

            manifest = build_manifest(
                requirements,
                cohort,
                unit_id=unit_id,
                range_sector_file=sector,
                raw_grid_file=raw_csv,
                sentinel_evidence_file=sentinel,
                gsi_dem_files=(dem,),
                worldcover_files=(wc,) if wc is not None else (),
            )
            manifest_json = unit_dir / "source_manifest.json"
            _write_json(manifest_json, manifest)

            private_frame, frame_summary = build_private_candidate_frame(
                raw,
                feature_family=family,
                source_manifest=manifest,
                graph_radius_cells=GRAPH_RADIUS_CELLS,
            )
            orders, order_audit = freeze_pre_field_orders(private_frame)
            method_columns = ["within_cell_structure_rank", "decision_method", "decision_rank"]
            covered_frame = (
                orders["coverage_then_fine_structure"]
                .drop(columns=[column for column in method_columns if column in orders["coverage_then_fine_structure"].columns])
                .sort_values("candidate_cell_id")
                .reset_index(drop=True)
            )
            candidate_frame_csv = unit_dir / "candidate_frame_pre_field.csv"
            frame_summary_json = unit_dir / "candidate_frame_summary.json"
            covered_frame.to_csv(candidate_frame_csv, index=False)
            _write_json(frame_summary_json, frame_summary)

            order_paths: dict[str, str] = {}
            order_hashes: dict[str, str] = {}
            for name, ordered in orders.items():
                path = unit_dir / f"order_{name}.csv"
                ordered.to_csv(path, index=False)
                order_paths[name] = path.name
                order_hashes[name] = _sha256(path)

            unit_receipt = {
                "schema_version": "cirsium-fresh-sentinel-pre-field-unit-freeze-v1",
                "status": "PRE_FIELD_METHOD_AND_COMPARATORS_FROZEN",
                "cohort_unit_id": unit_id,
                "species_binomial": str(req.loc[unit_id, "species_binomial"]),
                "feature_family": family,
                "raw_grid_sha256": _sha256(raw_csv),
                "source_manifest_sha256": _sha256(manifest_json),
                "candidate_frame_sha256": _sha256(candidate_frame_csv),
                "order_files": order_paths,
                "order_sha256": order_hashes,
                "order_audit": order_audit,
                "field_outcomes_opened": False,
                "human_access_used": False,
                "replacement_taxon_allowed": False,
                "retuning_after_failure_allowed": False,
                "public_hash_receipt_committed": False,
            }
            receipt_json = unit_dir / "pre_field_freeze_receipt.json"
            _write_json(receipt_json, unit_receipt)
            units[unit_id] = unit_receipt
    except Exception as exc:
        failure = {
            "schema_version": "cirsium-fresh-sentinel-pre-field-orchestration-v1",
            "status": "PRE_FIELD_PIPELINE_FAILED_NO_REPLACEMENT",
            "completed_units": list(units),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "field_outcomes_opened": False,
            "replacement_taxon_attempted": False,
        }
        _write_json(private_root / "orchestration_failure.json", failure)
        raise

    receipt = {
        "schema_version": "cirsium-fresh-sentinel-pre-field-orchestration-v1",
        "status": "ALL_FOUR_PRE_FIELD_METHOD_AND_COMPARATORS_FROZEN",
        "units": list(EXPECTED_UNITS),
        "bundle_summary_status": split["status"],
        "fine_candidate_spacing_m": FINE_SPACING_M,
        "coarse_coverage_cell_size_m": COARSE_COVERAGE_CELL_SIZE_M,
        "graph_radius_cells": GRAPH_RADIUS_CELLS,
        "method_identity": "COVERAGE_THEN_FINE_STRUCTURE_V1",
        "coverage_identity": "MORTON_DYADIC_COVERAGE_ORDER_V1",
        "coverage_only_comparator": COVERAGE_ONLY_METHOD,
        "fine_spatial_comparator": "MORTON_DYADIC_COVERAGE_ORDER_V1",
        "unit_receipts": {
            unit: {
                "candidate_frame_sha256": units[unit]["candidate_frame_sha256"],
                "order_sha256": units[unit]["order_sha256"],
            }
            for unit in EXPECTED_UNITS
        },
        "field_outcomes_opened": False,
        "human_access_used": False,
        "budget_used": False,
        "replacement_taxon_allowed": False,
        "public_hash_receipt_committed": False,
        "ready_for_public_hash_receipt_freeze": True,
        "ready_for_future_prospective_outcome_opening": False,
        "next_gate": "Export, commit and pin the coordinate-free public hash receipt before any prospective outcome-opening workflow is authorized.",
    }
    _write_json(private_root / "pre_field_freeze_receipt.json", receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-geojson", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    args = parser.parse_args()
    receipt = run_private_pre_field_pipeline(args.bundle_geojson, args.private_root)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
