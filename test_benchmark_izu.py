import unittest

import pandas as pd

from benchmark_izu_random_taxa import ISLAND_BOUNDS, _coverage_at_radius, island_features, island_wkt


class IzuBenchmarkTests(unittest.TestCase):
    def test_sampling_frame_contains_four_independent_islands(self):
        self.assertEqual(len(ISLAND_BOUNDS), 4)
        self.assertEqual(len(island_features()), 4)
        self.assertTrue(island_wkt().startswith("MULTIPOLYGON("))

    def test_radius_sensitivity_reuses_stored_distances(self):
        candidates = pd.DataFrame({
            "all_heldout_ids": ["0;1;2"],
            "heldout_distances_km": ["1.0;4.0;8.0"],
            "covered_heldout_ids": [""],
        })
        self.assertEqual(_coverage_at_radius(candidates, 2)["covered_heldout_ids"].iloc[0], "0")
        self.assertEqual(_coverage_at_radius(candidates, 5)["covered_heldout_ids"].iloc[0], "0;1")
        self.assertEqual(_coverage_at_radius(candidates, 10)["covered_heldout_ids"].iloc[0], "0;1;2")


if __name__ == "__main__":
    unittest.main()
