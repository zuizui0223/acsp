import unittest

import pandas as pd

from acsp.gap_patches import (
    GapPatchConfig,
    discover_gap_patches,
    patch_recovery_table,
    summarize_gap_patches,
)


class GapPatchTests(unittest.TestCase):
    def setUp(self):
        self.known = pd.DataFrame({"latitude": [35.0], "longitude": [139.0]})
        self.candidates = pd.DataFrame(
            {
                "site_id": ["a1", "a2", "s1", "s2", "o1", "o2", "noise"],
                "latitude": [
                    35.001,
                    35.004,
                    35.050,
                    35.054,
                    35.300,
                    35.304,
                    35.150,
                ],
                "longitude": [139.001, 139.004, 139.050, 139.054, 139.300, 139.304, 139.150],
                "integrated_support_score": [0.92, 0.88, 0.86, 0.82, 0.80, 0.77, 0.20],
            }
        )
        self.config = GapPatchConfig(
            support_thresholds=(0.45, 0.65, 0.75),
            link_distance_m=1_000,
            anchor_radius_m=1_000,
            satellite_max_distance_m=15_000,
            min_patch_members=2,
        )

    def test_discovers_anchor_satellite_and_outpost_components(self):
        members = discover_gap_patches(self.candidates, self.known, config=self.config)
        classes = set(members["gap_patch_class"])
        self.assertEqual(
            classes,
            {"anchor_expansion", "gap_separated_satellite", "environmental_analogue_outpost"},
        )
        self.assertNotIn("noise", members["site_id"].tolist())
        self.assertTrue(members["gap_patch_persistence"].between(0, 1).all())
        self.assertTrue(members["gap_patch_score"].between(0, 1).all())

    def test_patch_summary_has_one_row_per_patch(self):
        members = discover_gap_patches(self.candidates, self.known, config=self.config)
        summary = summarize_gap_patches(members)
        self.assertEqual(len(summary), members["gap_patch_id"].nunique())
        self.assertEqual(summary["gap_patch_rank"].tolist(), sorted(summary["gap_patch_rank"]))

    def test_recovery_uses_patch_members_not_only_centroids(self):
        members = discover_gap_patches(self.candidates, self.known, config=self.config)
        satellite = members[members["gap_patch_class"].eq("gap_separated_satellite")].iloc[0]
        held_out = pd.DataFrame(
            {"latitude": [satellite["latitude"]], "longitude": [satellite["longitude"]]}
        )
        recovery = patch_recovery_table(members, held_out, radii_km=(0.1, 1.0))
        self.assertTrue(bool(recovery.loc[0, "recovered_within_0.1km"]))
        self.assertEqual(recovery.loc[0, "nearest_patch_class"], "gap_separated_satellite")

    def test_minimum_patch_members_removes_singletons(self):
        singleton = pd.DataFrame(
            {
                "site_id": ["single"],
                "latitude": [35.05],
                "longitude": [139.05],
                "integrated_support_score": [0.9],
            }
        )
        result = discover_gap_patches(singleton, self.known, config=self.config)
        self.assertTrue(result.empty)

    def test_missing_support_column_is_explicit(self):
        with self.assertRaisesRegex(ValueError, "support column"):
            discover_gap_patches(self.candidates.drop(columns="integrated_support_score"), self.known)


if __name__ == "__main__":
    unittest.main()
