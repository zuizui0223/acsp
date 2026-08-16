from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from campanula_ndvi_microclimate_hybrid import NDVI_STATE, fit_distance_rank
from spatial_ndvi_support_scale import SpatialScaleFamily, VIEW_COLUMNS


def synthetic_frame(n: int) -> pd.DataFrame:
    x = np.linspace(0.0, 1.0, n)
    return pd.DataFrame(
        {
            "ndvi_p50": x,
            "ndvi_amp": 0.2 + x * 0.1,
            "ndvi_mean100": x[::-1],
            "ndvi_amp_mean100": 0.4 + x * 0.2,
            "ndvi_mean250": np.sin(x * np.pi),
            "ndvi_amp_mean250": 0.7 - x * 0.15,
        }
    )


class SpatialNdviSupportScaleTests(unittest.TestCase):
    def test_current_multiscale_is_exact_historical_mask(self):
        grid = synthetic_frame(101)
        train = grid.iloc[[5, 20, 40, 60, 80, 95]].reset_index(drop=True)
        family = SpatialScaleFamily.build(grid, train)
        _, rank = fit_distance_rank(grid, train, list(NDVI_STATE))
        for q in (0.05, 0.10, 0.25, 0.50, 0.75):
            np.testing.assert_array_equal(
                family.mask("current_multiscale", q), rank <= q + 1e-12
            )

    def test_every_view_matches_baseline_support_cardinality(self):
        grid = synthetic_frame(101)
        train = grid.iloc[[5, 20, 40, 60, 80, 95]].reset_index(drop=True)
        family = SpatialScaleFamily.build(grid, train)
        for q in (0.05, 0.10, 0.25, 0.50, 0.75):
            target = int(family.mask("current_multiscale", q).sum())
            for view in VIEW_COLUMNS:
                with self.subTest(q=q, view=view):
                    self.assertEqual(int(family.mask(view, q).sum()), target)

    def test_q1_is_whole_grid_for_every_view(self):
        grid = synthetic_frame(37)
        train = grid.iloc[[2, 8, 14, 20, 26, 32]].reset_index(drop=True)
        family = SpatialScaleFamily.build(grid, train)
        for view in VIEW_COLUMNS:
            self.assertTrue(family.mask(view, 1.0).all())

    def test_scale_view_changes_membership_without_changing_area(self):
        grid = synthetic_frame(101)
        train = grid.iloc[[5, 20, 40, 60, 80, 95]].reset_index(drop=True)
        family = SpatialScaleFamily.build(grid, train)
        q = 0.25
        baseline = family.mask("current_multiscale", q)
        point = family.mask("point", q)
        local100 = family.mask("local100", q)
        self.assertEqual(int(baseline.sum()), int(point.sum()))
        self.assertEqual(int(baseline.sum()), int(local100.sum()))
        self.assertFalse(np.array_equal(baseline, point))
        self.assertFalse(np.array_equal(point, local100))

    def test_missing_view_is_rejected(self):
        grid = synthetic_frame(31)
        train = grid.iloc[[2, 7, 12, 17, 22, 27]].reset_index(drop=True)
        family = SpatialScaleFamily.build(grid, train)
        with self.assertRaises(KeyError):
            family.mask("not_a_view", 0.10)


if __name__ == "__main__":
    unittest.main()
