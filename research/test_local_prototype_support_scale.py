from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from campanula_ndvi_microclimate_hybrid import NDVI_STATE, fit_distance_rank
from local_prototype_support_scale import LocalScaleFamily


def frame(values):
    values = np.asarray(values, dtype=float)
    return pd.DataFrame({name: values + i * 0.01 for i, name in enumerate(NDVI_STATE)})


class LocalPrototypeSupportScaleTests(unittest.TestCase):
    def test_k1_is_exact_historical_mask(self):
        train = frame([0.0, 0.1, 0.2, 1.0, 1.1, 1.2])
        grid = frame(np.linspace(-0.2, 1.4, 81))
        family = LocalScaleFamily.build(grid, train, NDVI_STATE, [1, 2, 3])
        _, rank = fit_distance_rank(grid, train, NDVI_STATE)
        for q in (0.05, 0.10, 0.25, 0.50, 0.75):
            np.testing.assert_array_equal(family.mask(1, q), rank <= q + 1e-12)

    def test_all_k_match_k1_support_cardinality(self):
        train = frame([0.0, 0.1, 0.2, 1.0, 1.1, 1.2])
        grid = frame(np.linspace(-0.2, 1.4, 81))
        family = LocalScaleFamily.build(grid, train, NDVI_STATE, [1, 2, 3])
        for q in (0.05, 0.10, 0.25, 0.50, 0.75):
            target = int(family.mask(1, q).sum())
            self.assertEqual(int(family.mask(2, q).sum()), target)
            self.assertEqual(int(family.mask(3, q).sum()), target)

    def test_multiple_neighbours_penalize_single_isolated_prototype(self):
        # Five prototypes form a local mode near zero and one is isolated near 10.
        # k=1 strongly supports the isolated point; k=3 requires local agreement
        # and therefore favors the replicated mode at the same support area.
        train = frame([0.0, 0.02, 0.04, 0.06, 0.08, 10.0])
        grid_values = np.array([0.0, 0.01, 0.03, 0.05, 0.07, 0.09, 9.99, 10.0, 10.01, 4.0, 6.0])
        grid = frame(grid_values)
        family = LocalScaleFamily.build(grid, train, NDVI_STATE, [1, 2, 3])
        q = 0.25
        k1 = grid_values[family.mask(1, q)]
        k3 = grid_values[family.mask(3, q)]
        self.assertEqual(len(k1), len(k3))
        self.assertTrue(np.any(k1 > 9.0))
        self.assertTrue(np.all(k3 < 1.0))

    def test_q1_is_whole_grid_for_every_k(self):
        train = frame([0, 1, 2, 3, 4, 5])
        grid = frame(np.linspace(0, 5, 20))
        family = LocalScaleFamily.build(grid, train, NDVI_STATE, [1, 2, 3])
        for k in (1, 2, 3):
            self.assertTrue(family.mask(k, 1.0).all())

    def test_requested_k_must_be_supported_by_training_size(self):
        train = frame([0, 1])
        grid = frame(np.linspace(0, 1, 10))
        with self.assertRaises(ValueError):
            LocalScaleFamily.build(grid, train, NDVI_STATE, [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
