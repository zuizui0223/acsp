#!/usr/bin/env python3
"""Freeze the deterministic pre-geometry movement constraint for fresh-SENTINEL.

Fresh-SENTINEL no longer asks the user to choose a movement-distance parameter.
The only operational movement scale is derived outcome-blind from the already
frozen 5-km coarse coverage scale used by COVERAGE_THEN_FINE_STRUCTURE_V1.

This value is downstream G_F only. It does not alter ecological support, candidate
membership, arm ranking, field effort, survey days, monetary budget, or outcomes.
The canonical declaration must be committed and immutably pinned before private
range-sector geometry is processed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from research.cirsium_fresh_sentinel_paths_v1 import (
    CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH,
    require_canonical_repo_path,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "cirsium-fresh-sentinel-movement-constraint-v1"
STATUS = "PRE_GEOMETRY_MOVEMENT_CONSTRAINT_FROZEN"
SOURCE_IDENTITY = "ALGORITHM_DERIVED_NETWORK_TRANSITION_LIMIT_V1"
DERIVATION_IDENTITY = "MATCH_FROZEN_COARSE_COVERAGE_SCALE_V1"
FROZEN_COARSE_COVERAGE_CELL_SIZE_M = 5000.0
ALGORITHM_DERIVED_MAX_NETWORK_TRANSITION_KM = (
    FROZEN_COARSE_COVERAGE_CELL_SIZE_M / 1000.0
)


def build_movement_constraint() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA,
        "status": STATUS,
        "source_identity": SOURCE_IDENTITY,
        "derivation_identity": DERIVATION_IDENTITY,
        "movement_constraint_mode": "osm_weighted_transport_network",
        "max_network_transition_km": ALGORITHM_DERIVED_MAX_NETWORK_TRANSITION_KM,
        "derived_from_coarse_coverage_cell_size_m": FROZEN_COARSE_COVERAGE_CELL_SIZE_M,
        "user_declared_value": False,
        "private_range_sector_geometry_opened_when_declared": False,
        "candidate_identity_used_to_set_constraint": False,
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used_to_set_constraint": False,
        "survey_days_input": False,
        "monetary_budget_input": False,
        "user_site_count_input": False,
        "user_coverage_target_input": False,
        "post_geometry_edits_allowed": False,
        "post_outcome_edits_allowed": False,
    }


def freeze_movement_constraint(
    *,
    out_json: Path = Path(CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH),
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    out_path = require_canonical_repo_path(
        Path(out_json),
        repo_root=repo,
        expected_repo_path=CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH,
        label="movement constraint protocol",
    )
    if out_path.exists():
        raise ValueError("refusing to overwrite the canonical movement constraint")
    value = build_movement_constraint()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-json",
        type=Path,
        default=Path(CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH),
    )
    args = parser.parse_args()
    value = freeze_movement_constraint(out_json=args.out_json)
    print(json.dumps({
        "status": value["status"],
        "max_network_transition_km": value["max_network_transition_km"],
        "derivation_identity": value["derivation_identity"],
        "out_json": str(args.out_json),
        "prospective_field_outcomes_opened": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
