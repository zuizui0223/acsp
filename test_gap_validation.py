import unittest

import pandas as pd

from acsp import cluster_patch_recovery_table, select_gap_patches_within_travel_distance


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
            "gap_patch_nearest_known_m": [100.0, 100.0, 5000.0, 5000.0, 5000.0],
            "gap_patch_width_m": [0.0, 0.0, 4250.0, 4250.0, 4250.0],
            "gap_patch_member_count": [2, 2, 3, 3, 3],
            "gap_patch_centroid_latitude": [35.0005, 35.0005, 35.101, 35.101, 35.101],
            "gap_patch_centroid_longitude": [139.0005, 139.0005, 139.101, 139.101, 139.101],
        })

    def test_travel_limit_keeps_whole_reachable_patch(self):
        selected = select_gap_patches_within_travel_distance(
            self.members, 35.0, 139.0, 5_000
        )
        self.assertEqual(selected["gap_patch_id"].unique().tolist(), ["a"])
        self.assertEqual(len(selected), 2)
        self.assertTrue(selected["gap_patch_route_distance_m"].le(5_000).all())

    def test_longer_travel_limit_can_add_second_patch(self):
        selected = select_gap_patches_within_travel_distance(
            self.members, 35.0, 139.0, 40_000
        )
        self.assertEqual(set(selected["gap_patch_id"]), {"a", "b"})

    def test_priority_column_changes_first_selected_patch(self):
        selected = select_gap_patches_within_travel_distance(
            self.members,
            35.05,
            139.05,
            40_000,
            priority_col="gap_patch_nearest_known_m",
            higher_priority_is_better=False,
        )
        self.assertEqual(selected.sort_values("gap_patch_selection_rank")["gap_patch_id"].iloc[0], "a")
        self.assertTrue(selected["gap_patch_selection_priority_col"].eq("gap_patch_nearest_known_m").all())

    def test_missing_priority_column_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "priority column"):
            select_gap_patches_within_travel_distance(
                self.members, 35.0, 139.0, 40_000, priority_col="missing"
            )

    def test_cluster_recovery_counts_population_once(self):
        held = pd.DataFrame({
            "cluster_id": ["x", "x", "y"],
            "latitude": [35.0, 35.0005, 36.0],
            "longitude": [139.0, 139.0005, 140.0],
        })
        result = cluster_patch_recovery_table(self.members.iloc[:2], held, radii_km=(1, 10))
        self.assertEqual(len(result), 2)
        self.assertTrue(bool(result.loc[result["cluster_id"].eq("x"), "recovered_within_1km"].iloc[0]))


if __name__ == "__main__":
    unittest.main()
