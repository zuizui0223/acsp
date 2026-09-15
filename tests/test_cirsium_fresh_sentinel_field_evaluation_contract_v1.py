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
