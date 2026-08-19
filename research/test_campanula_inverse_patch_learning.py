import unittest

import numpy as np

from campanula_inverse_patch_learning import characterize_minimum_cover_family


class MinimumCoverFamilyTests(unittest.TestCase):
    def test_all_tied_minimum_cover_members_are_compatible(self):
        # Two independent choices for each of two detections: every patch occurs
        # in some two-patch optimum, but no patch is individually necessary.
        coverage = np.array([
            [1, 0, 1, 0],
            [0, 1, 0, 1],
        ], dtype=float)
        family = characterize_minimum_cover_family(coverage, time_limit=2.0)
        self.assertEqual(family["minimum_size"], 2)
        self.assertTrue(np.asarray(family["compatible"]).all())
        self.assertFalse(np.asarray(family["necessary"]).any())

    def test_patch_can_be_necessary_without_using_one_solver_solution_as_label(self):
        # Patch 2 alone covers both detections. If it is excluded the optimum
        # rises to two patches, so it is both compatible and necessary.
        coverage = np.array([
            [1, 0, 1],
            [0, 1, 1],
        ], dtype=float)
        family = characterize_minimum_cover_family(coverage, time_limit=2.0)
        compatible = np.asarray(family["compatible"])
        necessary = np.asarray(family["necessary"])
        self.assertEqual(family["minimum_size"], 1)
        self.assertEqual(compatible.tolist(), [False, False, True])
        self.assertEqual(necessary.tolist(), [False, False, True])


if __name__ == "__main__":
    unittest.main()
