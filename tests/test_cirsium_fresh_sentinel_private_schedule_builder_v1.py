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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_order(path: Path, ids: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["candidate_cell_id", "decision_rank"])
        writer.writeheader()
        for rank, value in enumerate(ids, 1):
            writer.writerow({"candidate_cell_id": value, "decision_rank": rank})


def _write_frame(path: Path, unit: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "candidate_cell_id,latitude,longitude,coverage_cell_id\n"
        f"{unit}_frame,35.0,139.0,{unit}_cov\n",
        encoding="utf-8",
    )


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


def _effort() -> dict:
    return {
        "schema_version": "cirsium-fresh-sentinel-standardized-effort-protocol-v1",
        "status": "PRE_OUTCOME_STANDARDIZED_EFFORT_PROTOCOL_FROZEN",
        "cohort_unit_ids": list(builder.UNITS),
        "protocol_source_identity": "SYNTHETIC_TEST_PROTOCOL",
        "unit_effort": {
            unit: {
                "visits_per_candidate": 2,
                "search_minutes_per_visit": 15,
                "observer_count": 2,
            }
            for unit in builder.UNITS
        },
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used_to_set_effort": False,
        "candidate_identity_used_to_set_effort": False,
        "arm_specific_effort_allowed": False,
        "movement_constraint_used_to_set_effort": False,
        "post_outcome_effort_edits_allowed": False,
    }


def _capacity(private: Path, effort_path: Path, depth: int = 2) -> dict:
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
        "capacity_source_identity": "OSM_COMPLETE_COARSE_COVERAGE_SELECTED_COUNT_V1",
        "movement_constraint_mode": "osm_weighted_transport_network",
        "max_network_transition_km": 5.0,
        "automatic_prefix_depth_method": "OSM_COMPLETE_COARSE_COVERAGE_SELECTED_COUNT_V1",
        "coarse_redundancy_scale_m": 5000.0,
        "coarse_representative_rule": "STABLE_HASH_WITHIN_FROZEN_COARSE_CELL_V1",
        "standardized_effort_protocol_sha256": _sha256(effort_path),
        "private_candidate_frame_sha256_by_unit": {
            unit: _sha256(private / unit / "candidate_frame_pre_field.csv")
            for unit in builder.UNITS
        },
        "unit_capacity": {unit: dict(row) for unit in builder.UNITS},
        "movement_provider_successful_by_unit": {unit: True for unit in builder.UNITS},
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used_to_set_capacity": False,
        "frozen_common_candidate_geometry_used_for_movement_capacity": True,
        "arm_rank_used_to_set_prefix_depth": False,
        "candidate_identity_or_coordinates_exported": False,
        "structural_score_used_to_set_prefix_depth": False,
        "arm_specific_capacity_allowed": False,
        "survey_days_input": False,
        "monetary_budget_input": False,
        "user_site_count_input": False,
        "user_coverage_target_input": False,
        "post_outcome_capacity_edits_allowed": False,
    }


def _prepare_private(private: Path, *, order_len: int = 3) -> None:
    for unit in builder.UNITS:
        _write_frame(private / unit / "candidate_frame_pre_field.csv", unit)
        order_files = {}
        for arm_index, order_name in enumerate(builder.ARM_TO_ORDER.values()):
            name = f"order_{order_name}.csv"
            order_files[order_name] = name
            _write_order(
                private / unit / name,
                [f"{unit}_{arm_index}_r{rank}" for rank in range(1, order_len + 1)],
            )
        _write_json(
            private / unit / "pre_field_freeze_receipt.json",
            {
                "status": "PRE_FIELD_METHOD_AND_COMPARATORS_FROZEN",
                "order_files": order_files,
            },
        )


def test_builder_uses_exact_no_skip_prefix_and_arm_symmetric_effort(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    private = tmp_path / "private"
    candidate = repo / "validation" / "candidate.json"
    evaluation = repo / "validation" / "evaluation.json"
    effort = tmp_path / "effort.json"
    capacity = tmp_path / "capacity.json"
    out = tmp_path / "schedule.json"
    _prepare_private(private)
    _write_json(candidate, {"status": "PUBLIC_HASH_FREEZE_READY_FOR_COMMIT"})
    _write_json(evaluation, _evaluation())
    _write_json(effort, _effort())
    _write_json(capacity, _capacity(private, effort))

    monkeypatch.setattr(builder, "validate_private_field_schedule", lambda *a, **k: {"status": "PRIVATE_FIELD_ALLOCATION_AND_EFFORT_SCHEDULE_VALID"})
    monkeypatch.setattr(builder, "validate_private_schedule_membership", lambda *a, **k: {"status": "PRIVATE_FIELD_SCHEDULE_MEMBERSHIP_AND_PREFIX_VALID"})

    result = builder.build_private_field_schedule(private, candidate, evaluation, capacity, effort, out, repo_root=repo)
    schedule = json.loads(out.read_text())
    assert result["status"] == "PRIVATE_FIELD_SCHEDULE_BUILT_AND_VALIDATED"
    assert result["movement_constraint_mode"] == "osm_weighted_transport_network"
    assert result["max_network_transition_km"] == 5.0
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


def test_capacity_profile_forbids_manual_or_outcome_informed_capacity(tmp_path: Path) -> None:
    private = tmp_path / "private"
    effort = tmp_path / "effort.json"
    _prepare_private(private)
    _write_json(effort, _effort())

    value = _capacity(private, effort)
    value["arm_specific_capacity_allowed"] = True
    with pytest.raises(ValueError, match="arm_specific_capacity_allowed"):
        builder._validate_capacity_profile(value)

    value = _capacity(private, effort)
    value["field_outcomes_used_to_set_capacity"] = True
    with pytest.raises(ValueError, match="field_outcomes_used_to_set_capacity"):
        builder._validate_capacity_profile(value)

    value = _capacity(private, effort)
    value["user_site_count_input"] = True
    with pytest.raises(ValueError, match="user_site_count_input"):
        builder._validate_capacity_profile(value)


def test_builder_rejects_capacity_bound_to_different_private_frame(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    private = tmp_path / "private"
    candidate = repo / "validation" / "candidate.json"
    evaluation = repo / "validation" / "evaluation.json"
    effort = tmp_path / "effort.json"
    capacity = tmp_path / "capacity.json"
    out = tmp_path / "schedule.json"
    _prepare_private(private)
    _write_json(candidate, {"status": "PUBLIC_HASH_FREEZE_READY_FOR_COMMIT"})
    _write_json(evaluation, _evaluation())
    _write_json(effort, _effort())
    frozen_capacity = _capacity(private, effort)
    _write_json(capacity, frozen_capacity)
    (private / "CIR12" / "candidate_frame_pre_field.csv").write_text("changed\n", encoding="utf-8")

    monkeypatch.setattr(builder, "validate_private_field_schedule", lambda *a, **k: {"status": "ok"})
    monkeypatch.setattr(builder, "validate_private_schedule_membership", lambda *a, **k: {"status": "ok"})
    with pytest.raises(ValueError, match="exact frozen private candidate frame"):
        builder.build_private_field_schedule(private, candidate, evaluation, capacity, effort, out, repo_root=repo)
    assert not out.exists()


def test_builder_fails_closed_when_requested_prefix_exceeds_frozen_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    private = tmp_path / "private"
    candidate = repo / "validation" / "candidate.json"
    evaluation = repo / "validation" / "evaluation.json"
    effort = tmp_path / "effort.json"
    capacity = tmp_path / "capacity.json"
    out = tmp_path / "schedule.json"
    _prepare_private(private, order_len=2)
    _write_json(candidate, {"status": "PUBLIC_HASH_FREEZE_READY_FOR_COMMIT"})
    _write_json(evaluation, _evaluation())
    _write_json(effort, _effort())
    _write_json(capacity, _capacity(private, effort, depth=3))
    monkeypatch.setattr(builder, "validate_private_field_schedule", lambda *a, **k: {"status": "ok"})
    monkeypatch.setattr(builder, "validate_private_schedule_membership", lambda *a, **k: {"status": "ok"})
    with pytest.raises(ValueError, match="exceeds frozen order length"):
        builder.build_private_field_schedule(private, candidate, evaluation, capacity, effort, out, repo_root=repo)
    assert not out.exists()
