from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COHORT_PATH = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_cohort_v1.csv"
FREEZE_PATH = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_freeze_v1.json"
SOURCE_COHORT_PATH = ROOT / "validation" / "cirsium_aza3_prospective_validation_cohort_v1.csv"

EXPECTED_UNITS = ["CIR02", "CIR06", "CIR12", "CIR13"]
OPENED_DEVELOPMENT_UNITS = {"CIR01", "CIR04", "CIR07", "CIR08"}


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_fresh_sentinel_cohort_is_exact_unopened_sentinel_subset() -> None:
    source = {row["cohort_unit_id"]: row for row in _rows(SOURCE_COHORT_PATH)}
    frozen = _rows(COHORT_PATH)

    assert [row["cohort_unit_id"] for row in frozen] == EXPECTED_UNITS
    assert len(frozen) == len(EXPECTED_UNITS)

    for row in frozen:
        unit = row["cohort_unit_id"]
        src = source[unit]
        assert src["occurrence_problem_class"] == "SENTINEL"
        assert src["outcome_opened"].lower() == "false"
        assert src["field_performance_denominator"].lower() == "true"
        assert src["sentinel_subregime"] == row["sentinel_subregime"]
        assert src["sentinel_evidence_class"] == row["sentinel_evidence_class"]
        assert src["structural_feature_family"] == row["structural_feature_family"]
        assert src["habitat_evidence_source"] == row["habitat_evidence_source"]
        assert src["habitat_evidence_statement"] == row["habitat_evidence_statement"]
        assert row["outcome_opened"].lower() == "false"
        assert row["prior_structural_holdout_consumed"].lower() == "false"
        assert row["fresh_field_outcome_eligible"].lower() == "true"
        assert row["execution_status"] == "BLOCKED_PRIVATE_SOURCE_FREEZE"
        assert unit not in OPENED_DEVELOPMENT_UNITS


def test_freeze_contract_preserves_scale_separation_and_fail_closed_source_boundary() -> None:
    freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))

    assert freeze["status"] == "FROZEN_PRE_FIELD_OUTCOME_SOURCE_BLOCKED"
    assert freeze["method_identity"] == "COVERAGE_THEN_FINE_STRUCTURE_V1"
    assert freeze["selection_rule"]["selected_units"] == EXPECTED_UNITS
    assert freeze["selection_rule"]["no_replacement_after_source_or_frame_failure"] is True

    boundary = freeze["frozen_method_boundary"]
    assert boundary["fine_candidate_spacing_m"] == 100
    assert boundary["coarse_coverage_cell_size_m"] == 5000
    assert boundary["cross_cell_structural_score_comparison"] is False
    assert boundary["coverage_structure_weight"] is None
    assert boundary["budget_parameter"] is None
    assert boundary["known_point_kernel_for_sentinel"] is False

    assert freeze["comparators_to_freeze_before_execution"]["nearest_known"].startswith("NOT_DEFINED_FOR_SENTINEL")
    assert freeze["prefix_curve"]["fractions"] == [0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1.0]
    assert freeze["prefix_curve"]["favorable_prefix_selection_allowed"] is False

    policy = freeze["source_failure_policy"]
    assert policy["provider_relaxation"] is False
    assert policy["cohort_replacement"] is False
    assert policy["family_switch"] is False
    assert policy["subregime_switch"] is False
    assert policy["invented_geometry"] is False
    assert freeze["execution_blocker"]["current"] is True


def test_opened_and_local_units_cannot_enter_fresh_sentinel_freeze() -> None:
    freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    selected = set(freeze["selection_rule"]["selected_units"])
    exclusions = freeze["explicit_exclusions"]

    assert selected.isdisjoint(OPENED_DEVELOPMENT_UNITS)
    assert OPENED_DEVELOPMENT_UNITS == set(exclusions["opened_structural_holdout_units"]) | set(exclusions["opened_coastal_development_unit"])
    assert selected.isdisjoint(set(exclusions["local_lane_not_in_v1_scope"]))
