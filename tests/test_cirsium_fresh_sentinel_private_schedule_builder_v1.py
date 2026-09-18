from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

import research.build_cirsium_fresh_sentinel_private_field_schedule_v1 as builder


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _write_order(path: Path, ids: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["candidate_cell_id", "decision_rank"])
        writer.writeheader()
        for rank, value in enumerate(ids, 1):
            writer.writerow({"candidate_cell_id": value, "decision_rank": rank})


def _evaluation() -> dict:
    return {
        "analysis_unit_and_repeated_visits": {
            "primary_analysis_unit_identity": "COHORT_ARM_CANDIDATE_V1",
            "repeated_visit_aggregation_identity": "ANY_VERIFIED_DETECTION_ELSE_ALL_RESOLVED_NONDETECTION_V1",
            "repeated_visit_aggregation_rule": "fixed repeat rule",
            "shared_candidate_handling_identity": "RETAIN_IN_EACH_NOMINATING_ARM_WITH_SHARED_OBSERVATION_V1",
            "shared_candidate_handling_rule": "fixed shared-candidate rule",
        },
        "schedule_selection_mechanics": {
            "comparator_assignment_identity": "FROZEN_ORDER_PREFIX_V1",
            "arm_symmetry_identity": "ARM_SYMMETRIC_PREFIX_EFFORT_TEMPLATE_V1",
        },
        "effort_accounting": {
            "numeric_effort_metric": {
                "identity": "PERSON_MINUTES_V1",
                "unit": "person-minute",
                "formula": "search_minutes * observer_count",
            }
        },
    }


def _capacity(depth: int = 2) -> dict:
    row = {
        "prefix_depth": depth,
        "visits_per_candidate": 2,
        "search_minutes_per_visit": 15,
        "observer_count": 2,
    }
    return {
        "schema_version": builder.PROFILE_SCHEMA,
        "status": builder.PROFILE_STATUS,
        "cohort_unit_ids": list(builder.UNITS),
        "capacity_source_identity": "SYNTHETIC_G_F_TEST",
        "unit_capacity": {unit: dict(row) for unit in builder.UNITS},
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used_to_set_capacity": False,
        "arm_specific_capacity_allowed": False,
        "post_outcome_capacity_edits_allowed": False,
    }


def test_builder_uses_exact_no_skip_prefix_and_arm_symmetric_effort(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    private = tmp_path / "private"
    candidate = repo / "validation" / "candidate.json"
    evaluation = repo / "validation" / "evaluation.json"
    capacity = tmp_path / "capacity.json"
    out = tmp_path / "schedule.json"
    _write_json(candidate, {"status": "PUBLIC_HASH_FREEZE_READY_FOR_COMMIT"})
    _write_json(evaluation, _evaluation())
    _write_json(capacity, _capacity())

    for unit in builder.UNITS:
        order_files = {}
        for arm_index, order_name in enumerate(builder.ARM_TO_ORDER.values()):
            name = f"order_{order_name}.csv"
            order_files[order_name] = name
            _write_order(private / unit / name, [f"{unit}_{arm_index}_r1", f"{unit}_{arm_index}_r2", f"{unit}_{arm_index}_r3"])
        _write_json(private / unit / "pre_field_freeze_receipt.json", {
            "status": "PRE_FIELD_METHOD_AND_COMPARATORS_FROZEN",
            "order_files": order_files,
        })

    monkeypatch.setattr(builder, "validate_private_field_schedule", lambda *a, **k: {"status": "PRIVATE_FIELD_ALLOCATION_AND_EFFORT_SCHEDULE_VALID"})
    monkeypatch.setattr(builder, "validate_private_schedule_membership", lambda *a, **k: {"status": "PRIVATE_FIELD_SCHEDULE_MEMBERSHIP_AND_PREFIX_VALID"})

    result = builder.build_private_field_schedule(private, candidate, evaluation, capacity, out, repo_root=repo)
    schedule = json.loads(out.read_text())
    assert result["status"] == "PRIVATE_FIELD_SCHEDULE_BUILT_AND_VALIDATED"
    assert len(schedule["assignments"]) == 4 * 3 * 2 * 2
    assert schedule["field_outcomes_used_to_allocate"] is False
    assert schedule["arm_symmetry_identity"] == "ARM_SYMMETRIC_PREFIX_EFFORT_TEMPLATE_V1"

    for unit in builder.UNITS:
        for arm in builder.ARMS:
            rows = [r for r in schedule["assignments"] if r["cohort_unit_id"] == unit and r["method_arm"] == arm]
            assert len({r["private_candidate_ref"] for r in rows}) == 2
            assert {r["visit_index"] for r in rows} == {1, 2}
            assert {r["planned_search_minutes"] for r in rows} == {15.0}
            assert {r["planned_observer_count"] for r in rows} == {2}
            assert {r["planned_effort_value"] for r in rows} == {30.0}


def test_capacity_profile_forbids_arm_specific_or_outcome_informed_capacity() -> None:
    value = _capacity()
    value["arm_specific_capacity_allowed"] = True
    with pytest.raises(ValueError, match="arm-specific"):
        builder._validate_capacity_profile(value)
    value = _capacity()
    value["field_outcomes_used_to_set_capacity"] = True
    with pytest.raises(ValueError, match="cannot define"):
        builder._validate_capacity_profile(value)


def test_builder_fails_closed_when_requested_prefix_exceeds_frozen_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    private = tmp_path / "private"
    candidate = repo / "validation" / "candidate.json"
    evaluation = repo / "validation" / "evaluation.json"
    capacity = tmp_path / "capacity.json"
    out = tmp_path / "schedule.json"
    _write_json(candidate, {"status": "PUBLIC_HASH_FREEZE_READY_FOR_COMMIT"})
    _write_json(evaluation, _evaluation())
    _write_json(capacity, _capacity(depth=3))
    for unit in builder.UNITS:
        order_files = {}
        for order_name in builder.ARM_TO_ORDER.values():
            name = f"order_{order_name}.csv"
            order_files[order_name] = name
            _write_order(private / unit / name, [f"{unit}_{order_name}_r1", f"{unit}_{order_name}_r2"])
        _write_json(private / unit / "pre_field_freeze_receipt.json", {
            "status": "PRE_FIELD_METHOD_AND_COMPARATORS_FROZEN",
            "order_files": order_files,
        })
    monkeypatch.setattr(builder, "validate_private_field_schedule", lambda *a, **k: {"status": "ok"})
    monkeypatch.setattr(builder, "validate_private_schedule_membership", lambda *a, **k: {"status": "ok"})
    with pytest.raises(ValueError, match="exceeds frozen order length"):
        builder.build_private_field_schedule(private, candidate, evaluation, capacity, out, repo_root=repo)
    assert not out.exists()
