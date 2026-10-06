#!/usr/bin/env python3
"""Audit ESA WorldCover availability on fresh-SENTINEL v2 primary fine grids.

Coordinate-bearing output remains private. Every primary fine-grid row is retained
with one explicit WorldCover source state. Source-complete rows receive the
already-frozen 250-m neighbourhood fractions; unavailable rows remain
indeterminate and are never recoded as ecological zero or biological absence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from acsp.discovery.providers.worldcover_neighborhood_points import (
    FEATURE_COLUMNS,
    audit_worldcover_neighbourhood_availability_blocked,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_v2_fine_worldcover_availability_v1.json"
REQUIRED_UNITS = ("CIR02", "CIR12", "CIR13")


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


def _load_contract() -> dict[str, Any]:
    value = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if value.get("status") != "FROZEN_BEFORE_FINE_WORLDCOVER_AVAILABILITY_AUDIT":
        raise ValueError("fine WorldCover availability contract is not frozen")
    if tuple(value.get("required_units") or ()) != REQUIRED_UNITS:
        raise ValueError("fine WorldCover required-unit set drifted")
    provider = value.get("provider") or {}
    if provider.get("identity") != "ESA_WORLDCOVER" or provider.get("release") != "2021_v200":
        raise ValueError("WorldCover provider identity/release drifted")
    if float(provider.get("neighbourhood_radius_m")) != 250.0:
        raise ValueError("WorldCover neighbourhood radius drifted")
    if int(provider.get("blocked_pixel_chunk")) != 2048:
        raise ValueError("blocked WorldCover transport chunk drifted")
    if value.get("candidate_denominator", {}).get("preserve_all_primary_fine_grid_rows") is not True:
        raise ValueError("fine WorldCover denominator-preservation rule drifted")
    return value


def audit_unit(
    fine_grid: pd.DataFrame,
    *,
    unit_id: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    contract = _load_contract()
    if unit_id not in REQUIRED_UNITS:
        raise ValueError(f"unit has no frozen fine WorldCover dependency: {unit_id}")
    required = {
        "candidate_cell_id",
        "cohort_unit_id",
        "grid_row",
        "grid_col",
        "latitude",
        "longitude",
    }
    missing = sorted(required.difference(fine_grid.columns))
    if missing:
        raise ValueError(f"primary fine grid missing columns: {missing}")
    if fine_grid.empty:
        raise ValueError("primary fine grid cannot be empty")
    if set(fine_grid["cohort_unit_id"].astype(str)) != {unit_id}:
        raise ValueError("primary fine-grid unit identity drifted")
    if fine_grid["candidate_cell_id"].astype(str).duplicated().any():
        raise ValueError("primary fine-grid candidate IDs must be unique")

    provider = contract["provider"]
    audited, audit = audit_worldcover_neighbourhood_availability_blocked(
        fine_grid,
        radius_m=float(provider["neighbourhood_radius_m"]),
        block_pixels=int(provider["blocked_pixel_chunk"]),
    )
    if len(audited) != len(fine_grid):
        raise AssertionError("WorldCover availability audit changed candidate denominator")
    if audited["candidate_cell_id"].astype(str).tolist() != fine_grid["candidate_cell_id"].astype(str).tolist():
        raise AssertionError("WorldCover availability audit changed candidate identity/order")

    state_counts = (
        audited["worldcover_source_state"].astype(str).value_counts(sort=False).sort_index().to_dict()
    )
    expected_states = set(contract["candidate_denominator"]["source_states"])
    if not set(state_counts).issubset(expected_states):
        raise ValueError(f"unexpected fine WorldCover source state: {state_counts}")

    complete = audited["worldcover_source_state"].astype(str).eq("SOURCE_COMPLETE")
    if complete.any() and audited.loc[complete, list(FEATURE_COLUMNS)].isna().any().any():
        raise AssertionError("source-complete WorldCover rows have missing frozen features")
    if (~complete).any() and audited.loc[~complete, list(FEATURE_COLUMNS)].notna().any().any():
        raise AssertionError("source-indeterminate WorldCover rows must not carry partial feature values")

    summary = {
        "schema_version": "cirsium-fresh-sentinel-v2-fine-worldcover-availability-result-v1",
        "status": "FINE_WORLDCOVER_AVAILABILITY_AUDITED_PRE_OUTCOME",
        "cohort_unit_id": unit_id,
        "candidate_rows": int(len(audited)),
        "source_complete_rows": int(audit.source_complete_rows),
        "source_complete_fraction": float(audit.source_complete_rows / len(audited)),
        "neighbourhood_unavailable_rows": int(audit.neighbourhood_unavailable_rows),
        "provider_failure_rows": int(audit.provider_failure_rows),
        "provider_failure_tile_ids": list(audit.provider_failure_tile_ids),
        "source_tile_ids": list(audit.source_tile_ids),
        "source_complete_feature_digest_sha256": audit.source_complete_feature_digest_sha256,
        "worldcover_neighbourhood_radius_m": float(audit.neighbourhood_radius_m),
        "worldcover_release": audit.release_id,
        "candidate_denominator_preserved": True,
        "source_indeterminate_recoded_as_absence": False,
        "source_indeterminate_recoded_as_zero_support": False,
        "field_outcomes_opened": False,
        "human_access_used": False,
        "structural_graph_computed": False,
        "candidate_ranking_computed": False,
        "exact_coordinates_public": False,
        "next_gate": (
            "Freeze this source-completeness receipt. Structural raw-layer construction may use only SOURCE_COMPLETE rows; "
            "source-indeterminate rows remain retained separately."
        ),
    }
    return audited, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-id", choices=REQUIRED_UNITS, required=True)
    parser.add_argument("--fine-grid-csv-gz", type=Path, required=True)
    parser.add_argument("--private-out-csv-gz", type=Path, required=True)
    parser.add_argument("--public-safe-summary-json", type=Path, required=True)
    args = parser.parse_args()

    if not args.fine_grid_csv_gz.is_file():
        raise SystemExit(f"missing primary fine grid: {args.fine_grid_csv_gz}")
    if _inside_repo(args.private_out_csv_gz):
        raise SystemExit("refusing to write coordinate-bearing fine WorldCover output inside repository")
    if args.private_out_csv_gz.exists() or args.public_safe_summary_json.exists():
        raise SystemExit("refusing to overwrite fine WorldCover audit outputs")

    fine_grid = pd.read_csv(args.fine_grid_csv_gz, low_memory=False)
    audited, summary = audit_unit(fine_grid, unit_id=args.unit_id)
    args.private_out_csv_gz.parent.mkdir(parents=True, exist_ok=True)
    args.public_safe_summary_json.parent.mkdir(parents=True, exist_ok=True)
    audited.to_csv(
        args.private_out_csv_gz,
        index=False,
        compression={"method": "gzip", "mtime": 0},
    )
    summary["private_audited_frame_sha256"] = _sha256(args.private_out_csv_gz)
    args.public_safe_summary_json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
