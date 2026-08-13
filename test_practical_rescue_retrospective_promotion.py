from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import evaluate_practical_rescue_retrospective_promotion as promotion


class PracticalRescueRetrospectivePromotionTests(unittest.TestCase):
    def _primary(self, passed: bool) -> dict[str, object]:
        return {
            "status": "fresh_practical_rescue_confirmation_evaluated",
            "protocol_fingerprint": promotion.PRIMARY_PROTOCOL,
            "declared_pairs": 192,
            "verified_pair_artifacts": 192,
            "promotion_gate_passed": passed,
            "final_model_sha256": promotion.MODEL_SHA,
            "missing_pair_artifacts_scored_as_zero": False,
            "no_retuning_after_confirmation_outcome": True,
        }

    def _companion(self, passed: bool) -> dict[str, object]:
        return {
            "status": "fresh_practical_rescue_companion_evaluated",
            "protocol_fingerprint": promotion.COMPANION_PROTOCOL,
            "fresh_protocol_fingerprint": promotion.PRIMARY_PROTOCOL,
            "declared_pairs": 192,
            "verified_pair_artifacts": 192,
            "required_v2_minus_frozen_v1_gate_passed": passed,
            "final_model_sha256": promotion.MODEL_SHA,
            "missing_pair_artifacts_scored_as_zero": False,
            "fresh_outcomes_used_for_retuning": False,
        }

    def _run(self, primary_pass: bool, companion_pass: bool) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            primary = root / "primary.json"
            companion = root / "companion.json"
            output = root / "promotion.json"
            primary.write_text(json.dumps(self._primary(primary_pass)), encoding="utf-8")
            companion.write_text(json.dumps(self._companion(companion_pass)), encoding="utf-8")
            result = promotion.run(primary, companion, output)
            stored = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result, stored)
            return result

    def test_both_fresh_gates_are_required(self):
        self.assertTrue(self._run(True, True)["retrospective_ecological_promotion_passed"])
        self.assertFalse(self._run(True, False)["retrospective_ecological_promotion_passed"])
        self.assertFalse(self._run(False, True)["retrospective_ecological_promotion_passed"])
        self.assertFalse(self._run(False, False)["retrospective_ecological_promotion_passed"])

    def test_retrospective_pass_does_not_unlock_production_or_broad_tool_claim(self):
        result = self._run(True, True)
        self.assertEqual(
            result["production_promotion_status"],
            "blocked_pending_prospective_field_attempt_non_detection_effort_and_access_records",
        )
        self.assertEqual(
            result["broad_existing_tool_superiority_status"],
            "pending_native_biosurvey_end_to_end_gate_for_the_promoted_rescue_policy",
        )
        self.assertFalse(result["post_confirmation_retuning_allowed"])

    def test_missing_zero_fill_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            primary_payload = self._primary(True)
            primary_payload["missing_pair_artifacts_scored_as_zero"] = True
            primary = root / "primary.json"
            companion = root / "companion.json"
            primary.write_text(json.dumps(primary_payload), encoding="utf-8")
            companion.write_text(json.dumps(self._companion(True)), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing artifacts"):
                promotion.run(primary, companion, root / "out.json")


if __name__ == "__main__":
    unittest.main()
