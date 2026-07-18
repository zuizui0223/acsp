import unittest

import pandas as pd

from acsp import (
    cluster_patch_recovery_table,
    equal_member_budget_baselines,
    select_gap_patches_under_member_budget,
)


class GapValidationTests(unittest.TestCase):
    def setUp(self):
        self.members = pd.DataFrame({
            "site_id": [1, 2, 3, 4, 5],
            "latitude": [35.0, 35.001, 35.10, 35.101, 35.102],
            "longitude": [139.0, 139.001, 139.10, 139.101, 139.102],
            "gap_patch_id": ["a", "a", "b", "b", "b"],
            "gap_patch_class": ["gap_separated_satellite"] * 5,
            "gap_patch_rank": [1, 1, 2, 2, 2],
            "gap_patch_score": [0.8, 0.8, 0.9, 0.9, 0.9],
            "gap_patch_support_mean": [0.8, 0.8, 0.9, 0.9, 0.9],
            "gap_patch_persistence": [1.0] * 5,
            "gap_patch_nearest_known_m": [2000.0] * 5,
            "gap_patch_width_m": [1250.0] * 5,
            "gap_patch_member_count": [2, 2, 3, 3, 3],
            "gap_patch_centroid_latitude": [35.0005, 35.0005, 35.101, 35.101, 35.101],
            "gap_patch_centroid_longitude": [139.0005, 139.0005, 139.101, 139.101, 139.101],
        })

    def test_budget_keeps_whole_patch_and_does_not_overrun(self):
        selected = select_gap_patches_under_member_budget(self.members, 2)
        self.assertEqual(selected["gap_patch_id"].unique().tolist(), ["a"])
        self.assertEqual(len(selected), 2)
        self.assertTrue(selected["gap_patch_members_used"].eq(2).all())

    def test_cluster_recovery_counts_population_once(self):
        held = pd.DataFrame({
            "cluster_id": ["x", "x", "y"],
            "latitude": [35.0, 35.0005, 36.0],
            "longitude": [139.0, 139.0005, 140.0],
        })
        result = cluster_patch_recovery_table(self.members.iloc[:2], held, radii_km=(1, 10))
        self.assertEqual(len(result), 2)
        self.assertTrue(bool(result.loc[result["cluster_id"].eq("x"), "recovered_within_1km"].iloc[0]))

    def test_equal_budget_baselines_are_reproducible(self):
        candidates = self.members[["site_id", "latitude", "longitude"]].copy()
        candidates["integrated_support_score"] = [0.9, 0.8, 0.7, 0.6, 0.5]
        known = pd.DataFrame({"latitude": [34.99], "longitude": [138.99]})
        held = pd.DataFrame({
            "cluster_id": ["x", "y"],
            "latitude": [35.0, 35.101],
            "longitude": [139.0, 139.101],
        })
        selected = self.members.iloc[:2]
        first = equal_member_budget_baselines(
            candidates, known, held, selected, random_draws=3, random_state=7
        )
        second = equal_member_budget_baselines(
            candidates, known, held, selected, random_draws=3, random_state=7
        )
        pd.testing.assert_frame_equal(first, second)
        self.assertEqual(set(first["method"]), {"gap_patch", "support_topk", "nearest_known", "random"})
        self.assertTrue(first["member_budget"].eq(2).all())


if __name__ == "__main__":
    unittest.main()
