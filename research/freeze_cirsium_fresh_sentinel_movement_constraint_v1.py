#!/usr/bin/env python3
"""Create the one allowed human movement constraint before private geometry is opened.

The fresh-SENTINEL field protocol permits one operational input: the maximum
network transition distance a field team can traverse between candidate areas.
This declaration is public-safe and contains no candidate identities or coordinates.
It must be committed and immutably pinned before private range-sector geometry is
processed.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from research.cirsium_fresh_sentinel_paths_v1 import (
    CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH,
    require_canonical_repo_path,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "cirsium-fresh-sentinel-movement-constraint-v1"
STATUS = "PRE_GEOMETRY_MOVEMENT_CONSTRAINT_FROZEN"
SOURCE_IDENTITY = "USER_DECLARED_HUMAN_NETWORK_TRANSITION_LIMIT_V1"


def _positive_finite_float(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{label} must be finite and >0")
    return number


def build_movement_constraint(max_network_transition_km: float) -> dict[str, Any]:
    movement_km = _positive_finite_float(
        max_network_transition_km,
        "max_network_transition_km",
    )
    return {
        "schema_version": SCHEMA,
        "status": STATUS,
        "source_identity": SOURCE_IDENTITY,
        "movement_constraint_mode": "osm_weighted_transport_network",
        "max_network_transition_km": movement_km,
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
    max_network_transition_km: float,
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
    value = build_movement_constraint(max_network_transition_km)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-network-transition-km", type=float, required=True)
    parser.add_argument(
        "--out-json",
        type=Path,
        default=Path(CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH),
    )
    args = parser.parse_args()
    value = freeze_movement_constraint(
        args.max_network_transition_km,
        out_json=args.out_json,
    )
    print(json.dumps({
        "status": value["status"],
        "max_network_transition_km": value["max_network_transition_km"],
        "out_json": str(args.out_json),
        "prospective_field_outcomes_opened": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
