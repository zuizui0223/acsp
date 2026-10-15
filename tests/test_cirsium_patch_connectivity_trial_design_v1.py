"""Pre-field connectivity-overlay trial: synthetic-only, no field outcomes."""
from __future__ import annotations

import json
from pathlib import Path
import re
import pytest

from research.design_cirsium_patch_connectivity_field_trial_v1 import (
    build_private_trial_assignments,
    choose_counterfactual_sites,
    connected_components,
    public_design_receipt,
    validate_design_contract,
)


def patch(unit="NEW01", name="sensitive-patch", row_shift=0):
    # Three separated Moore8 components; all cells in a 1 km diameter.
    positions = [(0, c) for c in range(4)] + [(5, c) for c in range(3)] + [(9, c) for c in range(3)]
    return {
        "cohort_unit_id": unit,
        "patch_ref": name,
        "member_ids": [f"{unit}_r{r+row_shift}_c{c}" for r, c in positions],
        "patch_diameter_limit_m": 1000,
    }


def test_original_geometry_medoid_differs_from_largest_component_site():
    selection = choose_counterfactual_sites(patch())
    assert selection["eligible_disconnected"] is True
    assert selection["within_patch_components"] == 3
    assert selection["selected_by_topology"] == "NEW01_r0_c1"
    assert selection["selected_by_geometry"] in {"NEW01_r5_c0", "NEW01_r5_c1", "NEW01_r5_c2"}
    assert selection["counterfactual_site_shared"] is False


def test_diagonal_eight_neighbour_and_connected_patch_exclusion():
    assert len(connected_components({(0, 0), (1, 1), (4, 4)})) == 2
    q = {"cohort_unit_id": "NEW01", "patch_ref": "patch1", "member_ids": ["NEW01_r0_c0", "NEW01_r1_c1"]}
    s = choose_counterfactual_sites(q)
    assert s["eligible_disconnected"] is False
    assert s["within_patch_components"] == 1


def test_outcome_blind_hash_allocation_reproduces_and_balances_by_unit():
    values = [patch(name=f"private-patch-{i}", row_shift=30*i) for i in range(8)]
    first = build_private_trial_assignments(values)
    second = build_private_trial_assignments(list(reversed(values)))
    assert first == second
    arms = [x["assigned_arm"] for x in first["assigned"]]
    assert arms.count("TOPOLOGY") == arms.count("GEOMETRY") == 4
    assert first["unassigned_balance_reserve"] == []
    assert all(x["planned_person_minutes"] == 90 and x["visits"] == 3 for x in first["assigned"])


def test_odd_patch_is_preoutcome_unassigned_balance_reserve():
    values = [patch(name=f"private-{i}", row_shift=25*i) for i in range(5)]
    r = build_private_trial_assignments(values)
    assert len(r["assigned"]) == 4
    assert len(r["unassigned_balance_reserve"]) == 1
    assert [x["assigned_arm"] for x in r["assigned"]].count("TOPOLOGY") == 2
    assert [x["assigned_arm"] for x in r["assigned"]].count("GEOMETRY") == 2


def test_minimum_two_eligible_patches_for_estimand():
    r = build_private_trial_assignments([patch()])
    assert r["assigned"] == []
    assert len(r["unassigned_balance_reserve"]) == 1
    assert r["can_schedule_equal_effort"] is False
    public=public_design_receipt(r)
    assert public["by_cohort"]["NEW01"]["balance_reserve_count"] == 1
    assert public["by_cohort"]["NEW01"]["assigned_topology"] == 0
    assert public["by_cohort"]["NEW01"]["assigned_geometry"] == 0


def test_shared_site_counterfactual_preserved_not_removed():
    rows = ["NEW01_r0_c0", "NEW01_r0_c1", "NEW01_r5_c0"]
    x = choose_counterfactual_sites({"cohort_unit_id":"NEW01","patch_ref":"p","member_ids":rows})
    assert x["eligible_disconnected"] is True
    assert x["counterfactual_site_shared"] is True
    # Whatever the coincidence, retain as an eligible patch and document it.
    assert x["selected_by_geometry"] in rows
    assert x["selected_by_topology"] in rows


@pytest.mark.parametrize("invalid", [
    lambda p: {**p, "member_ids": p["member_ids"][:-1] + [p["member_ids"][0]]},
    lambda p: {**p, "member_ids": p["member_ids"] + ["NEW01_r99_c99"]},
    lambda p: {**p, "member_ids": p["member_ids"][:-1] + ["OTHER_r9_c2"]},
    lambda p: {**p, "member_ids": p["member_ids"][:-1] + ["NEW01_rnotint_c0"]},
])
def test_rejects_duplicate_out_of_diameter_wrong_unit_bad_lattice(invalid):
    with pytest.raises(ValueError):
        choose_counterfactual_sites(invalid(patch()))


def test_public_receipt_never_exports_site_or_patch_ids():
    assigned = build_private_trial_assignments([patch(name="SECRET_PATCH_B",row_shift=0), patch(name="SECRET_PATCH_A",row_shift=20)])
    receipt = public_design_receipt(assigned)
    encoded=json.dumps(receipt,sort_keys=True)
    for forbidden in ("SECRET_PATCH", "NEW01_r", "private_candidate_ref", "longitude", "latitude", "member_ids", "site_ref"):
        assert forbidden not in encoded
    assert re.fullmatch(r"[0-9a-f]{64}",receipt["private_assignments_sha256"])
    assert receipt["by_cohort"]["NEW01"]["assigned_topology"] == 1
    assert receipt["by_cohort"]["NEW01"]["assigned_geometry"] == 1
    assert receipt["field_outcomes_opened"] is False
    assert receipt["field_schedule_frozen"] is False


def test_original_exposed_units_never_claim_fresh_biological_confirmation():
    r=build_private_trial_assignments([patch(unit="CIR02",name="x"),patch(unit="CIR02",name="y",row_shift=20)])
    public=public_design_receipt(r)
    assert public["by_cohort"]["CIR02"]["cohort_exposure"] == "PREVIOUSLY_EXPOSED_DEVELOPMENT_ONLY"
    assert public["fresh_independent_biological_validation"] is False


def test_contract_freezes_distinct_scientific_lanes_and_existing_effort():
    d=validate_design_contract()
    assert d["status"] == "METHOD_DESIGN_FROZEN_BEFORE_NEW_COHORT_SELECTION_NO_OUTCOMES"
    assert d["cohort_identity_frozen"] is False
    assert d["field_schedule_frozen"] is False
    assert d["outcomes_may_be_opened"] is False
    assert d["original_three_arm_fresh_sentinel_protocol_changed"] is False
    assert d["strategy"]["topology"] == "LARGEST_MOORE8_COMPONENT_MEDOID_V1"
    assert d["strategy"]["geometry"] == "ALL_RETAINED_PATCH_CELLS_MEDOID_V1"
    assert d["effort"]["planned_person_minutes_per_assigned_candidate"] == 90
    assert d["sampling"]["only_internal_disconnected_patches"] is True
    assert d["sampling"]["projection_identity"] == "JAPAN_CENTERED_AEQD_V1"
    assert d["claim_limits"]["topological_high_support_is_habitat_continuity"] is False


def test_two_arms_in_one_unit_do_not_change_original_patch_member_sets():
    p0=patch(name="a");p1=patch(name="b",row_shift=20)
    before=[tuple(x["member_ids"]) for x in (p0,p1)]
    build_private_trial_assignments([p0,p1])
    assert [tuple(x["member_ids"]) for x in (p0,p1)] == before


def test_private_assignment_cannot_share_patch_id_with_different_membership():
    a=patch(name="x");b=patch(name="x",row_shift=20)
    with pytest.raises(ValueError,match="duplicate private patch"):
        build_private_trial_assignments([a,b])


def test_connected_only_cohort_is_reported_as_ineligible_not_discarded():
    p={"cohort_unit_id":"FRESH12","patch_ref":"masked-private-ref","member_ids":["FRESH12_r0_c0","FRESH12_r0_c1"]}
    private=build_private_trial_assignments([p])
    public=public_design_receipt(private)
    assert public["by_cohort"]["FRESH12"]["ineligible_connected_patch_count"]==1
    assert public["by_cohort"]["FRESH12"]["assigned_topology"]==0
    assert public["field_schedule_frozen"] is False
