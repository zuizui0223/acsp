import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from evaluate_practical_core_claim_guardrails import (
    EXPECTED_GUARDRAIL,
    _fingerprint,
    run,
)


class PracticalCoreClaimGuardrailTests(unittest.TestCase):
    def test_guardrail_fingerprint_is_frozen(self):
        payload, fingerprint = _fingerprint(
            Path("validation/acsp_practical_core_claim_guardrail.json")
        )
        self.assertEqual(fingerprint, EXPECTED_GUARDRAIL)
        self.assertTrue(payload["no_retuning_after_outcome"])

    def write_aggregate(
        self,
        root: Path,
        *,
        mindis_diff=0.02,
        mindis_low=0.005,
        mindis_p=0.01,
        prop_diff=0.02,
        prop_low=0.004,
        prop_p=0.02,
        equal_diff=0.01,
        equal_low=0.002,
        equal_p=0.03,
    ):
        root.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "method_a": "acsp_practical_core",
                "method_b": "official_grts_proportional_local_mindis10km",
                "pairs": 192,
                "mean_method_a": 0.15,
                "mean_method_b": 0.15 - mindis_diff,
                "mean_difference": mindis_diff,
                "bootstrap_95ci_low": mindis_low,
                "bootstrap_95ci_high": mindis_diff + 0.01,
                "sign_flip_p": mindis_p,
                "positive_pairs": 100,
                "negative_pairs": 70,
                "tied_pairs": 22,
                "difference_sd": 0.08,
            },
            {
                "method_a": "acsp_practical_core",
                "method_b": "official_grts_proportional_local",
                "pairs": 192,
                "mean_method_a": 0.15,
                "mean_method_b": 0.15 - prop_diff,
                "mean_difference": prop_diff,
                "bootstrap_95ci_low": prop_low,
                "bootstrap_95ci_high": prop_diff + 0.01,
                "sign_flip_p": prop_p,
                "positive_pairs": 100,
                "negative_pairs": 70,
                "tied_pairs": 22,
                "difference_sd": 0.08,
            },
            {
                "method_a": "acsp_practical_core",
                "method_b": "official_grts_equal",
                "pairs": 192,
                "mean_method_a": 0.15,
                "mean_method_b": 0.15 - equal_diff,
                "mean_difference": equal_diff,
                "bootstrap_95ci_low": equal_low,
                "bootstrap_95ci_high": equal_diff + 0.01,
                "sign_flip_p": equal_p,
                "positive_pairs": 100,
                "negative_pairs": 70,
                "tied_pairs": 22,
                "difference_sd": 0.08,
            },
        ]
        pd.DataFrame(rows).to_csv(root / "pair_level_inference.csv", index=False)
        primary_pass = (
            mindis_diff >= 0.015 and mindis_low > 0 and mindis_p < 0.05
        )
        (root / "primary_gate.json").write_text(
            json.dumps({
                "method_a": "acsp_practical_core",
                "method_b": "official_grts_proportional_local_mindis10km",
                "pairs": 192,
                "mean_difference": mindis_diff,
                "bootstrap_95ci_low": mindis_low,
                "sign_flip_p": mindis_p,
                "gate_passed": primary_pass,
            }),
            encoding="utf-8",
        )
        (root / "confirmation_manifest.json").write_text(
            json.dumps({
                "practical_core_fingerprint": "3dafe65b6bef09b1878d688730d5feb64a8de58843b06ff9fb14a876512d4905",
                "confirmation_protocol_fingerprint": "cd27dc5416057b574e58742bfe001307338a20aedb63ce1bac431588dc58eee9",
                "no_retuning_after_outcome": True,
            }),
            encoding="utf-8",
        )

    def test_all_grts_conditions_pass_but_existing_tool_claim_stays_blocked(self):
        with tempfile.TemporaryDirectory() as temporary:
            aggregate = Path(temporary) / "aggregate"
            output = Path(temporary) / "claim.json"
            self.write_aggregate(aggregate)
            result = run(aggregate, output)
        self.assertTrue(result["primary_same_pool_result"]["passed"])
        self.assertTrue(result["grts_family_superiority"]["passed"])
        self.assertTrue(
            result["existing_tool_superiority"]["ready_for_separate_biosurvey_gate"]
        )
        self.assertFalse(result["existing_tool_superiority"]["passed"])

    def test_primary_win_does_not_generalize_when_no_mindis_proportional_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            aggregate = Path(temporary) / "aggregate"
            output = Path(temporary) / "claim.json"
            self.write_aggregate(
                aggregate,
                prop_diff=0.005,
                prop_low=-0.004,
                prop_p=0.4,
            )
            result = run(aggregate, output)
        self.assertTrue(result["primary_same_pool_result"]["passed"])
        self.assertFalse(result["grts_family_superiority"]["passed"])
        self.assertIn(
            "10-km minimum-distance constraint",
            result["strongest_allowed_same_pool_claim"],
        )
        self.assertFalse(
            result["existing_tool_superiority"]["ready_for_separate_biosurvey_gate"]
        )

    def test_primary_failure_blocks_all_superiority_language(self):
        with tempfile.TemporaryDirectory() as temporary:
            aggregate = Path(temporary) / "aggregate"
            output = Path(temporary) / "claim.json"
            self.write_aggregate(
                aggregate,
                mindis_diff=0.005,
                mindis_low=-0.003,
                mindis_p=0.3,
            )
            result = run(aggregate, output)
        self.assertFalse(result["primary_same_pool_result"]["passed"])
        self.assertFalse(result["grts_family_superiority"]["passed"])
        self.assertTrue(
            result["strongest_allowed_same_pool_claim"].startswith(
                "No same-pool superiority claim"
            )
        )


if __name__ == "__main__":
    unittest.main()
