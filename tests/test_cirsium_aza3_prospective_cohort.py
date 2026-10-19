from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_exhaustive_occurrence_audit_is_pinned_and_public_safe() -> None:
    result = json.loads(
        (ROOT / "validation" / "cirsium_aza3_occurrence_audit_result_v1.json").read_text(encoding="utf-8")
    )
    assert result["status"] == "FROZEN_PRE_FIELD_RESULT"
    assert result["source_workflow"]["run_id"] == 33838128330
    assert result["source_workflow"]["artifact_id"] == 9924073984
    assert result["source_workflow"]["artifact_digest"] == "sha256:fe1971d5547b4741fdcfc568fe568193007398afca6dd0aa316c2713d8d6e430"
    assert result["universe"] == {
        "required_tree_slots": 228,
        "required_slot_species": 127,
        "p7_zero_required_slot_species_not_in_audit": 1,
    }
    assert result["taxon_match_counts"]["AUTO_EXACT_ACCEPTED"] == 100
    assert result["taxon_match_counts"]["review_required_total"] == 27
    assert result["species_problem_counts"]["LOCAL_CONTINUATION_INPUT_AVAILABLE"] == 29
    assert sum(result["species_problem_counts"].values()) == 127
    assert sum(result["slot_problem_counts"].values()) == 228
    assert result["derived_fractions"]["species_local_anchor_ready_given_auto_exact_taxonomy"] == 0.29
    assert result["algorithmic_consequence"]["local_anchor_search_is_majority_problem"] is False
    assert result["frozen_input_rules"]["public_exact_coordinates_written"] is False


def test_prospective_cohort_is_frozen_before_patch_and_field_outcomes() -> None:
    contract = json.loads(
        (ROOT / "validation" / "cirsium_aza3_prospective_validation_cohort_contract_v1.json").read_text(encoding="utf-8")
    )
    assert contract["status"] == "FROZEN_PRE_PATCH_PRE_FIELD"
    assert contract["cohort_size"] == 13
    assert contract["field_outcomes_opened"] is False
    assert contract["candidate_patches_built"] is False
    assert contract["regime_counts"] == {"LOCAL_CONTINUATION": 9, "SENTINEL": 4}
    assert contract["slot_selection"]["outcome_dependent_replacement_allowed"] is False

    with (ROOT / "validation" / "cirsium_aza3_prospective_validation_cohort_v1.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 13
    assert len({r["cohort_unit_id"] for r in rows}) == 13
    assert len({r["species_binomial"] for r in rows}) == 13
    assert all(r["outcome_opened"] == "false" for r in rows)
    assert all(r["candidate_patch_status"] == "NOT_BUILT" for r in rows)
    assert all(r["field_performance_denominator"] == "true" for r in rows)
    assert not any("latitude" in key.lower() or "longitude" in key.lower() for key in rows[0])

    regimes = Counter(r["occurrence_problem_class"] for r in rows)
    families = Counter(r["structural_feature_family"] for r in rows)
    assert regimes == Counter({"LOCAL_CONTINUATION": 9, "SENTINEL": 4})
    assert families == Counter(
        {
            "ALPINE_TOPOGRAPHIC_STRUCTURE": 4,
            "OPEN_GRASSLAND_STRUCTURE": 3,
            "WETLAND_MOISTURE_STRUCTURE": 2,
            "COASTAL_ISLAND_STRUCTURE": 2,
            "FOREST_EDGE_STRUCTURE": 1,
            "GENERAL_SPATIAL_BASELINE_ONLY": 1,
        }
    )
    lookup = {r["species_binomial"]: r for r in rows}
    assert lookup["Cirsium dipsacolepis"]["cohort_role"] == "FOCAL_SENTINEL_P02"
    assert lookup["Cirsium lineare"]["cohort_role"] == "FOCAL_SENTINEL_P02"
    assert lookup["Cirsium tamastoloniferum"]["method_arm"] == "SPATIAL_BASELINE_ONLY"
    assert lookup["Cirsium hachijoense"]["structural_feature_family"] == "FOREST_EDGE_STRUCTURE"
