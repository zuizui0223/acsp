import unittest

import pandas as pd

from acsp.decision_baselines import (
    DecisionBaselineConfig,
    compare_decision_baselines,
    random_same_pool_sets,
    select_dual_space_farthest,
    select_environmental_farthest,
    select_geographic_farthest,
    select_score_top_k,
)


class DecisionBaselineTests(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame({
            "site_id": ["a", "b", "c", "d"],
            "latitude": [0.0, 0.0, 0.0, 10.0],
            "longitude": [0.0, 0.1, 5.0, 0.0],
            "component_local_habitat_score": [0.9, 0.8, 0.2, 0.1],
            "bio1": [0.0, 0.1, 5.0, 0.0],
            "bio12": [0.0, 0.1, 0.0, 8.0],
            "covered_heldout_ids": ["h1", "h1", "h2", "h3"],
            "all_heldout_ids": ["h1;h2;h3"] * 4,
        })
        self.config = DecisionBaselineConfig(
            k=2,
            environmental_cols=("bio1", "bio12"),
            random_draws=10,
            random_state=9,
        )

    def test_score_top_k(self):
        self.assertEqual(
            select_score_top_k(self.frame, self.config)["site_id"].tolist(),
            ["a", "b"],
        )

    def test_geographic_and_environmental_are_deterministic(self):
        first = select_geographic_farthest(self.frame, self.config)["site_id"].tolist()
        second = select_geographic_farthest(
            self.frame.sample(frac=1, random_state=3), self.config
        )["site_id"].tolist()
        self.assertEqual(set(first), set(second))
        self.assertEqual(len(select_environmental_farthest(self.frame, self.config)), 2)
        self.assertEqual(len(select_dual_space_farthest(self.frame, self.config)), 2)

    def test_random_draws_are_reproducible(self):
        left = [draw["site_id"].tolist() for draw in random_same_pool_sets(self.frame, self.config)]
        right = [draw["site_id"].tolist() for draw in random_same_pool_sets(self.frame, self.config)]
        self.assertEqual(left, right)

    def test_comparator_table(self):
        result = compare_decision_baselines(self.frame, self.config)
        self.assertIn("random_same_pool_mean", set(result["decision_method"]))
        self.assertTrue(result["heldout_recall"].between(0, 1).all())


if __name__ == "__main__":
    unittest.main()
