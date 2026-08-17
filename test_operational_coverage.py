import unittest

import pandas as pd

from acsp import select_maximum_coverage_sites


class OperationalCoverageTests(unittest.TestCase):
    def test_deterministic_set_coverage_prefers_cluster_centres(self):
        candidates = pd.DataFrame(
            {
                "latitude": [0.0] * 6,
                "longitude": [0.000, 0.005, 0.010, 1.000, 1.005, 1.010],
            }
        )
        selected, audit = select_maximum_coverage_sites(
            candidates, radius_km=1.0, max_sites=2
        )
        self.assertEqual(selected["_input_index"].tolist(), [1, 4])
        self.assertEqual(selected["coverage_rank"].tolist(), [1, 2])
        self.assertEqual(selected["marginal_covered_candidates"].tolist(), [3, 3])
        self.assertAlmostEqual(selected["cumulative_coverage_fraction"].iloc[-1], 1.0)
        self.assertAlmostEqual(audit.final_coverage_fraction, 1.0)

    def test_group_boundaries_prevent_cross_area_coverage(self):
        candidates = pd.DataFrame(
            {
                "latitude": [35.0, 35.0],
                "longitude": [139.0, 139.0],
                "survey_area_id": ["A", "B"],
            }
        )
        selected, audit = select_maximum_coverage_sites(
            candidates,
            radius_km=10.0,
            max_sites=2,
            group_col="survey_area_id",
        )
        self.assertEqual(selected["_input_index"].tolist(), [0, 1])
        self.assertEqual(selected["marginal_covered_candidates"].tolist(), [1, 1])
        self.assertAlmostEqual(audit.final_coverage_fraction, 1.0)

    def test_zero_budget_returns_empty_selection(self):
        candidates = pd.DataFrame({"latitude": [35.0], "longitude": [139.0]})
        selected, audit = select_maximum_coverage_sites(
            candidates, radius_km=1.0, max_sites=0
        )
        self.assertTrue(selected.empty)
        self.assertEqual(audit.selected_count, 0)
        self.assertEqual(audit.final_coverage_fraction, 0.0)


if __name__ == "__main__":
    unittest.main()
