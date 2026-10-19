"""No-outcome, no-private-source regressions for optimistic site-only power scenarios."""
import json
import math
import pytest

from research.cirsium_topology_trial_effort_sensitivity_v1 import (
    SCHEMA, sample_size_scenario,
)


@pytest.mark.parametrize(("q", "theta", "n_arm", "person_hours"), [
    (0.25, 0.10, 5395, 16185.0),
    (0.25, 0.20, 1377, 4131.0),
    (0.50, 0.20, 356, 1068.0),
    (1.00, 0.20, 93, 279.0),
])
def test_optimistic_scenario_numbers(q, theta, n_arm, person_hours):
    x = sample_size_scenario(q, theta)
    assert x["required_per_arm"] == n_arm
    assert x["required_total_patches"] == 2 * n_arm
    assert x["optimistic_active_person_hours"] == person_hours
    assert x["assumed_intention_to_treat_difference"] == pytest.approx(q * theta)
    assert x["schema_version"] == SCHEMA
    assert x["status"] == "HYPOTHETICAL_NORMAL_APPROXIMATION_NOT_FIELD_EVIDENCE"
    assert x["real_new_cohort_q"] is None
    assert x["actual_cohort_field_ready"] is False
    assert x["prospective_outcomes_opened"] is False
    assert x["historical_cirsium_patch_outcomes_used"] is False
    assert not any("latitude" in key or "longitude" in key or "member_ids" in key for key in x)
    assert "CIR0" not in json.dumps(x)


def test_zero_q_or_zero_conditional_difference_has_no_finite_target():
    for q,theta in [(0.0,0.20),(0.5,0.0)]:
        x=sample_size_scenario(q,theta)
        assert x["required_per_arm"] is None
        assert x["required_total_patches"] is None
        assert x["optimistic_active_person_hours"] is None
        assert x["real_new_cohort_q"] is None


@pytest.mark.parametrize(("q","theta","p0"), [
    (-0.1,0.2,0.3),(1.01,0.2,0.3),
    (0.5,float("nan"),0.3),(0.5,2,0.3),
    (0.5,0.2,0.0),(0.5,0.2,1.0),
    (1.0,0.9,0.3),(1.0,-0.9,0.3),
    (True,0.2,0.3),
])
def test_impossible_assumptions_fail_closed(q,theta,p0):
    with pytest.raises(ValueError):
        sample_size_scenario(q,theta,p0)


def test_no_sites_outcomes_or_field_files_are_imported():
    x=sample_size_scenario(0.5,-0.1,0.5)
    assert x["required_total_patches"] > 0
    assert math.isfinite(x["optimistic_active_person_hours"])
    assert x["historical_cirsium_patch_outcomes_used"] is False
