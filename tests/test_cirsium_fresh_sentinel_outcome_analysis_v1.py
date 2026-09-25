from __future__ import annotations

from pathlib import Path

import pytest

import research.analyze_cirsium_fresh_sentinel_outcomes_v1 as analysis

UNITS = analysis.UNITS
ARMS = analysis.ARMS


def _schedule(*, two_visits_for: tuple[str, str] | None = None, shared_candidates: bool = False) -> dict:
    assignments = []
    for unit in UNITS:
        for arm_index, arm in enumerate(ARMS):
            candidate = f"{unit}-shared" if shared_candidates else f"{unit}-{arm_index}"
            analysis_unit = f"{unit}-analysis-{arm_index}"
            visit_count = 2 if two_visits_for == (unit, arm) else 1
            for visit in range(1, visit_count + 1):
                assignments.append({
                    "cohort_unit_id": unit,
                    "analysis_unit_id": analysis_unit,
                    "private_candidate_ref": candidate,
                    "method_arm": arm,
                    "visit_index": visit,
                    "planned_effort_value": 60.0,
                    "planned_search_minutes": 30.0,
                    "planned_observer_count": 2,
                })
    return {"assignments": assignments}


def _rows(schedule: dict, states: dict[tuple[str, str, int], str]) -> list[dict[str, str]]:
    rows = []
    for item in schedule["assignments"]:
        key = (item["cohort_unit_id"], item["method_arm"], item["visit_index"])
        state = states.get(key, analysis.NONDETECTED)
        rows.append({
            "analysis_unit_id": item["analysis_unit_id"],
            "visit_index": str(item["visit_index"]),
            "search_minutes": str(item["planned_search_minutes"]),
            "observer_count": str(item["planned_observer_count"]),
            "field_outcome_state": state,
        })
    return rows


def test_equal_taxon_macro_primary_is_computed_from_four_predeclared_taxa() -> None:
    schedule = _schedule()
    states = {
        ("CIR02", analysis.PRIMARY, 1): analysis.VERIFIED,
        ("CIR06", analysis.PRIMARY, 1): analysis.VERIFIED,
        ("CIR06", analysis.COVERAGE, 1): analysis.VERIFIED,
        ("CIR12", analysis.COVERAGE, 1): analysis.VERIFIED,
        ("CIR13", analysis.PRIMARY, 1): analysis.VERIFIED,
    }
    result = analysis.summarize_outcomes(schedule, _rows(schedule, states))
    assert result["status"] == "FRESH_SENTINEL_PROSPECTIVE_ANALYSIS_COMPLETE"
    primary = result["primary_estimand"]
    assert primary["per_taxon_contrast"] == {
        "CIR02": 1.0,
        "CIR06": 0.0,
        "CIR12": -1.0,
        "CIR13": 1.0,
    }
    assert primary["equal_taxon_macro_mean"] == pytest.approx(0.25)
    assert primary["taxon_weights"] == {unit: 0.25 for unit in UNITS}
    assert primary["dichotomous_pass_fail_threshold"] is None
    assert result["secondary_estimands"]["pooled_micro_descriptive_only"]["may_replace_primary"] is False
    assert set(result["sensitivity"]["leave_one_taxon_out_primary_macro"]) == set(UNITS)
    assert result["universal_promotion_authorized"] is False
    assert result["retuning_on_these_outcomes_authorized"] is False


def test_one_non_evaluable_taxon_makes_primary_macro_not_evaluable_without_dropping_taxon() -> None:
    schedule = _schedule()
    states = {
        ("CIR02", analysis.PRIMARY, 1): analysis.VERIFIED,
        ("CIR06", analysis.PRIMARY, 1): analysis.VERIFIED,
        ("CIR12", analysis.PRIMARY, 1): analysis.VERIFIED,
        ("CIR13", analysis.PRIMARY, 1): analysis.VERIFIED,
        ("CIR13", analysis.COVERAGE, 1): "ACCESS_FAILED",
    }
    result = analysis.summarize_outcomes(schedule, _rows(schedule, states))
    assert result["status"] == analysis.PRIMARY_NOT_EVALUABLE
    primary = result["primary_estimand"]
    assert primary["per_taxon_contrast"]["CIR13"] is None
    assert primary["equal_taxon_macro_mean"] is None
    assert result["sensitivity"]["leave_one_taxon_out_primary_macro"] is None


def test_repeated_visit_aggregation_follows_frozen_precedence() -> None:
    schedule = _schedule(two_visits_for=("CIR02", analysis.PRIMARY))
    states = {
        ("CIR02", analysis.PRIMARY, 1): analysis.UNRESOLVED,
        ("CIR02", analysis.PRIMARY, 2): analysis.VERIFIED,
    }
    result = analysis.summarize_outcomes(schedule, _rows(schedule, states))
    target = result["by_taxon_by_arm"]["CIR02"][analysis.PRIMARY]
    assert target["resolved_verified_detection_count"] == 1
    assert target["identity_unresolved_analysis_unit_count"] == 0
    assert target["resolved_binary_denominator"] == 1
    assert target["resolved_binary_success_proportion"] == 1.0


def test_mixed_non_detection_and_access_failure_stays_outside_resolved_denominator() -> None:
    schedule = _schedule(two_visits_for=("CIR02", analysis.PRIMARY))
    states = {
        ("CIR02", analysis.PRIMARY, 1): analysis.NONDETECTED,
        ("CIR02", analysis.PRIMARY, 2): "ACCESS_FAILED",
    }
    result = analysis.summarize_outcomes(schedule, _rows(schedule, states))
    target = result["by_taxon_by_arm"]["CIR02"][analysis.PRIMARY]
    assert target["resolved_verified_detection_count"] == 0
    assert target["resolved_non_detection_count"] == 0
    assert target["non_biological_or_non_evaluable_analysis_unit_count"] == 1
    assert target["resolved_binary_denominator"] == 0
    assert target["resolved_binary_success_proportion"] is None


def test_shared_candidate_overlap_is_reported_as_counts_without_candidate_ids() -> None:
    schedule = _schedule(shared_candidates=True)
    result = analysis.summarize_outcomes(schedule, _rows(schedule, {}))
    for unit in UNITS:
        assert result["cross_arm_shared_candidate_overlap_counts"][unit]["all_three_arms"] == 1
    rendered = str(result)
    assert "CIR02-shared" not in rendered


def test_executable_refuses_to_read_outcomes_when_pre_outcome_gate_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    touched = False

    def fail_gate(*args, **kwargs):
        raise ValueError("pre-outcome gate closed")

    def should_not_read(*args, **kwargs):
        nonlocal touched
        touched = True
        raise AssertionError("outcomes must not be read")

    monkeypatch.setattr(analysis, "verify_pre_outcome_gate", fail_gate)
    monkeypatch.setattr(analysis, "_read_rows", should_not_read)
    with pytest.raises(ValueError, match="pre-outcome gate closed"):
        analysis.analyze_prospective_outcomes(
            tmp_path / "outcomes.csv",
            tmp_path / "private-schedule.json",
            repo_root=tmp_path,
        )
    assert touched is False
