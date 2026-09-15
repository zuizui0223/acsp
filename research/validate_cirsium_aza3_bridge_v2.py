#!/usr/bin/env python3
"""Fail-closed validation for the prospective aza3 Cirsium ACSP bridge v2."""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "validation" / "acsp_occurrence_anchored_local_discovery_development_v2.json"
FIELD_LOG = ROOT / "validation" / "cirsium_aza3_acsp_field_log_template_v1.csv"
DOC = ROOT / "research" / "CIRSIUM_AZA3_PROSPECTIVE_LOCAL_DISCOVERY.md"

EXPECTED_FIELD_COLUMNS = [
    "validation_unit_id",
    "aza3_slot_id",
    "species_binomial",
    "acsp_patch_id",
    "discovery_regime",
    "method_arm",
    "comparator_assignment",
    "deidentified_locality_id",
    "visit_date",
    "phenology_status",
    "access_evaluability_state",
    "search_minutes",
    "observer_count",
    "traversed_length_m",
    "searched_area_m2",
    "field_outcome_state",
    "focal_detection_count",
    "identity_verification_status",
    "identity_evidence_id",
    "incomplete_search_reason",
    "tissue_acquired_secondary",
    "aza3_authorization_record_id",
    "private_exact_site_record_id",
    "notes",
]


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["schema_version"] == "acsp-occurrence-anchored-local-discovery-development-v2"
    assert contract["status"] == "PRE_CIRSIUM_OCCURRENCE_RETRIEVAL_FROZEN"

    preserve = contract["preserves"]
    assert preserve["validated_robust_candidate_patch_product"] is True
    assert preserve["validated_robust_support_fraction"] == 0.025
    assert preserve["validated_robust_primary_radius_km"] == 10.0
    assert preserve["campanula_role"] == "development_only_not_independent_confirmation"

    bridge = contract["external_bridge"]
    assert bridge["operational_core_species"] == 128
    assert bridge["required_tree_representation_slots"] == 228
    assert bridge["aza3_active_minimum_unique_sources"] == 314
    forbidden_choices = set(bridge["acsp_does_not_choose"])
    assert {"phylogenetic sampling priority", "private exact locality", "field campaign order"}.issubset(forbidden_choices)

    occ = contract["occurrence_input_freeze"]
    assert occ["country"] == "Japan"
    assert occ["event_date_max"] == "2025-12-31"
    assert occ["records_from_2026_or_later_allowed_in_first_pass"] is False
    assert "no fuzzy substitution" in occ["taxon_matching"]

    typing = contract["occurrence_evidence_typing"]
    assert set(typing["spatial_classes"]) == {
        "EXACT_OR_DECLARED_PRECISE_COORDINATE",
        "COORDINATE_UNCERTAIN",
        "COORDINATE_OBSCURED",
        "REGION_ONLY",
        "NO_LOCALITY",
    }
    primary = typing["primary_local_anchor_gate"]
    assert primary["maximum_declared_coordinate_uncertainty_m"] == 1000
    assert primary["unknown_coordinate_uncertainty_is_precise"] is False
    assert primary["event_year_min"] == 2000
    assert primary["event_year_max"] == 2025
    assert primary["provider_geospatial_issue_allowed"] is False
    legacy = typing["legacy_coordinate_sensitivity"]
    assert legacy["event_year_min"] == 1950 and legacy["event_year_max"] == 1999
    assert legacy["can_define_primary_local_kernel"] is False

    graphs = contract["graph_architecture"]
    assert graphs["ecological_support_graph"]["id"] == "G_E"
    assert graphs["survey_feasibility_graph_or_mask"]["id"] == "G_F"
    assert graphs["ecological_support_graph"]["human_accessibility_can_create_ecological_support"] is False
    assert graphs["survey_feasibility_graph_or_mask"]["applied_after_ecological_candidate_construction"] is True
    assert graphs["survey_feasibility_graph_or_mask"]["inaccessible_means_biological_absence"] is False

    regimes = set(contract["discovery_regimes"])
    assert regimes == {"LOCAL_CONTINUATION", "DETACHED_COMPONENT", "SENTINEL", "ABSTAIN_LOCAL_PATCH"}

    unavailable = set(contract["not_currently_identified"])
    assert {"optimal field days", "optimal total budget", "automatic stopping threshold"}.issubset(unavailable)
    assert contract["comparators"]["campanula_ndvi_hybrid_revival_allowed"] is False

    outcome = contract["prospective_field_endpoint"]
    assert outcome["tissue_acquisition_is_primary_acsp_endpoint"] is False
    assert outcome["access_failure_is_nondetection"] is False
    assert outcome["permission_blocked_is_nondetection"] is False
    states = set(outcome["allowed_states"])
    assert {"ACCESS_FAILED", "PERMISSION_BLOCKED", "SEARCH_COMPLETED_NOT_DETECTED"}.issubset(states)
    assert set(outcome["minimum_effort_fields"]) == {"search_minutes", "observer_count"}

    assert contract["public_data_safety"]["exact_sensitive_coordinates_in_repository"] is False
    assert contract["validation_cohort_boundary"]["failures_and_abstentions_retained"] is True
    assert contract["validation_cohort_boundary"]["no_post_outcome_taxon_or_site_substitution"] is True

    with FIELD_LOG.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        assert header == EXPECTED_FIELD_COLUMNS
        assert list(reader) == [], "field template must remain empty before prospective data collection"
    forbidden_public_columns = {"latitude", "longitude", "gps", "exact_latitude", "exact_longitude"}
    assert not forbidden_public_columns.intersection(header)

    text = DOC.read_text(encoding="utf-8")
    for phrase in (
        "2025-12-31",
        "G_E",
        "G_F",
        "ABSTAIN_LOCAL_PATCH",
        "ACCESS_FAILED",
        "Tissue collection is secondary",
        "does **not** yet estimate optimal field days",
        "Campanula",
        "deterministic spatial balance",
    ):
        assert phrase in text, phrase

    print("cirsium_aza3_acsp_bridge_v2_valid=true")
    print("operational_core_species=128")
    print("required_tree_slots=228")
    print("aza3_active_minimum_unique_sources=314")
    print("occurrence_event_date_max=2025-12-31")
    print("primary_anchor_uncertainty_m_max=1000")
    print("route_budget_stopping_identified=false")
    print("exact_sensitive_coordinates_public=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
