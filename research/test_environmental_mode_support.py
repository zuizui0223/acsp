from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from campanula_ndvi_microclimate_hybrid import NDVI_STATE, fit_distance_rank
from environmental_mode_support import infer_modes, multimodal_support_mask


def frame(values):
    values = np.asarray(values, dtype=float)
    return pd.DataFrame({name: values + i * 0.001 for i, name in enumerate(NDVI_STATE)})


class EnvironmentalModeSupportTests(unittest.TestCase):
    def test_single_mode_is_exactly_existing_support(self):
        train = frame([0.0, 0.1, 0.2, 0.3, 0.4, 0.5])
        grid = frame(np.linspace(-0.2, 0.8, 41))
        geometry, _ = infer_modes(train, NDVI_STATE)
        self.assertEqual(geometry.component_count, 1)
        for q in (0.05, 0.10, 0.25, 0.50, 0.75):
            _, rank = fit_distance_rank(grid, train, NDVI_STATE)
            expected = rank <= q + 1e-12
            observed, info = multimodal_support_mask(grid, train, NDVI_STATE, q)
            np.testing.assert_array_equal(observed, expected)
            self.assertTrue(info["single_mode_identity"])

    def test_two_modes_preserve_exact_global_support_size(self):
        train = frame([0.0, 0.1, 10.0, 10.1, 10.2, 0.2])
        grid_values = np.array([0.00, 0.01, 0.02, 0.03, 0.04, 0.05, 9.98, 10.00, 10.02, 10.04, 5.0, 6.0])
        grid = frame(grid_values)
        geometry, _ = infer_modes(train, NDVI_STATE)
        self.assertGreaterEqual(geometry.component_count, 2)
        q = 0.50
        _, rank = fit_distance_rank(grid, train, NDVI_STATE)
        target = int((rank <= q + 1e-12).sum())
        observed, info = multimodal_support_mask(grid, train, NDVI_STATE, q)
        self.assertEqual(int(observed.sum()), target)
        self.assertEqual(info["target_cells"], target)

    def test_balancing_gives_each_separated_mode_support(self):
        train = frame([0.0, 0.1, 10.0, 10.1, 10.2, 0.2])
        grid_values = np.array([0.000, 0.005, 0.010, 0.015, 0.020, 0.025, 9.99, 10.01, 10.03, 10.05, 4.0, 6.0])
        grid = frame(grid_values)
        mask, info = multimodal_support_mask(grid, train, NDVI_STATE, 0.50)
        self.assertGreaterEqual(info["component_count"], 2)
        chosen = grid_values[mask]
        self.assertGreaterEqual(int((chosen < 1.0).sum()), 2)
        self.assertGreaterEqual(int((chosen > 9.0).sum()), 2)

    def test_q1_returns_whole_grid(self):
        train = frame([0.0, 0.1, 10.0, 10.1])
        grid = frame(np.linspace(0, 10, 20))
        mask, info = multimodal_support_mask(grid, train, NDVI_STATE, 1.0)
        self.assertTrue(mask.all())
        self.assertEqual(info["target_cells"], len(grid))


if __name__ == "__main__":
    unittest.main()
