from __future__ import annotations

import json
from pathlib import Path
import unittest

import geoboundaries_v6_coverage_contract as coverage
import predeclare_provider_eligible_observability_confirmation as mod

ROOT = Path(__file__).resolve().parents[1]
OLD_PROTOCOL_PATH = ROOT / "validation" / "acsp_country_frame_observability_confirmation_v1.json"


class ProviderEligibleObservabilityPreregistrationTests(unittest.TestCase):
    def test_all_four_static_fingerprints_and_consumed_bytes_are_frozen(self) -> None:
        observed = mod.validate_static_preregistration()
        self.assertEqual(
            observed,
            {
                "protocol_fingerprint": mod.EXPECTED_PROTOCOL_FINGERPRINT,
                "execution_contract_fingerprint": mod.EXPECTED_EXECUTION_FINGERPRINT,
                "coverage_contract_fingerprint": mod.EXPECTED_COVERAGE_FINGERPRINT,
                "exclusion_provenance_fingerprint": mod.EXPECTED_EXCLUSION_FINGERPRINT,
            },
        )

    def test_scientific_score_endpoint_sample_size_and_primary_gate_are_not_retuned(self) -> None:
        new = mod.protocol()
        old = json.loads(OLD_PROTOCOL_PATH.read_text(encoding="utf-8"))

        for key in (
            "target_frames",
            "regions",
            "plant",
            "animal",
            "record_count_strata",
            "frames_per_region_group",
            "required_per_region_group_stratum",
            "facet_limit",
            "minimum_records",
        ):
            self.assertEqual(new["cohort"][key], old["cohort"][key], key)

        for key in (
            "historical_years",
            "historical_country_min_count",
            "country_selection_seed",
            "score_formula",
            "score_continuous",
            "score_cutoff_selected",
        ):
            self.assertEqual(new["country_declaration"][key], old["country_declaration"][key], key)

        for key in (
            "exact_unique_frozen_frames",
            "both_temporal_classes_present",
            "auc_gt",
            "bootstrap_ci95_lower_gt",
            "bootstrap_repetitions",
            "bootstrap_seed",
        ):
            self.assertEqual(new["primary_confirmation_gates"][key], old["primary_confirmation_gates"][key], key)

        self.assertEqual(
            new["execution"]["second_activation"]["primary_endpoint_positive"],
            old["execution"]["primary_endpoint_positive"],
        )
        self.assertEqual(
            new["execution"]["second_activation"]["primary_endpoint_negative"],
            old["execution"]["primary_endpoint_negative"],
        )
        self.assertFalse(new["trigger"]["scientific_score_or_endpoint_changed"])
        self.assertTrue(new["decision"]["cohort_eligibility_changed_from_aborted_163"])
        self.assertTrue(new["decision"]["cohort_eligibility_change_predeclared_before_new_identities"])

    def test_new_identity_seed_is_fixed_but_country_and_bootstrap_seeds_are_unchanged(self) -> None:
        cfg = mod.protocol()
        self.assertEqual(cfg["cohort"]["selection_seed"], 2026082703)
        self.assertIn("fixed before any new candidate identity", cfg["cohort"]["selection_seed_rule"])
        self.assertEqual(cfg["country_declaration"]["country_selection_seed"], 2026082401)
        self.assertEqual(cfg["primary_confirmation_gates"]["bootstrap_seed"], 2026082702)

    def test_provider_eligibility_is_universal_for_all_frozen_iso_codes(self) -> None:
        contract = coverage.load_contract()
        mapping = coverage.load_iso_mapping()
        supported = set(contract["coverage"]["supported_alpha3"])
        unsupported = []
        for alpha2, alpha3 in sorted(mapping.items()):
            eligible, observed_alpha3, status = mod.provider_eligibility(alpha2)
            if alpha3 in supported:
                self.assertTrue(eligible, alpha2)
                self.assertEqual(observed_alpha3, alpha3)
                self.assertEqual(status, "provider_eligible_before_final_selection")
            else:
                unsupported.append((alpha2, alpha3))
                self.assertFalse(eligible, alpha2)
                self.assertIsNone(observed_alpha3)
                self.assertEqual(status, "preselection_ineligible_provider_coverage")
        self.assertEqual(len(unsupported), 20)

    def test_no_country_is_ineligible_before_final_selection(self) -> None:
        self.assertEqual(
            mod.provider_eligibility(None),
            (False, None, "preselection_ineligible_no_historical_country"),
        )

    def test_final_selection_can_only_choose_from_complete_provider_eligible_pool(self) -> None:
        base = {
            "region_cell_index": 1,
            "taxon_group": "plant",
            "record_count_stratum": 0,
        }
        candidates = [
            {
                **base,
                "speciesKey": 11,
                "scientific_name": "Ineligible alpha",
                "provider_eligible": False,
                "eligibility_status": "preselection_ineligible_provider_coverage",
                "historical_selected_country_count": 1000000,
                "country_frame_observability_score": 99.0,
            },
            {
                **base,
                "speciesKey": 22,
                "scientific_name": "Eligible beta",
                "provider_eligible": True,
                "eligibility_status": "provider_eligible_before_final_selection",
                "historical_selected_country_count": 5,
                "country_frame_observability_score": mod.observability_score(5),
            },
        ]
        chosen = mod.select_final_eligible(candidates, region=1, group="plant", stratum=0)
        self.assertEqual(chosen["speciesKey"], 22)
        self.assertNotEqual(chosen["country_frame_observability_score"], 99.0)

    def test_score_magnitude_never_changes_identity_hash_selection(self) -> None:
        base = {
            "region_cell_index": 2,
            "taxon_group": "animal",
            "record_count_stratum": 3,
            "provider_eligible": True,
            "eligibility_status": "provider_eligible_before_final_selection",
        }
        candidates = [
            {
                **base,
                "speciesKey": 101,
                "scientific_name": "Eligible one",
                "historical_selected_country_count": 5,
                "country_frame_observability_score": mod.observability_score(5),
            },
            {
                **base,
                "speciesKey": 202,
                "scientific_name": "Eligible two",
                "historical_selected_country_count": 999999,
                "country_frame_observability_score": mod.observability_score(999999),
            },
        ]
        first = mod.select_final_eligible(candidates, region=2, group="animal", stratum=3)
        swapped_scores = [dict(x) for x in candidates]
        swapped_scores[0]["historical_selected_country_count"] = 999999
        swapped_scores[0]["country_frame_observability_score"] = mod.observability_score(999999)
        swapped_scores[1]["historical_selected_country_count"] = 5
        swapped_scores[1]["country_frame_observability_score"] = mod.observability_score(5)
        second = mod.select_final_eligible(swapped_scores, region=2, group="animal", stratum=3)
        self.assertEqual(first["speciesKey"], second["speciesKey"])

    def test_predecessor_partial_audit_and_known_pair_are_not_selection_inputs(self) -> None:
        cfg = mod.protocol()
        self.assertFalse(cfg["predecessor"]["partial_live_candidate_audit_may_be_replayed"])
        self.assertFalse(cfg["predecessor"]["known_technical_abort_pair_may_affect_new_selection"])
        self.assertFalse(cfg["exclusions"]["known_163_species_key_special_exclusion"])
        self.assertFalse(cfg["exclusions"]["known_163_country_special_exclusion"])
        selection_blocks = json.dumps(
            {
                "cohort": cfg["cohort"],
                "country_declaration": cfg["country_declaration"],
                "exclusions": cfg["exclusions"],
            },
            sort_keys=True,
        )
        self.assertNotIn("9775639", selection_blocks)

    def test_execution_contract_prevents_pr_schedule_dispatch_and_cron_from_consuming_scientific_run(self) -> None:
        execution = mod.execution_contract()
        first = execution["first_activation_workflow_contract"]
        second = execution["second_activation_workflow_contract"]
        self.assertTrue(first["workflow_must_not_have_pull_request_trigger"])
        self.assertTrue(first["workflow_must_not_have_schedule_trigger"])
        self.assertFalse(first["workflow_dispatch_allowed"])
        self.assertTrue(first["no_cron_fallback"])
        self.assertTrue(second["workflow_must_not_have_pull_request_trigger"])
        self.assertTrue(second["workflow_must_not_have_schedule_trigger"])
        self.assertFalse(second["workflow_dispatch_allowed"])

    def test_second_activation_is_impossible_after_incomplete_first_activation(self) -> None:
        cfg = mod.protocol()
        execution = mod.execution_contract()
        self.assertEqual(cfg["freeze_boundary"]["no_complete_cohort"], "not evaluable; second activation forbidden")
        self.assertFalse(execution["first_activation_failure_semantics"]["second_activation_after_abort_allowed"])
        self.assertTrue(
            execution["second_activation_workflow_contract"][
                "marker_requires_authoritative_first_activation_artifact_id_and_hash"
            ]
        )


if __name__ == "__main__":
    unittest.main()
