import unittest

import pandas as pd

from acsp.area_selection import select_area_balanced_candidates


class AreaBalancedSelectionTests(unittest.TestCase):
    def test_covers_each_declared_area_before_duplicates(self):
        candidates = pd.DataFrame({
            "site_id": [1, 2, 3, 4, 5, 6],
            "survey_area_id": ["a", "a", "a", "b", "b", "c"],
            "component_local_habitat_score": [1.0, 0.99, 0.98, 0.80, 0.79, 0.70],
            "latitude": [35.0, 35.01, 35.02, 36.0, 36.01, 37.0],
            "longitude": [139.0, 139.01, 139.02, 140.0, 140.01, 141.0],
        })
        selected = select_area_balanced_candidates(
            candidates,
            3,
            score_col="component_local_habitat_score",
            evidence_weight=1.0,
        )
        self.assertEqual(set(selected["survey_area_id"]), {"a", "b", "c"})
        self.assertEqual(selected.loc[selected["survey_area_id"].eq("a"), "site_id"].tolist(), [1])
        self.assertTrue(selected["area_coverage_required"].all())

    def test_does_not_claim_full_area_coverage_when_budget_is_smaller(self):
        candidates = pd.DataFrame({
            "site_id": [1, 2, 3],
            "survey_area_id": ["a", "b", "c"],
            "score": [0.9, 0.8, 0.7],
            "latitude": [35.0, 36.0, 37.0],
            "longitude": [139.0, 140.0, 141.0],
        })
        selected = select_area_balanced_candidates(
            candidates,
            2,
            score_col="score",
            evidence_weight=1.0,
        )
        self.assertEqual(selected["site_id"].tolist(), [1, 2])
        self.assertFalse(selected["area_coverage_required"].any())

    def test_single_area_matches_evidence_order_when_weight_is_one(self):
        candidates = pd.DataFrame({
            "site_id": [1, 2, 3],
            "survey_area_id": ["a", "a", "a"],
            "score": [0.2, 0.9, 0.5],
            "latitude": [35.0, 35.1, 35.2],
            "longitude": [139.0, 139.1, 139.2],
        })
        selected = select_area_balanced_candidates(
            candidates,
            2,
            score_col="score",
            evidence_weight=1.0,
        )
        self.assertEqual(selected["site_id"].tolist(), [2, 3])


if __name__ == "__main__":
    unittest.main()
