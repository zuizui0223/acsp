"""Secondary component-count synthesis: synthetic tests plus frozen fixture parity."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from research.summarize_cirsium_frozen_patch_topology_gap import (
    build_topology_component_gap,
    verify_saved_summary,
)

ROOT = Path(__file__).resolve().parents[1]
UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
FAMILIES = {
    "CIR02": "WETLAND_MOISTURE_STRUCTURE",
    "CIR06": "ALPINE_TOPOGRAPHIC_STRUCTURE",
    "CIR12": "OPEN_GRASSLAND_STRUCTURE",
    "CIR13": "OPEN_GRASSLAND_STRUCTURE",
}


def fixtures():
    # Each isolated fixture exercises the contract; the real frozen result is
    # read separately, never relabeled as an untouched biological test.
    rows = {
        "CIR02": (573, 320, 9546, 3472, 807, 588, 7),
        "CIR06": (3883, 3292, 20409, 19313, 10892, 7837, 10),
        "CIR12": (654, 278, 15187, 4767, 505, 398, 6),
        "CIR13": (654, 278, 15187, 4767, 505, 398, 6),
    }
    result = {
        "schema_version": "coverage-then-fine-structure-fresh-sentinel-v2-frozen-patch-topology-result-v1",
        "status": "FOUR_UNIT_FROZEN_PATCH_MASK_TOPOLOGY_COMPLETE_PRE_OUTCOME",
        "source_pr": 256, "source_run_id": 37732320419,
        "distinct_declared_structural_family_count": 3,
        "cohort_unit_ids": list(UNITS), "units": {},
        "interpretation": {
            "topology_only": True,
            "exact_original_frozen_patch_bytes_verified_all_four": True,
            "connectedness_of_retained_2p5pct_mask_not_habitat_connectivity": True,
            "full_structural_order_sha_replay_tested_by_this_route": False,
            "prospective_field_outcomes_opened": False,
            "species_specific_selector_independence_claimed": False,
            "field_selector_validation": False,
        },
    }
    frozen = {"status": "FINE_PATCH_REPRESENTATION_FEASIBLE_SELECTOR_UNVALIDATED",
              "source_pr": 247, "transferred_constants": {
                  "support_fraction": 0.025, "complete_link_max_distance_m": 1000}, "units": {}}
    for unit, (patches, disconnected, cells, in_disconnected, global_components, extras, largest) in rows.items():
        fake_sha = {"CIR02": "a", "CIR06": "b", "CIR12": "c", "CIR13": "d"}[unit] * 64
        result["units"][unit] = {
            "feature_family": FAMILIES[unit],
            "verified_original_patch_sha256": fake_sha,
            "retained_support_cell_count": cells,
            "complete_link_patch_count": patches,
            "connected_patch_count": patches - disconnected,
            "disconnected_patch_count": disconnected,
            "disconnected_patch_fraction": disconnected/patches,
            "cells_in_disconnected_patches": in_disconnected,
            "cells_in_disconnected_patch_fraction": in_disconnected/cells,
            "global_mask_component_count": global_components,
            "extra_within_patch_components": extras,
            "maximum_components_per_patch": largest,
            "original_frozen_singleton_patch_count": 1,
            "all_retained_cells_accounted_for": True,
            "ecological_connectivity_claim_authorized": False,
            "source_integrity_claim_authorized": False,
        }
        frozen["units"][unit] = {
            "private_patch_sha256": fake_sha,
            "complete_link_patch_count": patches,
            "transferred_2p5pct_retained_cell_count": cells,
        }
    return result, frozen


def test_signed_component_gap_and_two_mechanisms_are_consistent():
    source, frozen = fixtures()
    answer = build_topology_component_gap(source, frozen)
    expected = {
        "CIR02": (1161, 354, 234, "MORE_COMPONENTS_THAN_PATCHES"),
        "CIR06": (11720, 828, 7009, "MORE_COMPONENTS_THAN_PATCHES"),
        "CIR12": (1052, 547, -149, "FEWER_COMPONENTS_THAN_PATCHES"),
        "CIR13": (1052, 547, -149, "FEWER_COMPONENTS_THAN_PATCHES"),
    }
    for unit, (total, unions, gap, label) in expected.items():
        row = answer["units"][unit]
        assert row["within_patch_component_total"] == total
        assert row["net_cross_patch_component_unions"] == unions
        assert row["global_components_minus_patches"] == gap
        assert row["gap_direction"] == label
        assert row["global_components_per_patch"] == pytest.approx(row["global_mask_component_count"] / row["complete_link_patch_count"])
    assert answer["claims"]["treat_four_units_as_independent_ecological_replicates"] is False
    assert answer["claims"]["use_connected_component_count_as_field_visit_count"] is False


def test_arithmetic_identity_and_component_constraints_hold():
    s, f = fixtures()
    a = build_topology_component_gap(s, f)
    for unit in UNITS:
        row = a["units"][unit]
        assert row["within_patch_component_total"] == row["complete_link_patch_count"] + row["extra_within_patch_components"]
        assert row["net_cross_patch_component_unions"] == row["within_patch_component_total"] - row["global_mask_component_count"]
        assert row["global_components_minus_patches"] == row["extra_within_patch_components"] - row["net_cross_patch_component_unions"]


def test_patch_fraction_and_cell_fraction_are_not_confused():
    s, f = fixtures()
    a = build_topology_component_gap(s, f)
    alpine = a["units"]["CIR06"]
    assert alpine["disconnected_patch_fraction"] == pytest.approx(3292 / 3883)
    assert alpine["cells_in_disconnected_patch_fraction"] == pytest.approx(19313 / 20409)
    assert alpine["cells_in_disconnected_patch_fraction"] > alpine["disconnected_patch_fraction"]
    assert a["units"]["CIR02"]["cells_in_disconnected_patch_fraction"] < a["units"]["CIR02"]["disconnected_patch_fraction"]


def test_disconnected_patch_accounting_fails_closed():
    s, f = fixtures()
    s["units"]["CIR06"]["disconnected_patch_count"] -= 1
    with pytest.raises(ValueError, match="patch accounting"):
        build_topology_component_gap(s, f)


def test_crosspatch_union_cannot_be_negative():
    s, f = fixtures()
    s["units"]["CIR12"]["global_mask_component_count"] = 1053
    with pytest.raises(ValueError, match="global component"):
        build_topology_component_gap(s, f)


def test_original_patch_sha_cannot_be_changed():
    s, f = fixtures()
    s["units"]["CIR02"]["verified_original_patch_sha256"] = "f"*64
    with pytest.raises(ValueError, match="frozen patch SHA"):
        build_topology_component_gap(s, f)


def test_refuses_ecological_connectivity_promotion():
    s, f = fixtures()
    s["units"]["CIR02"]["ecological_connectivity_claim_authorized"] = True
    with pytest.raises(ValueError, match="ecological connectivity"):
        build_topology_component_gap(s, f)


def test_frozen_grassland_aggregate_equality_not_spatial_membership():
    s, f = fixtures()
    a = build_topology_component_gap(s, f)
    assert a["grassland_aggregate_metrics_equal"] is True
    assert a["grassland_patch_membership_sha_equal"] is False
    assert a["claims"]["grassland_units_are_spatially_identical"] is False


def test_rejects_third_family_relabel_and_missing_units():
    s, f = fixtures()
    s["units"]["CIR02"]["feature_family"] = "ALPINE_TOPOGRAPHIC_STRUCTURE"
    with pytest.raises(ValueError, match="family"):
        build_topology_component_gap(s, f)
    s, f = fixtures()
    del s["units"]["CIR13"]
    with pytest.raises(ValueError, match="four original"):
        build_topology_component_gap(s, f)


def test_immutable_derived_result_verifies_and_tampered_gap_rejects():
    s, f = fixtures()
    a = build_topology_component_gap(s, f)
    assert verify_saved_summary(a, s, f)["status"] == "FROZEN_TOPOLOGY_GAP_DERIVATION_REPRODUCED"
    altered = copy.deepcopy(a)
    altered["units"]["CIR06"]["global_components_minus_patches"] = 0
    with pytest.raises(ValueError, match="derived topology"):
        verify_saved_summary(altered, s, f)


def test_frozen_live_result_and_derived_snapshot_agree_if_available():
    # This integration assertion operates on existing public-only *frozen*
    # repo files; optional in isolated source-fixture experiments.
    top = ROOT / "validation/coverage_then_fine_structure_fresh_sentinel_v2_frozen_patch_topology_result_v1.json"
    source = ROOT / "validation/coverage_then_fine_structure_fresh_sentinel_v2_fine_patch_transfer_result_v1.json"
    saved = ROOT / "validation/coverage_then_fine_structure_fresh_sentinel_v2_patch_topology_component_gap_v1.json"
    if not (top.exists() and source.exists() and saved.exists()):
        pytest.skip("frozen GitHub input files not staged in the local fixture")
    assert verify_saved_summary(json.loads(saved.read_text()), json.loads(top.read_text()), json.loads(source.read_text()))["status"] == "FROZEN_TOPOLOGY_GAP_DERIVATION_REPRODUCED"
