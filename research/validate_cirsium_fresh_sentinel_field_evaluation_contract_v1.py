#!/usr/bin/env python3
"""Validate the fresh-SENTINEL field-evaluation contract without opening outcomes.

This validator intentionally reads only the public pre-outcome evaluation contract
and the empty field-log template. It must never inspect prospective field rows.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_field_evaluation_contract_v1.json"
DEFAULT_FIELD_LOG_TEMPLATE = ROOT / "validation" / "cirsium_aza3_acsp_field_log_template_v1.csv"
EXPECTED_UNITS = ["CIR02", "CIR06", "CIR12", "CIR13"]
EXPECTED_NON_BIOLOGICAL_STATES = ["ACCESS_FAILED", "PERMISSION_BLOCKED", "PHENOLOGY_NOT_EVALUABLE", "SEARCH_INCOMPLETE_OTHER"]
EXPECTED_RESOLVED_DENOMINATOR_STATES = ["SEARCH_COMPLETED_DETECTED_VERIFIED", "SEARCH_COMPLETED_NOT_DETECTED"]
EXPECTED_EFFORT_METRIC = {
    "identity": "PERSON_MINUTES_V1",
    "unit": "person-minute",
    "formula": "search_minutes * observer_count",
}
EXPECTED_ASSIGNMENT_IDENTITY = "FROZEN_ORDER_PREFIX_V1"


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("field evaluation contract must be a JSON object")
    return value


def _field_log_header(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        try:
            return next(reader)
        except StopIteration as exc:
            raise ValueError("field log template is empty") from exc


def validate_field_evaluation_contract(contract_path: Path = DEFAULT_CONTRACT, field_log_template: Path = DEFAULT_FIELD_LOG_TEMPLATE) -> dict[str, Any]:
    contract = _load_json(Path(contract_path))
    if contract.get("status") != "FROZEN_PRE_OUTCOME_EVALUATION_SEMANTICS_ALLOCATION_SCHEDULE_PENDING":
        raise ValueError("unexpected field evaluation contract status")
    if contract.get("method_identity") != "COVERAGE_THEN_FINE_STRUCTURE_V1":
        raise ValueError("unexpected primary method identity")
    if contract.get("cohort_unit_ids") != EXPECTED_UNITS:
        raise ValueError("fresh cohort unit set/order changed")

    endpoint = contract.get("field_endpoint") or {}
    if endpoint.get("primary_success_state") != "SEARCH_COMPLETED_DETECTED_VERIFIED":
        raise ValueError("primary verified-occurrence success state changed")
    if endpoint.get("resolved_completed_non_detection_state") != "SEARCH_COMPLETED_NOT_DETECTED":
        raise ValueError("resolved biological non-detection state changed")
    if endpoint.get("identity_unresolved_state") != "SEARCH_COMPLETED_DETECTED_IDENTITY_UNRESOLVED":
        raise ValueError("identity-unresolved state changed")
    if endpoint.get("non_biological_negative_states") != EXPECTED_NON_BIOLOGICAL_STATES:
        raise ValueError("non-biological-negative state set/order changed")
    if endpoint.get("tissue_collection_is_secondary") is not True:
        raise ValueError("tissue collection must remain secondary to location discovery")

    primary = contract.get("newly_frozen_primary_binary_endpoint") or {}
    if primary.get("resolved_binary_denominator_states") != EXPECTED_RESOLVED_DENOMINATOR_STATES:
        raise ValueError("resolved binary denominator states changed")
    if "never recode as absence" not in str(primary.get("identity_unresolved_handling") or ""):
        raise ValueError("identity-unresolved records must not be recoded as absence")
    if "never recode as absence" not in str(primary.get("non_biological_negative_handling") or ""):
        raise ValueError("operational/non-evaluable states must not be recoded as absence")
    if primary.get("favorable_subsetting_after_outcome") is not False:
        raise ValueError("favorable post-outcome subsetting must remain forbidden")
    if primary.get("switching_primary_endpoint_after_outcome") is not False:
        raise ValueError("post-outcome endpoint switching must remain forbidden")

    arms = contract.get("frozen_method_arms") or {}
    if arms != {
        "primary": "COVERAGE_THEN_FINE_STRUCTURE_V1",
        "coverage_only": "COVERAGE_ONLY_STABLE_WITHIN_CELL_V1",
        "fine_spatial_balance": "MORTON_DYADIC_COVERAGE_ORDER_V1",
        "nearest_known": "NOT_DEFINED_FOR_SENTINEL",
    }:
        raise ValueError("fresh-SENTINEL method/comparator arms changed")

    effort = contract.get("effort_accounting") or {}
    if effort.get("minimum_required_fields") != ["search_minutes", "observer_count"]:
        raise ValueError("minimum field-effort columns changed")
    if effort.get("matched_field_effort_required_for_between_arm_promotion") is not True:
        raise ValueError("matched field effort must be required for promotion")
    if effort.get("complete_visited_patch_detection_and_non_detection_logs_required") is not True:
        raise ValueError("complete visited-patch logs must be required")
    if effort.get("numeric_effort_metric_frozen_now") is not True:
        raise ValueError("PERSON_MINUTES_V1 must remain frozen before outcomes")
    if effort.get("numeric_effort_metric") != EXPECTED_EFFORT_METRIC:
        raise ValueError("numeric effort metric changed from PERSON_MINUTES_V1")
    if effort.get("numeric_effort_schedule_frozen_now") is not False:
        raise ValueError("numeric effort schedule cannot be claimed frozen before candidate-specific allocation")

    mechanics = contract.get("schedule_selection_mechanics") or {}
    if mechanics.get("comparator_assignment_identity") != EXPECTED_ASSIGNMENT_IDENTITY:
        raise ValueError("schedule comparator assignment changed from FROZEN_ORDER_PREFIX_V1")
    for key in (
        "candidate_membership_in_exact_frozen_arm_order_required",
        "private_unit_receipt_hash_linkage_required",
        "private_order_hash_linkage_required",
    ):
        if mechanics.get(key) is not True:
            raise ValueError(f"schedule selection mechanic weakened: {key}")
    if mechanics.get("post_outcome_candidate_substitution_allowed") is not False:
        raise ValueError("post-outcome candidate substitution must remain forbidden")

    analysis = contract.get("analysis_unit_and_repeated_visits") or {}
    if analysis.get("primary_analysis_unit_frozen_now") is not False:
        raise ValueError("analysis unit cannot be claimed frozen before allocation schedule")
    if analysis.get("repeated_visit_aggregation_frozen_now") is not False:
        raise ValueError("repeated-visit aggregation cannot be claimed frozen yet")

    gate = contract.get("pre_outcome_gate_state") or {}
    if gate.get("static_evaluation_semantics_frozen") is not True:
        raise ValueError("static evaluation semantics must be frozen")
    if gate.get("field_allocation_and_effort_schedule_frozen") is not False:
        raise ValueError("field allocation/effort schedule is not frozen yet")
    if gate.get("field_allocation_and_effort_schedule_pinned") is not False:
        raise ValueError("field allocation/effort schedule is not pinned yet")
    if gate.get("prospective_outcome_opening_allowed_now") is not False:
        raise ValueError("prospective outcome opening must remain blocked")

    header = _field_log_header(Path(field_log_template))
    required = contract.get("field_log_schema_required_columns") or []
    if not isinstance(required, list) or not required:
        raise ValueError("field log required-column contract is empty")
    missing = [column for column in required if column not in header]
    if missing:
        raise ValueError(f"field log template is missing required columns: {missing}")

    return {
        "status": "FRESH_SENTINEL_FIELD_EVALUATION_CONTRACT_VALID",
        "cohort_unit_ids": EXPECTED_UNITS,
        "primary_success_state": endpoint["primary_success_state"],
        "resolved_binary_denominator_states": primary["resolved_binary_denominator_states"],
        "numeric_effort_metric": EXPECTED_EFFORT_METRIC,
        "comparator_assignment_identity": EXPECTED_ASSIGNMENT_IDENTITY,
        "numeric_effort_schedule_frozen": False,
        "prospective_outcome_opening_allowed_now": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--field-log-template", type=Path, default=DEFAULT_FIELD_LOG_TEMPLATE)
    args = parser.parse_args()
    result = validate_field_evaluation_contract(args.contract, args.field_log_template)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
