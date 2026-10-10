from __future__ import annotations

import json
from pathlib import Path

from research.cirsium_fresh_sentinel_paths_v1 import (
    CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH,
)
from research.derive_cirsium_fresh_sentinel_movement_capacity_v1 import (
    validate_effort_protocol,
)

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH
UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")


def test_canonical_standardized_effort_instance_is_frozen_and_uniform() -> None:
    value = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    normalized = validate_effort_protocol(value)

    assert value["protocol_source_identity"] == "ACSP_CIRSIUM_FIXED_TIMED_SEARCH_3X30MIN_1OBSERVER_V1"
    assert tuple(value["cohort_unit_ids"]) == UNITS
    assert value["prospective_field_outcomes_opened"] is False
    assert value["field_outcomes_used_to_set_effort"] is False
    assert value["candidate_identity_used_to_set_effort"] is False
    assert value["arm_specific_effort_allowed"] is False
    assert value["movement_constraint_used_to_set_effort"] is False
    assert value["post_outcome_effort_edits_allowed"] is False

    expected = {
        "visits_per_candidate": 3,
        "search_minutes_per_visit": 30.0,
        "observer_count": 1,
    }
    assert normalized == {unit: expected for unit in UNITS}
    assert {
        normalized[unit]["visits_per_candidate"]
        * normalized[unit]["search_minutes_per_visit"]
        * normalized[unit]["observer_count"]
        for unit in UNITS
    } == {90.0}


def test_effort_protocol_remains_independent_of_candidate_and_movement_inputs() -> None:
    value = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    rendered = json.dumps(value, sort_keys=True)
    for forbidden in (
        "candidate_cell_id",
        "latitude",
        "longitude",
        "coverage_cell_id",
        "max_network_transition_km",
        "survey_days",
        "monetary_budget",
    ):
        assert forbidden not in rendered
