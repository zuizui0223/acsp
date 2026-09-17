#!/usr/bin/env python3
"""Validate a private fresh-SENTINEL field allocation/effort schedule pre-outcome.

The instantiated schedule may contain sensitive candidate references and therefore
must remain outside the public repository. This validator never reads field outcome
logs. It binds the schedule to the exact public candidate/order receipt and static
field-evaluation contract, requires all four frozen cohort units and all three arms,
enforces the already-frozen analysis/repeat/shared-candidate semantics, requires a
one-to-one analysis-unit mapping with contiguous visit indices, and enforces equal
declared total effort across arms within each cohort unit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
EXPECTED_ARMS = (
    "COVERAGE_THEN_FINE_STRUCTURE_V1",
    "COVERAGE_ONLY_STABLE_WITHIN_CELL_V1",
    "MORTON_DYADIC_COVERAGE_ORDER_V1",
)
EXPECTED_SCHEMA = "cirsium-fresh-sentinel-private-field-schedule-v1"
EXPECTED_STATUS = "PRIVATE_FIELD_ALLOCATION_AND_EFFORT_SCHEDULE_FROZEN"
EXPECTED_MATCH_SCOPE = "WITHIN_COHORT_UNIT_ACROSS_ALL_THREE_ARMS"
CANDIDATE_RECEIPT_STATUS = "PUBLIC_HASH_FREEZE_READY_FOR_COMMIT"
EVALUATION_STATUS = "FROZEN_PRE_OUTCOME_EVALUATION_SEMANTICS_ALLOCATION_SCHEDULE_PENDING"

TOP_KEYS = {
    "schema_version",
    "status",
    "cohort_unit_ids",
    "candidate_order_public_receipt_sha256",
    "field_evaluation_contract_sha256",
    "primary_analysis_unit_identity",
    "repeated_visit_aggregation_identity",
    "repeated_visit_aggregation_rule",
    "shared_candidate_handling_identity",
    "shared_candidate_handling_rule",
    "comparator_assignment_identity",
    "numeric_effort_metric",
    "matched_effort_scope",
    "assignments",
    "prospective_field_outcomes_opened",
    "field_outcomes_used_to_allocate",
    "post_outcome_schedule_edits_allowed",
}
METRIC_KEYS = {"identity", "unit", "formula"}
ASSIGNMENT_KEYS = {
    "cohort_unit_id",
    "analysis_unit_id",
    "private_candidate_ref",
    "method_arm",
    "visit_index",
    "planned_effort_value",
    "planned_search_minutes",
    "planned_observer_count",
}


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"missing JSON input: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON input must be an object: {path}")
    return value


def _nonempty(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} must be a non-empty frozen identity/rule")
    return text


def _positive_number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{label} must be finite and >0")
    return number


def _require_exact_schedule_semantics(schedule: dict[str, Any], evaluation: dict[str, Any]) -> None:
    analysis = evaluation.get("analysis_unit_and_repeated_visits")
    if not isinstance(analysis, dict):
        raise ValueError("field evaluation contract lacks frozen analysis-unit semantics")
    mechanics = evaluation.get("schedule_selection_mechanics")
    if not isinstance(mechanics, dict):
        raise ValueError("field evaluation contract lacks frozen schedule-selection mechanics")
    effort = evaluation.get("effort_accounting")
    if not isinstance(effort, dict):
        raise ValueError("field evaluation contract lacks frozen effort accounting")

    exact_pairs = (
        ("primary_analysis_unit_identity", analysis.get("primary_analysis_unit_identity"), "analysis unit identity"),
        ("repeated_visit_aggregation_identity", analysis.get("repeated_visit_aggregation_identity"), "repeated-visit aggregation identity"),
        ("repeated_visit_aggregation_rule", analysis.get("repeated_visit_aggregation_rule"), "repeated-visit aggregation rule"),
        ("shared_candidate_handling_identity", analysis.get("shared_candidate_handling_identity"), "shared-candidate handling identity"),
        ("shared_candidate_handling_rule", analysis.get("shared_candidate_handling_rule"), "shared-candidate handling rule"),
        ("comparator_assignment_identity", mechanics.get("comparator_assignment_identity"), "comparator assignment identity"),
    )
    for schedule_key, expected, label in exact_pairs:
        expected_text = _nonempty(expected, f"field evaluation contract {label}")
        if schedule.get(schedule_key) != expected_text:
            raise ValueError(f"private schedule {label} differs from the exact frozen field evaluation contract")

    expected_metric = effort.get("numeric_effort_metric")
    if not isinstance(expected_metric, dict) or set(expected_metric) != METRIC_KEYS:
        raise ValueError("field evaluation contract numeric effort metric is malformed")
    if schedule.get("numeric_effort_metric") != expected_metric:
        raise ValueError("private schedule numeric effort metric differs from the exact frozen field evaluation contract")

    if analysis.get("analysis_unit_id_must_map_one_to_one_to_cohort_arm_candidate") is not True:
        raise ValueError("field evaluation contract must require one-to-one analysis-unit mapping")
    if analysis.get("visit_indices_must_be_contiguous_from_one_within_analysis_unit") is not True:
        raise ValueError("field evaluation contract must require contiguous visit indices")


def validate_private_field_schedule(
    schedule_path: Path,
    candidate_receipt_path: Path,
    field_evaluation_contract_path: Path,
    *,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    schedule_path = Path(schedule_path).resolve()
    candidate_receipt_path = Path(candidate_receipt_path).resolve()
    field_evaluation_contract_path = Path(field_evaluation_contract_path).resolve()

    if _inside(schedule_path, repo):
        raise ValueError("private field schedule must remain outside the public repository")
    if not _inside(candidate_receipt_path, repo):
        raise ValueError("candidate/order public receipt must be inside the repository")
    if not _inside(field_evaluation_contract_path, repo):
        raise ValueError("field evaluation contract must be inside the repository")

    schedule = _load(schedule_path)
    if set(schedule) != TOP_KEYS:
        raise ValueError(f"private schedule keys must match the frozen schema exactly; got {sorted(schedule)}")
    if schedule.get("schema_version") != EXPECTED_SCHEMA or schedule.get("status") != EXPECTED_STATUS:
        raise ValueError("private schedule schema/status does not match the frozen contract")
    if tuple(schedule.get("cohort_unit_ids") or ()) != EXPECTED_UNITS:
        raise ValueError("private schedule cohort must be exactly CIR02/CIR06/CIR12/CIR13 in frozen order")
    if schedule.get("prospective_field_outcomes_opened") is not False:
        raise ValueError("private schedule cannot be frozen after prospective outcomes are opened")
    if schedule.get("field_outcomes_used_to_allocate") is not False:
        raise ValueError("field outcomes cannot be used to define field allocation")
    if schedule.get("post_outcome_schedule_edits_allowed") is not False:
        raise ValueError("post-outcome schedule edits must remain forbidden")
    if schedule.get("matched_effort_scope") != EXPECTED_MATCH_SCOPE:
        raise ValueError("matched effort scope must remain within cohort unit across all three arms")

    for key in (
        "primary_analysis_unit_identity",
        "repeated_visit_aggregation_identity",
        "repeated_visit_aggregation_rule",
        "shared_candidate_handling_identity",
        "shared_candidate_handling_rule",
        "comparator_assignment_identity",
    ):
        _nonempty(schedule.get(key), key)

    metric = schedule.get("numeric_effort_metric")
    if not isinstance(metric, dict) or set(metric) != METRIC_KEYS:
        raise ValueError("numeric_effort_metric must contain exactly identity/unit/formula")
    for key in METRIC_KEYS:
        _nonempty(metric.get(key), f"numeric_effort_metric.{key}")

    candidate_receipt = _load(candidate_receipt_path)
    if candidate_receipt.get("status") != CANDIDATE_RECEIPT_STATUS:
        raise ValueError("candidate/order receipt is not in the frozen commit-ready state")
    if candidate_receipt.get("prospective_field_outcomes_opened") is not False:
        raise ValueError("candidate/order receipt cannot declare opened outcomes")
    if candidate_receipt.get("field_outcomes_used_to_choose_or_rank") is not False:
        raise ValueError("candidate/order receipt cannot be outcome-informed")
    candidate_hash = _sha256(candidate_receipt_path)
    if schedule.get("candidate_order_public_receipt_sha256") != candidate_hash:
        raise ValueError("private schedule is not bound to the exact candidate/order public receipt bytes")

    evaluation = _load(field_evaluation_contract_path)
    if evaluation.get("status") != EVALUATION_STATUS:
        raise ValueError("field evaluation contract status changed")
    if tuple(evaluation.get("cohort_unit_ids") or ()) != EXPECTED_UNITS:
        raise ValueError("field evaluation contract cohort changed")
    evaluation_hash = _sha256(field_evaluation_contract_path)
    if schedule.get("field_evaluation_contract_sha256") != evaluation_hash:
        raise ValueError("private schedule is not bound to the exact field evaluation contract bytes")
    _require_exact_schedule_semantics(schedule, evaluation)

    assignments = schedule.get("assignments")
    if not isinstance(assignments, list) or not assignments:
        raise ValueError("private schedule must contain candidate-specific assignments")

    totals = {unit: {arm: 0.0 for arm in EXPECTED_ARMS} for unit in EXPECTED_UNITS}
    counts = {unit: {arm: 0 for arm in EXPECTED_ARMS} for unit in EXPECTED_UNITS}
    seen_visits: set[tuple[str, int]] = set()
    candidate_to_analysis: dict[tuple[str, str, str], str] = {}
    analysis_to_candidate: dict[str, tuple[str, str, str]] = {}
    visits_by_analysis: dict[str, list[int]] = {}

    for index, row in enumerate(assignments):
        if not isinstance(row, dict) or set(row) != ASSIGNMENT_KEYS:
            raise ValueError(f"assignment {index} keys do not match the frozen private schedule schema")
        unit = str(row.get("cohort_unit_id") or "")
        arm = str(row.get("method_arm") or "")
        if unit not in EXPECTED_UNITS:
            raise ValueError(f"assignment {index} has unexpected cohort unit: {unit}")
        if arm not in EXPECTED_ARMS:
            raise ValueError(f"assignment {index} has unexpected method arm: {arm}")
        analysis_unit = _nonempty(row.get("analysis_unit_id"), f"assignment {index}.analysis_unit_id")
        candidate_ref = _nonempty(row.get("private_candidate_ref"), f"assignment {index}.private_candidate_ref")
        visit = row.get("visit_index")
        if isinstance(visit, bool) or not isinstance(visit, int) or visit < 1:
            raise ValueError(f"assignment {index}.visit_index must be an integer >=1")

        candidate_key = (unit, arm, candidate_ref)
        prior_analysis = candidate_to_analysis.setdefault(candidate_key, analysis_unit)
        if prior_analysis != analysis_unit:
            raise ValueError("analysis unit id must map one-to-one to cohort-arm-candidate identity")
        prior_candidate = analysis_to_candidate.setdefault(analysis_unit, candidate_key)
        if prior_candidate != candidate_key:
            raise ValueError("analysis unit id must map one-to-one to cohort-arm-candidate identity")

        visit_key = (analysis_unit, visit)
        if visit_key in seen_visits:
            raise ValueError(f"duplicate scheduled visit identity: {visit_key}")
        seen_visits.add(visit_key)
        visits_by_analysis.setdefault(analysis_unit, []).append(visit)

        effort = _positive_number(row.get("planned_effort_value"), f"assignment {index}.planned_effort_value")
        _positive_number(row.get("planned_search_minutes"), f"assignment {index}.planned_search_minutes")
        observers = row.get("planned_observer_count")
        if isinstance(observers, bool) or not isinstance(observers, int) or observers < 1:
            raise ValueError(f"assignment {index}.planned_observer_count must be an integer >=1")
        totals[unit][arm] += effort
        counts[unit][arm] += 1

    for analysis_unit, visits in visits_by_analysis.items():
        ordered = sorted(visits)
        if ordered != list(range(1, len(ordered) + 1)):
            raise ValueError(f"visit indices must be contiguous from one within analysis unit: {analysis_unit}")

    for unit in EXPECTED_UNITS:
        if any(counts[unit][arm] == 0 for arm in EXPECTED_ARMS):
            raise ValueError(f"{unit} must have at least one assignment in every frozen method arm")
        reference = totals[unit][EXPECTED_ARMS[0]]
        for arm in EXPECTED_ARMS[1:]:
            if not math.isclose(totals[unit][arm], reference, rel_tol=1e-9, abs_tol=1e-9):
                raise ValueError(f"declared total effort is not matched across arms within {unit}")

    return {
        "status": "PRIVATE_FIELD_ALLOCATION_AND_EFFORT_SCHEDULE_VALID",
        "cohort_unit_ids": list(EXPECTED_UNITS),
        "method_arms": list(EXPECTED_ARMS),
        "candidate_order_public_receipt_sha256": candidate_hash,
        "field_evaluation_contract_sha256": evaluation_hash,
        "numeric_effort_metric": metric,
        "primary_analysis_unit_identity": schedule["primary_analysis_unit_identity"],
        "repeated_visit_aggregation_identity": schedule["repeated_visit_aggregation_identity"],
        "shared_candidate_handling_identity": schedule["shared_candidate_handling_identity"],
        "comparator_assignment_identity": schedule["comparator_assignment_identity"],
        "analysis_unit_mapping_verified": True,
        "visit_index_contiguity_verified": True,
        "assignment_count": len(assignments),
        "assignment_count_by_unit_arm": counts,
        "matched_effort_totals_by_unit_arm": totals,
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used_to_allocate": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schedule", type=Path, required=True)
    parser.add_argument("--candidate-receipt", type=Path, required=True)
    parser.add_argument("--field-evaluation-contract", type=Path, required=True)
    args = parser.parse_args()
    result = validate_private_field_schedule(
        args.schedule,
        args.candidate_receipt,
        args.field_evaluation_contract,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
