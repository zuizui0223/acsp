import unittest

import numpy as np
import pandas as pd

from acsp.robust_patches import (
    leave_one_out_consensus_support,
    robust_environment_geometry,
    support_cells_to_patches,
)


class RobustPatchTests(unittest.TestCase):
    def setUp(self):
        self.universe = pd.DataFrame(
            {
                "latitude": [35.000, 35.004, 35.050, 35.054, 36.000],
                "longitude": [139.000, 139.004, 139.050, 139.054, 140.000],
                "survey_area_id": ["a", "a", "a", "a", "b"],
                "f1": [0.0, 0.1, 1.0, 1.1, 5.0],
                "f2": [0.0, 0.1, 1.0, 1.1, 5.0],
            }
        )
        self.prototypes = pd.DataFrame(
            {
                "f1": [0.0, 0.2, 1.0, 1.2],
                "f2": [0.0, 0.2, 1.0, 1.2],
            }
        )

    def test_environment_geometry_is_feature_name_agnostic(self):
        responsibility, rank, rows, kernel = robust_environment_geometry(
            self.universe,
            self.prototypes,
            feature_columns=["f1", "f2"],
        )
        self.assertEqual(responsibility.shape, (5, 4))
        self.assertEqual(len(rank), 5)
        self.assertEqual(len(rows), 4)
        self.assertGreaterEqual(kernel, 0.25)
        self.assertLess(rank[0], rank[-1])

    def test_leave_one_out_consensus_is_deterministic(self):
        first, first_uncertainty, audit = leave_one_out_consensus_support(
            self.universe,
            self.prototypes,
            feature_columns=["f1", "f2"],
            support_world_dtype="float32",
        )
        second, second_uncertainty, _ = leave_one_out_consensus_support(
            self.universe,
            self.prototypes,
            feature_columns=["f1", "f2"],
            support_world_dtype="float32",
        )
        np.testing.assert_array_equal(first, second)
        np.testing.assert_array_equal(first_uncertainty, second_uncertainty)
        self.assertEqual(audit.prototype_count, 4)
        self.assertEqual(audit.leave_one_out_worlds, 4)
        self.assertEqual(audit.feature_columns, ("f1", "f2"))

    def test_support_cells_become_same_area_bounded_patches(self):
        rank = np.array([0.01, 0.02, 0.03, 0.04, 0.9])
        cells, patches = support_cells_to_patches(
            self.universe,
            rank,
            threshold=0.05,
            merge_distance_m=1000.0,
        )
        self.assertEqual(len(cells), 4)
        self.assertEqual(set(patches["survey_area_id"]), {"a"})
        self.assertTrue(patches["ecological_status"].eq("robust_support_patch").all())
        self.assertTrue(patches["site_id"].eq(patches["zone_id"].astype(str)).all())
        self.assertTrue((patches["zone_radius_m"] <= 1000.0).all())

    def test_missing_feature_is_explicit_error(self):
        with self.assertRaisesRegex(ValueError, "missing environmental features"):
            robust_environment_geometry(
                self.universe,
                self.prototypes,
                feature_columns=["not_a_feature"],
            )


if __name__ == "__main__":
    unittest.main()
