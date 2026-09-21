#!/usr/bin/env python3
"""Advance the fresh-SENTINEL prospective protocol by exactly one legal state transition.

This is a state-aware front door for the frozen Cirsium fresh-SENTINEL workflow.
It never opens prospective field outcomes. The canonical standardized effort
protocol must already be immutably pinned before private range-sector geometry is
processed. Public candidate/order and field-schedule receipts still require real
Git commits between stages; this command never creates those commits itself.

The only scientific/operational value that can be declared through this front door
is the maximum network transition distance. It is written once to a canonical
public-safe protocol, must be immutably pinned before private geometry is processed,
and is then read from that pinned protocol. File paths identify artifacts only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from research.build_cirsium_fresh_sentinel_private_field_schedule_v1 import (
    build_private_field_schedule,
)
from research.cirsium_fresh_sentinel_paths_v1 import (
    CANONICAL_ANALYSIS_PLAN_REPO_PATH,
    CANONICAL_CANDIDATE_RECEIPT_REPO_PATH,
    CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH,
    CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH,
    CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH,
    CANONICAL_OPERATIONAL_CAPACITY_PROFILE_REPO_PATH,
    CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH,
    CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH,
)
from research.derive_cirsium_fresh_sentinel_movement_capacity_v1 import (
    derive_operational_capacity_profile,
)
from research.freeze_cirsium_fresh_sentinel_movement_constraint_v1 import (
    freeze_movement_constraint,
)
from research.export_cirsium_fresh_sentinel_public_field_schedule_receipt_v1 import (
    build_public_field_schedule_receipt,
)
from research.run_cirsium_fresh_sentinel_freeze_v1 import run_full_pre_field_freeze
from research.verify_cirsium_fresh_sentinel_pre_outcome_gate_v1 import (
    verify_pre_outcome_gate,
)
from research.verify_cirsium_fresh_sentinel_public_field_schedule_pin_v1 import (
    verify_public_field_schedule_pin,
)
from research.verify_cirsium_fresh_sentinel_public_freeze_pin_v1 import (
    verify_public_freeze_pin,
)
from research.verify_cirsium_fresh_sentinel_standardized_effort_pin_v1 import (
    verify_standardized_effort_pin,
)
from research.verify_cirsium_fresh_sentinel_movement_constraint_pin_v1 import (
    verify_movement_constraint_pin,
)

ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def advance_pre_outcome_pipeline(
    private_pre_field_root: Path,
    *,
    max_network_transition_km: float | None = None,
    bundle_geojson: Path | None = None,
    private_schedule_path: Path | None = None,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    private_root = Path(private_pre_field_root).resolve()
    private_schedule = (
        Path(private_schedule_path).resolve()
        if private_schedule_path is not None
        else (private_root / "field_schedule_v1.json").resolve()
    )
    candidate = repo / CANONICAL_CANDIDATE_RECEIPT_REPO_PATH
    schedule_receipt = repo / CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH
    capacity = repo / CANONICAL_OPERATIONAL_CAPACITY_PROFILE_REPO_PATH
    effort = repo / CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH
    movement = repo / CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH
    evaluation = repo / CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH
    analysis_plan = repo / CANONICAL_ANALYSIS_PLAN_REPO_PATH
    field_log_template = repo / CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH

    # Both protocol pins must be satisfied before private geometry is read or constructed.
    effort_pin = verify_standardized_effort_pin(effort, repo_root=repo)

    if not movement.exists():
        if max_network_transition_km is None:
            return {
                "schema_version": "cirsium-fresh-sentinel-pre-outcome-advance-v1",
                "status": "BLOCKED_MOVEMENT_CONSTRAINT_DECLARATION",
                "standardized_effort_protocol_pin_commit": effort_pin["pin_commit"],
                "prospective_field_outcomes_opened": False,
                "outcome_opening_gate_satisfied": False,
                "next_required_input": "declare max_network_transition_km once before private geometry is opened",
            }
        movement_value = freeze_movement_constraint(
            max_network_transition_km,
            out_json=movement,
            repo_root=repo,
        )
        return {
            "schema_version": "cirsium-fresh-sentinel-pre-outcome-advance-v1",
            "status": "MOVEMENT_CONSTRAINT_READY_FOR_COMMIT",
            "standardized_effort_protocol_pin_commit": effort_pin["pin_commit"],
            "max_network_transition_km": movement_value["max_network_transition_km"],
            "public_paths_to_commit": [CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH],
            "prospective_field_outcomes_opened": False,
            "outcome_opening_gate_satisfied": False,
            "next_gate": "Commit the canonical movement constraint, then rerun before supplying private geometry.",
        }

    try:
        movement_pin = verify_movement_constraint_pin(movement, repo_root=repo)
    except ValueError as exc:
        return {
            "schema_version": "cirsium-fresh-sentinel-pre-outcome-advance-v1",
            "status": "MOVEMENT_CONSTRAINT_PIN_NOT_SATISFIED",
            "standardized_effort_protocol_pin_commit": effort_pin["pin_commit"],
            "movement_constraint_repo_path": CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH,
            "prospective_field_outcomes_opened": False,
            "outcome_opening_gate_satisfied": False,
            "pin_error": str(exc),
            "next_gate": "Commit the exact canonical movement constraint without modifying its bytes.",
        }

    movement_km = float(movement_pin["max_network_transition_km"])
    if max_network_transition_km is not None and float(max_network_transition_km) != movement_km:
        raise ValueError("requested movement constraint differs from the immutable pre-geometry movement constraint")

    if not candidate.exists():
        if private_root.exists():
            raise ValueError(
                "private pre-field root exists but canonical candidate receipt is absent; "
                "refusing to overwrite or infer recovery state"
            )
        if bundle_geojson is None:
            return {
                "schema_version": "cirsium-fresh-sentinel-pre-outcome-advance-v1",
                "status": "BLOCKED_PRIVATE_RANGE_SECTOR_GEOMETRY",
                "standardized_effort_protocol_pin_commit": effort_pin["pin_commit"],
                "movement_constraint_pin_commit": movement_pin["pin_commit"],
                "prospective_field_outcomes_opened": False,
                "next_required_input": "one private four-feature range-sector GeoJSON bundle",
            }
        result = run_full_pre_field_freeze(
            Path(bundle_geojson),
            private_root,
            candidate,
            repo_root=repo,
        )
        return {
            "schema_version": "cirsium-fresh-sentinel-pre-outcome-advance-v1",
            "status": "CANDIDATE_RECEIPT_READY_FOR_COMMIT",
            "freeze_status": result["status"],
            "standardized_effort_protocol_pin_commit": effort_pin["pin_commit"],
            "movement_constraint_pin_commit": movement_pin["pin_commit"],
            "public_paths_to_commit": [CANONICAL_CANDIDATE_RECEIPT_REPO_PATH],
            "prospective_field_outcomes_opened": False,
            "outcome_opening_gate_satisfied": False,
            "next_gate": "Commit the canonical candidate/order receipt, then rerun this command.",
        }

    if not private_root.is_dir():
        raise ValueError("canonical candidate receipt exists but private pre-field root is missing")

    try:
        candidate_pin = verify_public_freeze_pin(candidate, repo_root=repo)
    except ValueError as exc:
        return {
            "schema_version": "cirsium-fresh-sentinel-pre-outcome-advance-v1",
            "status": "CANDIDATE_RECEIPT_PIN_NOT_SATISFIED",
            "standardized_effort_protocol_pin_commit": effort_pin["pin_commit"],
            "movement_constraint_pin_commit": movement_pin["pin_commit"],
            "prospective_field_outcomes_opened": False,
            "outcome_opening_gate_satisfied": False,
            "pin_error": str(exc),
            "next_gate": "Commit the exact canonical candidate/order receipt without modifying its bytes.",
        }

    if capacity.exists():
        capacity_value = _load_json(capacity)
        frozen_movement = float(capacity_value.get("max_network_transition_km") or 0.0)
        if frozen_movement != movement_km:
            raise ValueError(
                "requested movement constraint differs from the already-frozen canonical operational capacity profile"
            )
    else:
        derive_operational_capacity_profile(
            private_root,
            effort,
            max_network_transition_km=movement_km,
            out_json=capacity,
            repo_root=repo,
        )

    if not private_schedule.exists():
        build_private_field_schedule(
            private_root,
            candidate,
            evaluation,
            capacity,
            effort,
            private_schedule,
            repo_root=repo,
        )

    if not schedule_receipt.exists():
        receipt = build_public_field_schedule_receipt(
            private_schedule,
            candidate,
            evaluation,
            private_root,
            capacity,
            effort,
            analysis_plan,
            field_log_template,
            repo_root=repo,
        )
        schedule_receipt.parent.mkdir(parents=True, exist_ok=True)
        schedule_receipt.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return {
            "schema_version": "cirsium-fresh-sentinel-pre-outcome-advance-v1",
            "status": "FIELD_SCHEDULE_RECEIPT_READY_FOR_COMMIT",
            "standardized_effort_protocol_pin_commit": effort_pin["pin_commit"],
            "movement_constraint_pin_commit": movement_pin["pin_commit"],
            "candidate_order_pin_commit": candidate_pin["pin_commit"],
            "max_network_transition_km": movement_km,
            "private_schedule_path": str(private_schedule),
            "public_paths_to_commit": [
                CANONICAL_OPERATIONAL_CAPACITY_PROFILE_REPO_PATH,
                CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH,
            ],
            "prospective_field_outcomes_opened": False,
            "outcome_opening_gate_satisfied": False,
            "next_gate": "Commit the canonical capacity profile and field-schedule receipt, then rerun this command.",
        }

    try:
        schedule_pin = verify_public_field_schedule_pin(schedule_receipt, repo_root=repo)
    except ValueError as exc:
        return {
            "schema_version": "cirsium-fresh-sentinel-pre-outcome-advance-v1",
            "status": "FIELD_SCHEDULE_RECEIPT_PIN_NOT_SATISFIED",
            "standardized_effort_protocol_pin_commit": effort_pin["pin_commit"],
            "movement_constraint_pin_commit": movement_pin["pin_commit"],
            "candidate_order_pin_commit": candidate_pin["pin_commit"],
            "prospective_field_outcomes_opened": False,
            "outcome_opening_gate_satisfied": False,
            "pin_error": str(exc),
            "next_gate": "Commit the exact canonical field-schedule receipt and bound capacity profile without changing frozen bytes.",
        }

    final = verify_pre_outcome_gate(
        candidate,
        schedule_receipt,
        evaluation,
        field_log_template,
        analysis_plan,
        repo_root=repo,
        expected_candidate_pin_commit=candidate_pin["pin_commit"],
        expected_schedule_pin_commit=schedule_pin["pin_commit"],
        expected_effort_pin_commit=effort_pin["pin_commit"],
        expected_movement_pin_commit=movement_pin["pin_commit"],
    )
    return {
        "schema_version": "cirsium-fresh-sentinel-pre-outcome-advance-v1",
        "status": final["status"],
        "standardized_effort_protocol_pin_commit": effort_pin["pin_commit"],
        "movement_constraint_pin_commit": movement_pin["pin_commit"],
        "candidate_order_pin_commit": candidate_pin["pin_commit"],
        "field_schedule_pin_commit": schedule_pin["pin_commit"],
        "max_network_transition_km": movement_km,
        "prospective_field_outcomes_opened": False,
        "outcome_opening_gate_satisfied": bool(final["outcome_opening_gate_satisfied"]),
        "next_gate": "Only the preregistered prospective field-log workflow may now open outcomes.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-pre-field-root", type=Path, required=True)
    parser.add_argument("--bundle-geojson", type=Path)
    parser.add_argument("--private-schedule", type=Path)
    parser.add_argument("--max-network-transition-km", type=float)
    args = parser.parse_args()
    result = advance_pre_outcome_pipeline(
        args.private_pre_field_root,
        max_network_transition_km=args.max_network_transition_km,
        bundle_geojson=args.bundle_geojson,
        private_schedule_path=args.private_schedule,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
