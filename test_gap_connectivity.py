import unittest

import pandas as pd

from acsp import (
    CorridorBarrierConfig,
    annotate_gap_patch_barriers,
    corridor_support_profile,
    summarize_corridor_barrier,
)


class GapConnectivityTests(unittest.TestCase):
    def test_profile_detects_long_low_support_run(self):
        candidates = pd.DataFrame({
            "latitude": [35.0, 35.01, 35.02, 35.03, 35.04],
            "longitude": [139.0] * 5,
            "integrated_support_score": [0.9, 0.1, 0.1, 0.1, 0.9],
        })
        cfg = CorridorBarrierConfig(
            sample_spacing_m=500,
            interpolation_radius_m=700,
            low_support_threshold=0.35,
            min_barrier_length_m=1_000,
        )
        profile = corridor_support_profile(
            candidates,
            (35.0, 139.0),
            (35.04, 139.0),
            config=cfg,
        )
        summary = summarize_corridor_barrier(profile, config=cfg)
        self.assertTrue(summary["corridor_barrier_present"])
        self.assertGreaterEqual(summary["corridor_longest_low_support_m"], 1_000)

    def test_continuous_support_has_no_barrier(self):
        candidates = pd.DataFrame({
            "latitude": [35.0, 35.01, 35.02, 35.03, 35.04],
            "longitude": [139.0] * 5,
            "integrated_support_score": [0.8] * 5,
        })
        cfg = CorridorBarrierConfig(
            sample_spacing_m=500,
            interpolation_radius_m=700,
            low_support_threshold=0.35,
            min_barrier_length_m=1_000,
        )
        profile = corridor_support_profile(
            candidates,
            (35.0, 139.0),
            (35.04, 139.0),
            config=cfg,
        )
        summary = summarize_corridor_barrier(profile, config=cfg)
        self.assertFalse(summary["corridor_barrier_present"])

    def test_annotation_separates_distance_and_ecological_gap(self):
        candidates = pd.DataFrame({
            "latitude": [35.0, 35.01, 35.02, 35.03, 35.04],
            "longitude": [139.0] * 5,
            "integrated_support_score": [0.9, 0.1, 0.1, 0.1, 0.9],
        })
        patches = pd.DataFrame({
            "site_id": [1, 2],
            "latitude": [35.039, 35.04],
            "longitude": [139.0, 139.0],
            "gap_patch_id": ["p1", "p1"],
            "gap_patch_class": ["gap_separated_satellite"] * 2,
        })
        known = pd.DataFrame({"latitude": [35.0], "longitude": [139.0]})
        cfg = CorridorBarrierConfig(
            sample_spacing_m=500,
            interpolation_radius_m=700,
            low_support_threshold=0.35,
            min_barrier_length_m=1_000,
        )
        annotated = annotate_gap_patch_barriers(candidates, patches, known, config=cfg)
        self.assertTrue(annotated["corridor_barrier_present"].all())
        self.assertTrue(annotated["gap_patch_ecological_class"].eq("barrier_separated_patch").all())


if __name__ == "__main__":
    unittest.main()
