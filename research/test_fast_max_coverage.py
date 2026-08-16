from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from develop_izu_strong_coverage_comparator import build_geometry
from develop_izu_strong_coverage_sweep import greedy_coverage_order as reference
from fast_max_coverage import greedy_coverage_order_fast


class FastMaxCoverageTests(unittest.TestCase):
    def grid(self):
        rows = []
        for island, lon0, lat0 in [("a", 139.0, 34.0), ("b", 140.0, 35.0)]:
            for iy in range(5):
                for ix in range(6):
                    rows.append(
                        {
                            "island": island,
                            "lat": lat0 + iy * 0.002,
                            "lon": lon0 + ix * 0.002,
                            "cell": f"{island}-{iy}-{ix}",
                        }
                    )
        return pd.DataFrame(rows).reset_index(drop=True)

    def test_exact_match_across_masks_budgets_and_radii(self):
        grid = self.grid()
        geometry = build_geometry(grid)
        rng = np.random.default_rng(20260816)
        masks = [
            np.ones(len(grid), dtype=bool),
            np.arange(len(grid)) % 2 == 0,
            rng.random(len(grid)) < 0.37,
            rng.random(len(grid)) < 0.75,
        ]
        for radius in (0.15, 0.35, 0.75, 1.0):
            for mask in masks:
                for budget in (1, 3, 5, 10, 20):
                    with self.subTest(radius=radius, budget=budget, n=int(mask.sum())):
                        old = reference(
                            grid, geometry, mask, max_budget=budget, radius_km=radius
                        )
                        new = greedy_coverage_order_fast(
                            grid, geometry, mask, max_budget=budget, radius_km=radius
                        )
                        self.assertEqual(old["cell"].tolist(), new["cell"].tolist())

    def test_empty_eligibility_matches_reference(self):
        grid = self.grid()
        geometry = build_geometry(grid)
        mask = np.zeros(len(grid), dtype=bool)
        old = reference(grid, geometry, mask, max_budget=5, radius_km=1.0)
        new = greedy_coverage_order_fast(grid, geometry, mask, max_budget=5, radius_km=1.0)
        self.assertTrue(old.empty)
        self.assertTrue(new.empty)


if __name__ == "__main__":
    unittest.main()
