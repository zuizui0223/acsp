from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from research.export_cirsium_fresh_sentinel_public_field_schedule_receipt_v1 import (
    PUBLIC_STATUS,
    build_public_field_schedule_receipt,
)
from research.validate_cirsium_fresh_sentinel_private_field_schedule_v1 import (
    EXPECTED_ARMS,
    EXPECTED_UNITS,
    validate_private_field_schedule,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _public_inputs(repo: Path) -> tuple[Path, Path]:
    candidate = repo / "validation" / "candidate-receipt.json"
    evaluation = repo / "validation" / "field-evaluation.json"
    _write(
        candidate,
        {
            "status": "PUBLIC_HASH_FREEZE_READY_FOR_COMMIT",
            "prospective_field_outcomes_opened": False,
            "field_outcomes_used_to_choose_or_rank": False,
        },
    )
    _write(
        evaluation,
        {
            "status": "FROZEN_PRE_OUTCOME_EVALUATION_SEMANTICS_ALLOCATION_SCHEDULE_PENDING",
            "cohort_unit_ids": list(EXPECTED_UNITS),
        },
    )
    return candidate, evaluation


def _schedule(path: Path, candidate: Path, evaluation: Path) -> dict:
    assignments = []
    for unit in EXPECTED_UNITS:
        for arm_index, arm in enumerate(EXPECTED_ARMS):
            assignments.append(
                {
                    "cohort_unit_id": unit,
                    "analysis_unit_id": f"{unit}-analysis-{arm_index}",
                    "private_candidate_ref": f"PRIVATE-{unit}-{arm_index}",
                    "method_arm": arm,
                    "visit_index": 1,
                    "planned_effort_value": 60.0,
                    "planned_search_minutes": 30.0,
                    "planned_observer_count": 2,
                }
            )
    return {
        "schema_version": "cirsium-fresh-sentinel-private-field-schedule-v1",
        "status": "PRIVATE_FIELD_ALLOCATION_AND_EFFORT_SCHEDULE_FROZEN",
        "cohort_unit_ids": list(EXPECTED_UNITS),
        "candidate_order_public_receipt_sha256": _sha256(candidate),
        "field_evaluation_contract_sha256": _sha256(evaluation),
        "primary_analysis_unit_identity": "TEST_ANALYSIS_UNIT_V1",
        "repeated_visit_aggregation_identity": "TEST_REPEAT_RULE_V1",
        "repeated_visit_aggregation_rule": "fixture rule chosen before outcomes",
        "shared_candidate_handling_identity": "TEST_SHARED_CANDIDATE_RULE_V1",
        "shared_candidate_handling_rule": "fixture handling chosen before outcomes",
        "comparator_assignment_identity": "TEST_COMPARATOR_ASSIGNMENT_V1",
        "numeric_effort_metric": {
            "identity": "TEST_PERSON_MINUTES_V1",
            "unit": "person-minute",
            "formula": "planned_search_minutes * planned_observer_count",
        },
        "matched_effort_scope": "WITHIN_COHORT_UNIT_ACROSS_ALL_THREE_ARMS",
        "assignments": assignments,
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used_to_allocate": False,
        "post_outcome_schedule_edits_allowed": False,
    }


def test_private_schedule_validates_and_public_receipt_leaks_no_candidate_refs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    candidate, evaluation = _public_inputs(repo)
    schedule_path = tmp_path / "private-field-schedule.json"
    schedule = _schedule(schedule_path, candidate, evaluation)
    _write(schedule_path, schedule)

    validated = validate_private_field_schedule(schedule_path, candidate, evaluation, repo_root=repo)
    assert validated["status"] == "PRIVATE_FIELD_ALLOCATION_AND_EFFORT_SCHEDULE_VALID"
    assert validated["assignment_count"] == 12
    for unit in EXPECTED_UNITS:
        assert set(validated["assignment_count_by_unit_arm"][unit]) == set(EXPECTED_ARMS)
        assert len(set(validated["matched_effort_totals_by_unit_arm"][unit].values())) == 1

    receipt = build_public_field_schedule_receipt(schedule_path, candidate, evaluation, repo_root=repo)
    assert receipt["status"] == PUBLIC_STATUS
    assert receipt["coordinate_bearing_data_included"] is False
    assert receipt["private_candidate_refs_included"] is False
    assert receipt["private_paths_included"] is False
    assert receipt["prospective_field_outcomes_opened"] is False
    assert receipt["outcome_opening_authorized_by_generation_alone"] is False
    rendered = json.dumps(receipt)
    assert "PRIVATE-CIR02" not in rendered
    assert str(tmp_path) not in rendered


def test_private_schedule_must_remain_outside_repository(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    candidate, evaluation = _public_inputs(repo)
    schedule_path = repo / "private-field-schedule.json"
    _write(schedule_path, _schedule(schedule_path, candidate, evaluation))
    with pytest.raises(ValueError, match="outside"):
        validate_private_field_schedule(schedule_path, candidate, evaluation, repo_root=repo)


def test_private_schedule_rejects_effort_mismatch_between_arms(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    candidate, evaluation = _public_inputs(repo)
    schedule_path = tmp_path / "private-field-schedule.json"
    value = _schedule(schedule_path, candidate, evaluation)
    value["assignments"][0]["planned_effort_value"] = 61.0
    _write(schedule_path, value)
    with pytest.raises(ValueError, match="not matched"):
        validate_private_field_schedule(schedule_path, candidate, evaluation, repo_root=repo)


def test_private_schedule_rejects_missing_method_arm(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    candidate, evaluation = _public_inputs(repo)
    schedule_path = tmp_path / "private-field-schedule.json"
    value = _schedule(schedule_path, candidate, evaluation)
    value["assignments"] = [
        row for row in value["assignments"]
        if not (row["cohort_unit_id"] == "CIR13" and row["method_arm"] == EXPECTED_ARMS[2])
    ]
    _write(schedule_path, value)
    with pytest.raises(ValueError, match="every frozen method arm"):
        validate_private_field_schedule(schedule_path, candidate, evaluation, repo_root=repo)


def test_private_schedule_rejects_wrong_candidate_receipt_hash(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    candidate, evaluation = _public_inputs(repo)
    schedule_path = tmp_path / "private-field-schedule.json"
    value = _schedule(schedule_path, candidate, evaluation)
    value["candidate_order_public_receipt_sha256"] = "0" * 64
    _write(schedule_path, value)
    with pytest.raises(ValueError, match="exact candidate/order"):
        validate_private_field_schedule(schedule_path, candidate, evaluation, repo_root=repo)


def test_private_schedule_rejects_outcome_field_in_assignment(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    candidate, evaluation = _public_inputs(repo)
    schedule_path = tmp_path / "private-field-schedule.json"
    value = _schedule(schedule_path, candidate, evaluation)
    value["assignments"][0]["field_outcome_state"] = "SEARCH_COMPLETED_DETECTED_VERIFIED"
    _write(schedule_path, value)
    with pytest.raises(ValueError, match="keys"):
        validate_private_field_schedule(schedule_path, candidate, evaluation, repo_root=repo)
