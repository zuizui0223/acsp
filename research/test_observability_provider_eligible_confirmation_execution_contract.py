from __future__ import annotations

from pathlib import Path
import unittest

import observability_provider_eligible_confirmation_execution_contract as execution


ROOT = Path(__file__).resolve().parents[1]


class ProviderEligibleObservabilityExecutionContractTests(unittest.TestCase):
    def test_execution_contract_is_byte_pinned_and_preheldout(self) -> None:
        cfg = execution.load_contract()
        self.assertEqual(
            cfg["execution_fingerprint"],
            "0bdc69f05fb1d8030c13f9ccea01676d2915a544846bda8c216362e9890adc34",
        )
        self.assertEqual(
            cfg["protocol_fingerprint"],
            "91b8143f38abb173c3cdabc198bfcc5f113632f33b3c674b99374aac1efdd644",
        )
        self.assertEqual(
            cfg["coverage_contract_fingerprint"],
            "377f6374e077cc38ea7fc026de6dc289abc2716aca8c83d66ddcd42826139520",
        )
        self.assertEqual(cfg["workflow"]["required_run_number"], 1)
        self.assertFalse(cfg["workflow"]["schedule_present"])
        self.assertFalse(cfg["workflow"]["pull_request_trigger_present"])
        self.assertFalse(cfg["workflow"]["workflow_dispatch_present"])
        self.assertFalse(cfg["scientific_object"]["freeze_opens_heldout"])
        self.assertFalse(cfg["scientific_object"]["replacement_after_freeze_allowed"])
        self.assertTrue(cfg["heldout_stage"]["separate_explicit_one_shot_activation_required"])
        self.assertFalse(cfg["heldout_stage"]["heldout_execution_may_start_in_this_workflow"])

    def test_unsupported_country_is_pre_freeze_ineligibility_not_post_selection_replacement(self) -> None:
        semantics = execution.load_contract()["eligibility_semantics"]
        self.assertTrue(semantics["country_declaration_precedes_provider_coverage_check"])
        self.assertTrue(semantics["unsupported_declared_country_is_pre_freeze_candidate_ineligibility"])
        self.assertFalse(semantics["unsupported_declared_country_may_be_substituted"])
        self.assertFalse(semantics["candidate_is_scientifically_frozen_before_provider_eligibility"])
        self.assertFalse(
            semantics[
                "continuing_to_next_hash_ordered_candidate_after_pre_freeze_ineligibility_is_post_selection_replacement"
            ]
        )
        self.assertTrue(semantics["supported_geometry_provider_error_aborts"])
        self.assertTrue(semantics["historical_or_discovery_provider_error_aborts"])

    def test_activation_marker_is_absent_in_preregistration_branch_until_explicit_activation(self) -> None:
        marker = ROOT / execution.ACTIVATION_MARKER_PATH
        self.assertFalse(marker.exists(), "preregistration PR must not contain the activation marker")

    def test_workflow_is_dormant_and_bound_to_exact_marker_only(self) -> None:
        workflow = ROOT / execution.WORKFLOW_PATH
        text = workflow.read_text(encoding="utf-8")
        self.assertIn("name: Country-frame observability provider-eligible confirmation freeze", text)
        self.assertIn("branches: [main]", text)
        self.assertIn(
            "- validation/activate_country_frame_observability_provider_eligible_confirmation_v1.marker",
            text,
        )
        self.assertNotIn("\n  pull_request:", text)
        self.assertNotIn("\n  schedule:", text)
        self.assertNotIn("\n  workflow_dispatch:", text)
        self.assertIn("RUN_NUMBER: ${{ github.run_number }}", text)
        self.assertIn('assert os.environ["RUN_NUMBER"] == "1"', text)
        self.assertIn(
            "91b8143f38abb173c3cdabc198bfcc5f113632f33b3c674b99374aac1efdd644",
            text,
        )
        self.assertIn(
            "0bdc69f05fb1d8030c13f9ccea01676d2915a544846bda8c216362e9890adc34",
            text,
        )
        self.assertIn(
            "377f6374e077cc38ea7fc026de6dc289abc2716aca8c83d66ddcd42826139520",
            text,
        )
        self.assertIn(execution.AUTHORITATIVE_ARTIFACT_NAME, text)
        self.assertIn(execution.ABORT_ARTIFACT_NAME, text)
        self.assertNotIn("2021-2025 occurrence", text)


if __name__ == "__main__":
    unittest.main()
