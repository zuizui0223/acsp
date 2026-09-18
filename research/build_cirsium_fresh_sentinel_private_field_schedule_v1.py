#!/usr/bin/env python3
"""Build the private fresh-SENTINEL field schedule from frozen orders and an outcome-blind G_F capacity profile.

The capacity profile contains no candidate identities. For each frozen cohort unit,
this builder takes the exact no-skip prefix of every arm order and applies one
arm-symmetric visit/effort pattern. It never reads prospective field outcomes and
never chooses candidates by habitat score, access, or route information.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from research.validate_cirsium_fresh_sentinel_private_field_schedule_v1 import (
    validate_private_field_schedule,
)
from research.validate_cirsium_fresh_sentinel_private_schedule_membership_v1 import (
    validate_private_schedule_membership,
)

ROOT = Path(__file__).resolve().parents[1]
UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
ARMS = (
    "COVERAGE_THEN_FINE_STRUCTURE_V1",
    "COVERAGE_ONLY_STABLE_WITHIN_CELL_V1",
    "MORTON_DYADIC_COVERAGE_ORDER_V1",
)
ARM_TO_ORDER = {
    ARMS[0]: "coverage_then_fine_structure",
    ARMS[1]: "coverage_only",
    ARMS[2]: "fine_spatial_balance",
}
PROFILE_SCHEMA = "cirsium-fresh-sentinel-operational-capacity-profile-v1"
PROFILE_STATUS = "PRE_OUTCOME_OPERATIONAL_CAPACITY_FROZEN"
SCHEDULE_SCHEMA = "cirsium-fresh-sentinel-private-field-schedule-v1"
SCHEDULE_STATUS = "PRIVATE_FIELD_ALLOCATION_AND_EFFORT_SCHEDULE_FROZEN"


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be an integer >=1")
    return value


def _positive_float(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not number > 0:
        raise ValueError(f"{label} must be >0")
    return number


def _validate_capacity_profile(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    required = {
        "schema_version",
        "status",
        "cohort_unit_ids",
        "capacity_source_identity",
        "unit_capacity",
        "prospective_field_outcomes_opened",
        "field_outcomes_used_to_set_capacity",
        "arm_specific_capacity_allowed",
        "post_outcome_capacity_edits_allowed",
    }
    if set(profile) != required:
        raise ValueError("operational capacity profile keys must match the frozen v1 contract exactly")
    if profile.get("schema_version") != PROFILE_SCHEMA or profile.get("status") != PROFILE_STATUS:
        raise ValueError("operational capacity profile schema/status changed")
    if tuple(profile.get("cohort_unit_ids") or ()) != UNITS:
        raise ValueError("operational capacity profile must contain the exact four frozen cohort units")
    if not str(profile.get("capacity_source_identity") or "").strip():
        raise ValueError("capacity_source_identity must be non-empty")
    if profile.get("prospective_field_outcomes_opened") is not False:
        raise ValueError("capacity cannot be frozen after outcomes are opened")
    if profile.get("field_outcomes_used_to_set_capacity") is not False:
        raise ValueError("field outcomes cannot define operational capacity")
    if profile.get("arm_specific_capacity_allowed") is not False:
        raise ValueError("arm-specific capacity is forbidden")
    if profile.get("post_outcome_capacity_edits_allowed") is not False:
        raise ValueError("post-outcome capacity edits are forbidden")

    capacities = profile.get("unit_capacity")
    if not isinstance(capacities, dict) or set(capacities) != set(UNITS):
        raise ValueError("unit_capacity must contain exactly CIR02/CIR06/CIR12/CIR13")
    expected_keys = {
        "prefix_depth",
        "visits_per_candidate",
        "search_minutes_per_visit",
        "observer_count",
    }
    normalized: dict[str, dict[str, Any]] = {}
    for unit in UNITS:
        row = capacities[unit]
        if not isinstance(row, dict) or set(row) != expected_keys:
            raise ValueError(f"{unit} capacity keys do not match the frozen v1 contract")
        normalized[unit] = {
            "prefix_depth": _positive_int(row["prefix_depth"], f"{unit}.prefix_depth"),
            "visits_per_candidate": _positive_int(row["visits_per_candidate"], f"{unit}.visits_per_candidate"),
            "search_minutes_per_visit": _positive_float(row["search_minutes_per_visit"], f"{unit}.search_minutes_per_visit"),
            "observer_count": _positive_int(row["observer_count"], f"{unit}.observer_count"),
        }
    return normalized


def _order_prefix(private_root: Path, unit: str, order_name: str, depth: int) -> list[str]:
    unit_receipt_path = private_root / unit / "pre_field_freeze_receipt.json"
    unit_receipt = _load_json(unit_receipt_path)
    if unit_receipt.get("status") != "PRE_FIELD_METHOD_AND_COMPARATORS_FROZEN":
        raise ValueError(f"{unit} private pre-field receipt is not frozen")
    files = unit_receipt.get("order_files")
    if not isinstance(files, dict) or order_name not in files:
        raise ValueError(f"{unit} private receipt lacks frozen order file {order_name}")
    order_path = private_root / unit / str(files[order_name])
    with order_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or "candidate_cell_id" not in (rows[0].keys() if rows else []):
        raise ValueError(f"frozen order lacks candidate_cell_id: {order_path}")
    if "decision_rank" not in rows[0]:
        raise ValueError(f"frozen order lacks decision_rank: {order_path}")
    try:
        ranked = sorted(rows, key=lambda row: int(str(row["decision_rank"])))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid decision_rank in {order_path}") from exc
    ranks = [int(str(row["decision_rank"])) for row in ranked]
    if ranks != list(range(1, len(ranked) + 1)):
        raise ValueError(f"frozen order decision_rank must be complete 1..N: {order_path}")
    if depth > len(ranked):
        raise ValueError(f"{unit}/{order_name} requested prefix depth {depth} exceeds frozen order length {len(ranked)}")
    ids = [str(row["candidate_cell_id"]).strip() for row in ranked[:depth]]
    if any(not value for value in ids) or len(set(ids)) != len(ids):
        raise ValueError(f"candidate ids are incomplete or duplicated in {order_path}")
    return ids


def _analysis_unit_id(unit: str, arm: str, candidate_ref: str) -> str:
    token = hashlib.sha256(f"{unit}|{arm}|{candidate_ref}".encode("utf-8")).hexdigest()[:20]
    return f"au_{token}"


def build_private_field_schedule(
    private_pre_field_root: Path,
    candidate_receipt_path: Path,
    field_evaluation_contract_path: Path,
    capacity_profile_path: Path,
    out_schedule_path: Path,
    *,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    private_root = Path(private_pre_field_root).resolve()
    candidate_receipt = Path(candidate_receipt_path).resolve()
    evaluation_path = Path(field_evaluation_contract_path).resolve()
    capacity_path = Path(capacity_profile_path).resolve()
    out_path = Path(out_schedule_path).resolve()

    if _inside(private_root, repo):
        raise ValueError("private pre-field root must remain outside the public repository")
    if _inside(out_path, repo):
        raise ValueError("private field schedule must remain outside the public repository")
    if out_path.exists():
        raise ValueError("refusing to overwrite an existing private field schedule")
    if not candidate_receipt.is_file() or not evaluation_path.is_file() or not capacity_path.is_file():
        raise ValueError("candidate receipt, evaluation contract and capacity profile must all exist")

    profile = _load_json(capacity_path)
    capacity = _validate_capacity_profile(profile)
    evaluation = _load_json(evaluation_path)
    analysis = evaluation["analysis_unit_and_repeated_visits"]
    mechanics = evaluation["schedule_selection_mechanics"]
    effort = evaluation["effort_accounting"]["numeric_effort_metric"]

    assignments: list[dict[str, Any]] = []
    selected_counts: dict[str, dict[str, int]] = {unit: {} for unit in UNITS}
    for unit in UNITS:
        cap = capacity[unit]
        depth = int(cap["prefix_depth"])
        visits = int(cap["visits_per_candidate"])
        minutes = float(cap["search_minutes_per_visit"])
        observers = int(cap["observer_count"])
        person_minutes = minutes * observers
        for arm in ARMS:
            refs = _order_prefix(private_root, unit, ARM_TO_ORDER[arm], depth)
            selected_counts[unit][arm] = len(refs)
            for candidate_ref in refs:
                analysis_unit = _analysis_unit_id(unit, arm, candidate_ref)
                for visit_index in range(1, visits + 1):
                    assignments.append({
                        "cohort_unit_id": unit,
                        "analysis_unit_id": analysis_unit,
                        "private_candidate_ref": candidate_ref,
                        "method_arm": arm,
                        "visit_index": visit_index,
                        "planned_effort_value": person_minutes,
                        "planned_search_minutes": minutes,
                        "planned_observer_count": observers,
                    })

    schedule = {
        "schema_version": SCHEDULE_SCHEMA,
        "status": SCHEDULE_STATUS,
        "cohort_unit_ids": list(UNITS),
        "candidate_order_public_receipt_sha256": _sha256(candidate_receipt),
        "field_evaluation_contract_sha256": _sha256(evaluation_path),
        "primary_analysis_unit_identity": analysis["primary_analysis_unit_identity"],
        "repeated_visit_aggregation_identity": analysis["repeated_visit_aggregation_identity"],
        "repeated_visit_aggregation_rule": analysis["repeated_visit_aggregation_rule"],
        "shared_candidate_handling_identity": analysis["shared_candidate_handling_identity"],
        "shared_candidate_handling_rule": analysis["shared_candidate_handling_rule"],
        "comparator_assignment_identity": mechanics["comparator_assignment_identity"],
        "arm_symmetry_identity": mechanics["arm_symmetry_identity"],
        "numeric_effort_metric": effort,
        "matched_effort_scope": "WITHIN_COHORT_UNIT_ACROSS_ALL_THREE_ARMS",
        "assignments": assignments,
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used_to_allocate": False,
        "post_outcome_schedule_edits_allowed": False,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(schedule, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    schedule_validation = validate_private_field_schedule(
        out_path,
        candidate_receipt,
        evaluation_path,
        repo_root=repo,
    )
    membership_validation = validate_private_schedule_membership(
        out_path,
        candidate_receipt,
        private_root,
        repo_root=repo,
    )
    return {
        "status": "PRIVATE_FIELD_SCHEDULE_BUILT_AND_VALIDATED",
        "out_schedule": str(out_path),
        "capacity_profile_sha256": _sha256(capacity_path),
        "assignment_count": len(assignments),
        "selected_unique_candidate_count_by_unit_arm": selected_counts,
        "schedule_validation_status": schedule_validation["status"],
        "membership_validation_status": membership_validation["status"],
        "prospective_field_outcomes_opened": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-pre-field-root", type=Path, required=True)
    parser.add_argument("--candidate-receipt", type=Path, required=True)
    parser.add_argument("--field-evaluation-contract", type=Path, required=True)
    parser.add_argument("--capacity-profile", type=Path, required=True)
    parser.add_argument("--out-schedule", type=Path, required=True)
    args = parser.parse_args()
    result = build_private_field_schedule(
        args.private_pre_field_root,
        args.candidate_receipt,
        args.field_evaluation_contract,
        args.capacity_profile,
        args.out_schedule,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
