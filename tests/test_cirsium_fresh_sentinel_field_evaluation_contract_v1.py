from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from research.validate_cirsium_fresh_sentinel_field_evaluation_contract_v1 import (
    DEFAULT_CONTRACT,
    DEFAULT_FIELD_LOG_TEMPLATE,
    EXPECTED_RESOLVED_DENOMINATOR_STATES,
    validate_field_evaluation_contract,
)


def _load_contract() -> dict:
    return json.loads(DEFAULT_CONTRACT.read_text(encoding="utf-8"))


def _write_contract(tmp_path: Path, value: dict) -> Path:
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def test_repository_contract_and_empty_field_log_template_are_valid() -> None:
    result = validate_field_evaluation_contract()
    assert result["status"] == "FRESH_SENTINEL_FIELD_EVALUATION_CONTRACT_VALID"
    assert result["cohort_unit_ids"] == ["CIR02", "CIR06", "CIR12", "CIR13"]
    assert result["primary_success_state"] == "SEARCH_COMPLETED_DETECTED_VERIFIED"
    assert result["resolved_binary_denominator_states"] == EXPECTED_RESOLVED_DENOMINATOR_STATES
    assert result["analysis_unit_frozen"] is True
    assert result["analysis_unit_identity"] == "COHORT_ARM_CANDIDATE_V1"
    assert result["repeated_visit_aggregation_frozen"] is True
    assert result["repeated_visit_aggregation_identity"] == "ANY_VERIFIED_DETECTION_ELSE_ALL_RESOLVED_NONDETECTION_V1"
    assert result["shared_candidate_handling_frozen"] is True
    assert result["shared_candidate_handling_identity"] == "RETAIN_IN_EACH_NOMINATING_ARM_WITH_SHARED_OBSERVATION_V1"
    assert result["arm_symmetry_identity"] == "ARM_SYMMETRIC_PREFIX_EFFORT_TEMPLATE_V1"
    assert result["arm_symmetric_prefix_effort_template_required"] is True
    assert result["analysis_plan_frozen"] is True
    assert result["primary_cross_taxon_estimand_identity"] == "EQUAL_TAXON_MACRO_PRIMARY_MINUS_COVERAGE_ONLY_V1"
    assert result["field_log_schedule_linkage_identity"] == "ANALYSIS_UNIT_VISIT_SCHEDULE_JOIN_V1"
    assert result["numeric_effort_schedule_frozen"] is False
    assert result["prospective_outcome_opening_allowed_now"] is False


def test_unresolved_identity_cannot_be_reclassified_as_absence(tmp_path: Path) -> None:
    value = _load_contract()
    value["newly_frozen_primary_binary_endpoint"]["identity_unresolved_handling"] = "count as absence"
    with pytest.raises(ValueError, match="identity-unresolved"):
        validate_field_evaluation_contract(_write_contract(tmp_path, value), DEFAULT_FIELD_LOG_TEMPLATE)


def test_operational_failures_cannot_enter_biological_negative_denominator(tmp_path: Path) -> None:
    value = _load_contract()
    value["newly_frozen_primary_binary_endpoint"]["non_biological_negative_handling"] = "count as non-detection"
    with pytest.raises(ValueError, match="operational/non-evaluable"):
        validate_field_evaluation_contract(_write_contract(tmp_path, value), DEFAULT_FIELD_LOG_TEMPLATE)


def test_numeric_effort_schedule_cannot_be_claimed_frozen_without_schedule_gate(tmp_path: Path) -> None:
    value = _load_contract()
    value["effort_accounting"]["numeric_effort_schedule_frozen_now"] = True
    with pytest.raises(ValueError, match="numeric effort schedule"):
        validate_field_evaluation_contract(_write_contract(tmp_path, value), DEFAULT_FIELD_LOG_TEMPLATE)


def test_outcome_opening_cannot_be_enabled_while_allocation_schedule_is_pending(tmp_path: Path) -> None:
    value = _load_contract()
    value["pre_outcome_gate_state"]["prospective_outcome_opening_allowed_now"] = True
    with pytest.raises(ValueError, match="outcome opening"):
        validate_field_evaluation_contract(_write_contract(tmp_path, value), DEFAULT_FIELD_LOG_TEMPLATE)


def test_required_field_log_column_removal_is_detected(tmp_path: Path) -> None:
    with DEFAULT_FIELD_LOG_TEMPLATE.open(newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    header.remove("search_minutes")
    template = tmp_path / "field_log.csv"
    template.write_text(",".join(header) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="search_minutes"):
        validate_field_evaluation_contract(DEFAULT_CONTRACT, template)


def test_analysis_unit_identity_is_frozen_before_schedule_instantiation(tmp_path: Path) -> None:
    value = _load_contract()
    value["analysis_unit_and_repeated_visits"]["primary_analysis_unit_identity"] = "CHANGED_ANALYSIS_UNIT"
    with pytest.raises(ValueError, match="analysis unit identity"):
        validate_field_evaluation_contract(_write_contract(tmp_path, value), DEFAULT_FIELD_LOG_TEMPLATE)


def test_repeated_visit_aggregation_identity_is_frozen_before_schedule_instantiation(tmp_path: Path) -> None:
    value = _load_contract()
    value["analysis_unit_and_repeated_visits"]["repeated_visit_aggregation_identity"] = "CHANGED_REPEAT_RULE"
    with pytest.raises(ValueError, match="repeated-visit aggregation"):
        validate_field_evaluation_contract(_write_contract(tmp_path, value), DEFAULT_FIELD_LOG_TEMPLATE)


def test_shared_candidate_handling_identity_is_frozen_before_schedule_instantiation(tmp_path: Path) -> None:
    value = _load_contract()
    value["analysis_unit_and_repeated_visits"]["shared_candidate_handling_identity"] = "CHANGED_SHARED_RULE"
    with pytest.raises(ValueError, match="shared-candidate handling"):
        validate_field_evaluation_contract(_write_contract(tmp_path, value), DEFAULT_FIELD_LOG_TEMPLATE)


def test_arm_symmetry_identity_is_frozen_before_schedule_instantiation(tmp_path: Path) -> None:
    value = _load_contract()
    value["schedule_selection_mechanics"]["arm_symmetry_identity"] = "ARM_SPECIFIC_ALLOCATION"
    with pytest.raises(ValueError, match="arm symmetry"):
        validate_field_evaluation_contract(_write_contract(tmp_path, value), DEFAULT_FIELD_LOG_TEMPLATE)


def test_arm_specific_effort_reallocation_cannot_be_enabled(tmp_path: Path) -> None:
    value = _load_contract()
    value["schedule_selection_mechanics"]["arm_specific_effort_reallocation_allowed"] = True
    with pytest.raises(ValueError, match="arm-specific effort"):
        validate_field_evaluation_contract(_write_contract(tmp_path, value), DEFAULT_FIELD_LOG_TEMPLATE)


def test_field_log_schedule_join_cannot_be_weakened(tmp_path: Path) -> None:
    value = _load_contract()
    value["field_log_schedule_linkage"]["exact_one_field_log_row_per_scheduled_visit_required"] = False
    with pytest.raises(ValueError, match="field-log schedule linkage"):
        validate_field_evaluation_contract(_write_contract(tmp_path, value), DEFAULT_FIELD_LOG_TEMPLATE)


def test_unscheduled_field_log_rows_cannot_be_enabled(tmp_path: Path) -> None:
    value = _load_contract()
    value["field_log_schedule_linkage"]["unscheduled_extra_field_log_rows_allowed"] = True
    with pytest.raises(ValueError, match="unscheduled"):
        validate_field_evaluation_contract(_write_contract(tmp_path, value), DEFAULT_FIELD_LOG_TEMPLATE)
