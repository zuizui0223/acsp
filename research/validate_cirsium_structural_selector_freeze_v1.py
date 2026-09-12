#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from acsp.structural_support import BASELINE_FAMILY, FAMILY_COMPONENTS

ROOT = Path(__file__).resolve().parents[1]
EXECUTION = ROOT / "validation" / "cirsium_structural_selector_execution_freeze_v1.json"
FAMILY_CONTRACT = ROOT / "validation" / "cirsium_structural_selector_family_contract_v1.json"
RAW_ADAPTER_CONTRACT = ROOT / "validation" / "cirsium_structural_raw_adapter_contract_v1.json"
GRAPH_CONTRACT = ROOT / "validation" / "cirsium_structural_graph_contract_v1.json"
FRAME_CONTRACT = ROOT / "validation" / "cirsium_candidate_frame_contract_v1.json"
SOURCE_REQUIREMENTS = ROOT / "validation" / "cirsium_private_frame_source_requirements_v1.csv"
SOURCE_TEMPLATE = ROOT / "validation" / "cirsium_private_source_manifest_template_v1.json"
COHORT = ROOT / "validation" / "cirsium_aza3_prospective_validation_cohort_v1.csv"


def validate() -> dict[str, object]:
    execution = json.loads(EXECUTION.read_text(encoding="utf-8"))
    family_contract = json.loads(FAMILY_CONTRACT.read_text(encoding="utf-8"))
    raw_contract = json.loads(RAW_ADAPTER_CONTRACT.read_text(encoding="utf-8"))
    graph_contract = json.loads(GRAPH_CONTRACT.read_text(encoding="utf-8"))
    frame_contract = json.loads(FRAME_CONTRACT.read_text(encoding="utf-8"))
    source_template = json.loads(SOURCE_TEMPLATE.read_text(encoding="utf-8"))
    with COHORT.open(encoding="utf-8", newline="") as handle:
        cohort = list(csv.DictReader(handle))
    with SOURCE_REQUIREMENTS.open(encoding="utf-8", newline="") as handle:
        source_rows = list(csv.DictReader(handle))

    assert execution["status"] == "ALGORITHM_ADAPTERS_GRAPH_RANKING_AND_SENTINEL_AUDIT_FROZEN_PRIVATE_FRAMES_NOT_YET_EXECUTED"
    assert execution["field_outcomes_opened"] is False
    assert execution["private_candidate_frames_built"] is False
    assert execution["public_patch_manifest_built"] is False
    assert execution["public_full_ranking_built"] is False
    assert execution["field_prefix_selected"] is False
    assert execution["cohort_size"] == len(cohort) == len(source_rows) == 13
    assert execution["feature_weights_fitted"] is False
    assert execution["field_outcome_columns_allowed_in_generation"] is False
    assert execution["post_outcome_family_switch_allowed"] is False
    assert execution["ecological_graph_uses_human_access"] is False
    assert execution["raw_adapter_uses_human_access"] is False
    assert execution["full_ranking_before_field_prefix"] is True
    assert execution["outcome_dependent_prefix_extension_allowed"] is False
    assert execution["same_candidate_frame_full_ranking_within_unit"] is True
    assert execution["matched_field_effort_claim"] is False
    assert execution["legacy_fixed_k_generator_authoritative_for_new_execution"] is False
    assert execution["public_full_ranking_generator"].endswith("freeze_cirsium_candidate_patch_ranking_v2.py")

    audit_v2 = execution["occurrence_uncertainty_audit_v2"]
    assert audit_v2["completed"] is True
    assert audit_v2["workflow_run_id"] == 33847046386
    assert audit_v2["artifact_id"] == 9926992269
    assert audit_v2["artifact_digest"] == "sha256:5e908fecb625f2f8e4e87e758a0a9d0ace63c14e63fce19cf7bf87c0c7fe8147"
    assert audit_v2["field_outcomes_opened"] is False
    assert audit_v2["coordinate_leakage_guard_passed"] is True

    code_components = {family: list(columns) for family, columns in FAMILY_COMPONENTS.items()}
    code_components[BASELINE_FAMILY] = []
    assert execution["family_components"] == code_components

    contract_families = set(family_contract["families"])
    assert set(execution["family_components"]) <= contract_families
    assert family_contract["no_post_outcome_feature_family_switch"] is True

    assert raw_contract["status"] == "PRE_PRIVATE_FRAME_PRE_FIELD_FROZEN"
    assert raw_contract["field_outcomes_used"] is False
    assert raw_contract["fitted_feature_weights"] is False
    assert raw_contract["post_outcome_formula_switch_allowed"] is False
    assert "graph builder" in raw_contract["general_rules"]["graph_rule"]

    assert graph_contract["status"] == "PRE_PRIVATE_FRAME_PRE_FIELD_FROZEN"
    assert graph_contract["graph_id"] == "G_E_LOCAL_GRID_V1"
    assert graph_contract["field_outcomes_used"] is False
    assert graph_contract["human_access_used"] is False
    assert graph_contract["roads_or_trails_used"] is False
    assert graph_contract["permissions_used"] is False
    assert graph_contract["coastline_source"]["source_of_record"].startswith(
        "Geospatial Information Authority of Japan"
    )

    assert frame_contract["status"] == "LOCAL_FRAME_AND_SENTINEL_SUBREGIMES_FROZEN_PRE_PRIVATE_FRAME"
    assert frame_contract["grid"]["target_spacing_m"] == 100
    assert frame_contract["local_continuation"]["known_point_exclusion_km"] == 0.5
    assert frame_contract["local_continuation"]["primary_outer_radius_km"] == 2.0
    assert frame_contract["local_continuation"]["sensitivity_outer_radius_km"] == 5.0
    assert frame_contract["selection_count"]["status"] == "RANKING_FREEZE_FIRST"
    sentinel_contract = frame_contract["sentinel"]
    assert sentinel_contract["status"] == "SUBREGIMES_FROZEN_AFTER_UNCERTAINTY_AUDIT_V2"
    assert set(sentinel_contract["subregimes"]) == {
        "UNCERTAINTY_FOOTPRINT",
        "LEGACY_RANGE_CONTEXT",
        "COARSE_RANGE_CONTEXT",
    }
    assert sentinel_contract["known_point_local_kernel_allowed"] is False
    assert sentinel_contract["forced_pseudo_exact_coordinate_allowed"] is False

    assert source_template["field_outcomes_opened"] is False
    assert source_template["candidate_grid"]["target_spacing_m"] == 100
    assert source_template["authorization_access_layers_in_G_E"] is False
    assert source_template["occurrence_input"]["audit_v2_artifact_digest"] == audit_v2["artifact_digest"]
    assert source_template["occurrence_input"]["sentinel_evidence_class"] == "REPLACE_FROM_FROZEN_COHORT"
    assert all(row["private_source_manifest_status"] == "NOT_BUILT" for row in source_rows)
    assert all(row["private_frame_status"] == "NOT_BUILT" for row in source_rows)
    assert all(row["public_full_ranking_status"] == "NOT_FROZEN" for row in source_rows)
    assert {row["cohort_unit_id"] for row in source_rows} == {row["cohort_unit_id"] for row in cohort}

    source_state = execution["source_layer_state"]
    assert source_state["terrain_semantics"] == "PINNED_GSI_DEM_DERIVED"
    assert source_state["worldcover_semantics"] == "PINNED_ESA_WORLDCOVER_2021_NEIGHBOURHOOD"
    assert source_state["coastline_source_of_record"] == "GSI_FUNDAMENTAL_GEOSPATIAL_DATA_BASIC_ITEMS_COASTLINE"
    assert source_state["coastline_private_snapshot_sha256_recorded"] is False
    assert source_state["private_unit_source_snapshots_built"] is False
    assert source_state["sentinel_uncertainty_audit_v2_completed"] is True

    method_counts = Counter(row["method_arm"] for row in cohort)
    assert method_counts == Counter(
        {"STRUCTURAL_LOCAL": 8, "STRUCTURAL_SENTINEL": 4, "SPATIAL_BASELINE_ONLY": 1}
    )
    sentinel_subregime_counts = Counter(
        row["sentinel_subregime"] for row in cohort if row["occurrence_problem_class"] == "SENTINEL"
    )
    assert sentinel_subregime_counts == Counter(
        {"UNCERTAINTY_FOOTPRINT": 2, "LEGACY_RANGE_CONTEXT": 1, "COARSE_RANGE_CONTEXT": 1}
    )
    for row in cohort:
        family = row["structural_feature_family"]
        arm = row["method_arm"]
        assert family in execution["family_components"]
        assert arm in execution["ranking_method_sets"]
        if arm == "SPATIAL_BASELINE_ONLY":
            assert family == BASELINE_FAMILY
        else:
            assert execution["family_components"][family]
        assert row["outcome_opened"] == "false"
        assert row["candidate_patch_status"] == "NOT_BUILT"
        if row["occurrence_problem_class"] == "LOCAL_CONTINUATION":
            assert row["sentinel_subregime"] == "NOT_APPLICABLE"
        elif row["sentinel_subregime"] == "UNCERTAINTY_FOOTPRINT":
            assert "UNCERTAINTY_FOOTPRINT_SUPPORT" in row["comparators"]
        else:
            assert row["comparators"] == "DETERMINISTIC_SPATIAL_BALANCE"

    policy = execution["public_sensitive_coordinate_policy"]
    assert policy["exact_coordinates_written"] is False
    assert policy["raw_candidate_ids_written"] is False
    assert policy["private_salt_committed"] is False
    assert "HMAC-SHA256" in policy["public_candidate_identifier"]

    return {
        "status": "OK",
        "cohort_size": len(cohort),
        "method_arm_counts": dict(method_counts),
        "sentinel_subregime_counts": dict(sentinel_subregime_counts),
        "family_count": len(execution["family_components"]),
        "algorithm_frozen": True,
        "raw_adapters_frozen": True,
        "ecological_graph_frozen": True,
        "local_candidate_frame_frozen": True,
        "sentinel_subregimes_frozen": True,
        "full_ranking_mechanics_frozen": True,
        "sentinel_subregime_pending_v2": False,
        "real_candidate_patches_built": False,
        "field_outcomes_opened": False,
    }


if __name__ == "__main__":
    print(json.dumps(validate(), ensure_ascii=False, indent=2))
