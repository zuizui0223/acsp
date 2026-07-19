import unittest

import pandas as pd

from acsp.occurrence_patch_connectivity import (
    OccurrencePatchConnectivityConfig,
    annotate_occurrence_patch_connectivity,
    build_occurrence_patches,
)


class OccurrencePatchConnectivityTests(unittest.TestCase):
    def test_known_occurrences_are_grouped_into_spatial_patches(self):
        known = pd.DataFrame({
            "latitude": [35.0, 35.001, 35.05],
            "longitude": [139.0, 139.001, 139.05],
        })
        result = build_occurrence_patches(known, link_distance_m=500)
        self.assertEqual(result["occurrence_patch_id"].nunique(), 2)
        self.assertEqual(result.loc[0, "occurrence_patch_id"], result.loc[1, "occurrence_patch_id"])

    def test_close_but_disconnected_candidate_patch_is_identified(self):
        known = pd.DataFrame({"latitude": [35.0], "longitude": [139.0]})
        candidates = pd.DataFrame({
            "gap_patch_id": ["p1", "p1"],
            "latitude": [35.012, 35.013],
            "longitude": [139.0, 139.0],
        })
        config = OccurrencePatchConnectivityConfig(
            occurrence_link_distance_m=500,
            candidate_occurrence_link_distance_m=750,
            near_disconnected_max_distance_m=3000,
        )
        result = annotate_occurrence_patch_connectivity(candidates, known, config=config)
        self.assertTrue(
            result["occurrence_patch_connectivity_class"]
            .eq("near_disconnected_occurrence_patch")
            .all()
        )
        self.assertTrue(result["candidate_occurrence_gap_width_m"].gt(0).all())

    def test_touching_candidate_patch_is_extension(self):
        known = pd.DataFrame({"latitude": [35.0], "longitude": [139.0]})
        candidates = pd.DataFrame({
            "gap_patch_id": ["p1"],
            "latitude": [35.003],
            "longitude": [139.0],
        })
        result = annotate_occurrence_patch_connectivity(candidates, known)
        self.assertEqual(
            result.loc[0, "occurrence_patch_connectivity_class"],
            "occurrence_patch_extension",
        )


if __name__ == "__main__":
    unittest.main()
