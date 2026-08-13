from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

import aggregate_practical_rescue_fresh_companion as companion


class PracticalRescueFreshCompanionTests(unittest.TestCase):
    def _candidates(self) -> pd.DataFrame:
        return pd.DataFrame({
            "candidate_id": [f"c{i}" for i in range(1, 9)],
            "candidate_type": ["Habitat-match"] * 8,
            "latitude": [35.00, 35.04, 35.08, 35.12, 35.16, 35.20, 35.24, 35.28],
            "longitude": [139.00, 139.07, 139.14, 139.21, 139.28, 139.35, 139.42, 139.49],
            "component_local_habitat_score": [0.95, 0.82, 0.78, 0.64, 0.60, 0.52, 0.40, 0.31],
            "heldout_recovery_10km": np.linspace(0.0, 1.0, 8),
            "distance_to_heldout_km": np.linspace(1.0, 100.0, 8),
        })

    def test_companion_protocol_fingerprint_is_frozen(self):
        payload, fingerprint = companion._canonical(
            Path("validation/acsp_practical_rescue_fresh_companion_protocol.json"),
            expected=companion.EXPECTED_COMPANION_PROTOCOL,
        )
        self.assertEqual(fingerprint, companion.EXPECTED_COMPANION_PROTOCOL)
        self.assertFalse(payload["fresh_outcomes_fetched_or_inspected_at_freeze"])
        self.assertFalse(payload["changes_to_primary_grts_protocol"])
        self.assertFalse(payload["changes_to_final_rescue_model"])
        self.assertFalse(payload["taxon_replacement_allowed"])
        self.assertEqual(payload["bound_fresh_confirmation"]["pair_count"], 192)
        self.assertEqual(
            payload["bound_fresh_confirmation"]["fresh_protocol_fingerprint"],
            "c7d84a3160e9d9b0b05b932c44444be5dfd750200e72749fb413592499bcf8bd",
        )

    def test_companion_decisions_ignore_heldout_named_columns(self):
        protocol, _ = companion._canonical(
            Path("validation/acsp_practical_rescue_fresh_companion_protocol.json"),
            expected=companion.EXPECTED_COMPANION_PROTOCOL,
        )
        candidates = self._candidates()
        with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
            first = companion._freeze_companion_decisions(
                candidates, "animal", 7, 2, protocol, Path(tmp1)
            )
            altered = candidates.copy()
            altered["heldout_recovery_10km"] = altered["heldout_recovery_10km"][::-1].to_numpy()
            altered["distance_to_heldout_km"] = -9999.0
            second = companion._freeze_companion_decisions(
                altered, "animal", 7, 2, protocol, Path(tmp2)
            )
        for key in (
            "frozen_v1_ids",
            "local_only_ids",
            "geographic_maximin_ids",
            "same_pool_random_ids",
        ):
            self.assertEqual(first[key], second[key])
        self.assertFalse(first["outcomes_available_to_selectors"])

    def test_companion_decisions_are_top5_and_random_count_is_frozen(self):
        protocol, _ = companion._canonical(
            Path("validation/acsp_practical_rescue_fresh_companion_protocol.json"),
            expected=companion.EXPECTED_COMPANION_PROTOCOL,
        )
        with tempfile.TemporaryDirectory() as tmp:
            decisions = companion._freeze_companion_decisions(
                self._candidates(), "plant", 11, 4, protocol, Path(tmp)
            )
            stored = json.loads(Path(tmp, "decisions_pre_outcome.json").read_text())
        self.assertEqual(len(decisions["frozen_v1_ids"]), 5)
        self.assertEqual(len(decisions["local_only_ids"]), 5)
        self.assertEqual(len(decisions["geographic_maximin_ids"]), 5)
        self.assertEqual(len(decisions["same_pool_random_ids"]), 50)
        self.assertTrue(all(len(ids) == 5 for ids in decisions["same_pool_random_ids"]))
        self.assertEqual(stored, decisions)

    def test_v1_gate_uses_predeclared_threshold(self):
        positive = np.full(192, 0.02)
        result = companion._inference(positive, 1000, 20260813)
        self.assertGreaterEqual(result["mean_difference"], 0.015)
        self.assertGreater(result["bootstrap_95ci_low"], 0.0)
        self.assertLess(result["sign_flip_p"], 0.05)


if __name__ == "__main__":
    unittest.main()
