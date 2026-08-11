import json
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

from acsp.practical_v2 import (
    V2_PROTOCOL_FINGERPRINT,
    build_candidate_decision_utility_features,
    development_protocol_fingerprint,
    score_candidate_decision_utility,
    select_candidate_decision_utility,
    select_practical_v2,
)


class PracticalV2Tests(unittest.TestCase):
    def candidates(self):
        return pd.DataFrame({
            "candidate_id": [f"c{i}" for i in range(1, 8)],
            "candidate_type": [
                "habitat-match", "survey-gap", "environmental-test", "other",
                "habitat analogue", "habitat-match", "survey-gap",
            ],
            "latitude": [35.00, 35.03, 35.20, 35.22, 35.45, 35.48, 35.70],
            "longitude": [139.00, 139.04, 139.10, 139.13, 139.25, 139.30, 139.45],
            "component_local_habitat_score": [0.95, 0.88, 0.84, 0.82, 0.91, 0.79, 0.76],
            "elevation": [10, 20, 100, 120, 250, 270, 400],
            "slope": [2, 3, 7, 8, 12, 13, 18],
            "aspect": [359, 2, 80, 100, 180, 190, 270],
            "roughness": [0.1, 0.2, 0.4, 0.5, 0.8, 0.9, 1.2],
            "tpi": [-1.0, -0.8, -0.2, 0.0, 0.5, 0.7, 1.2],
        })

    def test_protocol_fingerprint_matches_committed_artifact(self):
        payload = json.loads(
            (Path(__file__).parent / "validation" / "acsp_v2_candidate_utility_protocol.json").read_text()
        )
        self.assertEqual(development_protocol_fingerprint(payload), V2_PROTOCOL_FINGERPRINT)
        self.assertEqual(payload["fingerprint"], V2_PROTOCOL_FINGERPRINT)

    def test_features_use_only_candidate_pool_context(self):
        candidates = self.candidates()
        features = build_candidate_decision_utility_features(candidates, "plant")
        required = {
            "local_score", "local_rank_pct", "geo_nn_km", "geo_avg_km",
            "env_nn", "env_avg", "candidate_pool", "pool_local_sd",
            "pool_local_q90", "taxon_group", "candidate_type",
        }
        self.assertTrue(required.issubset(features.columns))
        self.assertEqual(set(features["taxon_group"]), {"plant"})
        self.assertTrue(np.isfinite(features["geo_nn_km"]).all())
        self.assertTrue(np.isfinite(features["env_nn"]).all())

    def test_heldout_columns_cannot_change_scores_or_selection(self):
        candidates = self.candidates()
        first = candidates.copy()
        first["covered_heldout_ids"] = ["h1", "", "h2", "", "", "h3", ""]
        first["all_heldout_ids"] = "h1;h2;h3"
        first["heldout_distances_km"] = "1;2;3"
        second = first.copy()
        second["covered_heldout_ids"] = ["x;y;z"] * len(second)
        second["all_heldout_ids"] = "x;y;z;q"
        second["heldout_distances_km"] = "999;999"

        score1 = score_candidate_decision_utility(first, "plant")
        score2 = score_candidate_decision_utility(second, "plant")
        np.testing.assert_allclose(
            score1["v2_candidate_decision_utility_score"],
            score2["v2_candidate_decision_utility_score"],
        )
        sel1 = select_candidate_decision_utility(first, "plant")
        sel2 = select_candidate_decision_utility(second, "plant")
        self.assertEqual(sel1["candidate_id"].tolist(), sel2["candidate_id"].tolist())

    def test_scientific_name_and_region_do_not_change_decision(self):
        candidates = self.candidates()
        a = candidates.assign(scientific_name="Species alpha", geographic_stratum="north")
        b = candidates.assign(scientific_name="Species beta", geographic_stratum="south")
        sa = select_candidate_decision_utility(a, "animal")
        sb = select_candidate_decision_utility(b, "animal")
        self.assertEqual(sa["candidate_id"].tolist(), sb["candidate_id"].tolist())

    def test_selection_is_deterministic_and_budgeted(self):
        candidates = self.candidates()
        first = select_candidate_decision_utility(candidates, "plant")
        second = select_candidate_decision_utility(candidates.sample(frac=1, random_state=9), "plant")
        self.assertEqual(len(first), 5)
        self.assertEqual(first["candidate_id"].tolist(), second["candidate_id"].tolist())
        self.assertEqual(first["v2_selection_rank"].tolist(), [1, 2, 3, 4, 5])
        self.assertFalse(first["v2_fallback_used"].any())

    def test_missing_v2_schema_falls_back_to_frozen_v1(self):
        candidates = self.candidates().drop(columns="tpi")
        selected = select_practical_v2(candidates, "plant")
        self.assertTrue(selected["v2_fallback_used"].all())
        self.assertTrue(selected["v2_fallback_reason"].str.contains("tpi").all())
        self.assertIn("validated_core_policy", selected.columns)


if __name__ == "__main__":
    unittest.main()
