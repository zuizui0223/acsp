import json
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

from acsp.practical_rescue import (
    PRACTICAL_RESCUE_PROTOCOL_FINGERPRINT,
    build_rescue_features,
    make_rescue_estimator,
    protocol_fingerprint,
    select_local_anchor_rescue,
)


class PracticalRescueTests(unittest.TestCase):
    def candidates(self):
        return pd.DataFrame({
            "candidate_id": ["a", "b", "c", "d", "e", "f"],
            "candidate_type": [
                "Habitat-match", "Survey-gap", "Environmental-test",
                "Regional-screen", "Habitat-match", "Survey-gap",
            ],
            "latitude": [35.0, 35.01, 35.2, 35.4, 35.6, 35.8],
            "longitude": [139.0, 139.01, 139.2, 139.4, 139.6, 139.8],
            "component_local_habitat_score": [0.95, 0.90, 0.6, 0.5, 0.4, np.nan],
            "integrated_support_score": [0.9, 0.8, 0.7, 0.6, 0.5, 0.4],
            "survey_gap_score": [0.1, 0.2, 1.0, 0.9, 0.8, 0.7],
            "environmental_novelty": [0.1, 0.1, 0.8, 0.7, 0.6, 0.5],
            "access_score": [1, 1, .8, .8, .7, .7],
            "evidence_agreement_score": [.5] * 6,
            "evidence_divergence_score": [.2] * 6,
            "distance_excluded_validation_score": [True] * 6,
            "component_macro_model_score": [.3] * 6,
        })

    def test_protocol_hash(self):
        payload = json.loads(
            (Path(__file__).parent / "validation" / "acsp_practical_rescue_development_protocol.json").read_text()
        )
        self.assertEqual(protocol_fingerprint(payload), PRACTICAL_RESCUE_PROTOCOL_FINGERPRINT)

    def test_features_ignore_outcome_columns(self):
        first = self.candidates()
        second = first.copy()
        first["covered_heldout_ids"] = "x"
        second["covered_heldout_ids"] = "totally-different"
        first["all_heldout_ids"] = "x;y"
        second["all_heldout_ids"] = "q;r;s"
        pd.testing.assert_frame_equal(
            build_rescue_features(first, "plant"),
            build_rescue_features(second, "plant"),
        )

    def test_top_local_is_always_anchor(self):
        candidates = self.candidates()
        predictions = np.array([0, .1, .9, .8, .7, .6])
        selected = select_local_anchor_rescue(candidates, predictions)
        self.assertEqual(selected.iloc[0].candidate_id, "a")
        self.assertEqual(selected.iloc[0].rescue_role, "local_anchor")
        self.assertEqual(len(selected), 5)

    def test_deterministic_under_row_shuffle(self):
        candidates = self.candidates()
        predicted = dict(zip(candidates.candidate_id, [0, .1, .9, .8, .7, .6]))
        first = select_local_anchor_rescue(
            candidates,
            np.array([predicted[value] for value in candidates.candidate_id]),
        )
        shuffled = candidates.sample(frac=1, random_state=3).reset_index(drop=True)
        second = select_local_anchor_rescue(
            shuffled,
            np.array([predicted[value] for value in shuffled.candidate_id]),
        )
        self.assertEqual(first.candidate_id.tolist(), second.candidate_id.tolist())

    def test_estimator_contract(self):
        model = make_rescue_estimator().named_steps["model"]
        self.assertEqual(model.n_estimators, 100)
        self.assertEqual(model.max_depth, 2)
        self.assertEqual(model.min_samples_leaf, 10)
        self.assertEqual(model.loss, "huber")
        self.assertEqual(model.random_state, 42)


if __name__ == "__main__":
    unittest.main()
