from __future__ import annotations

import unittest

import pandas as pd

from diagnose_campanula_occurrence_anchor import (
    assign_island,
    classify_anchor_distance,
    diagnose_occurrence_anchors,
)


class CampanulaOccurrenceAnchorDiagnosticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bounds = {
            "alpha": [0.0, 0.0, 1.0, 1.0],
            "beta": [2.0, 0.0, 3.0, 1.0],
        }

    def test_assign_island_uses_frozen_lon_lat_order(self):
        self.assertEqual(assign_island(0.5, 0.5, self.bounds), "alpha")
        self.assertEqual(assign_island(0.5, 2.5, self.bounds), "beta")
        self.assertIsNone(assign_island(5.0, 5.0, self.bounds))

    def test_anchor_regimes_are_separate(self):
        self.assertEqual(
            classify_anchor_distance(
                0.5, local_radius_km=2.0, tail_radius_km=5.0
            ),
            "local_continuation",
        )
        self.assertEqual(
            classify_anchor_distance(
                3.0, local_radius_km=2.0, tail_radius_km=5.0
            ),
            "regional_tail",
        )
        self.assertEqual(
            classify_anchor_distance(
                6.0, local_radius_km=2.0, tail_radius_km=5.0
            ),
            "distant_tail",
        )
        self.assertEqual(
            classify_anchor_distance(
                None, local_radius_km=2.0, tail_radius_km=5.0
            ),
            "anchor_absent",
        )

    def test_duplicate_occurrences_are_one_anchor(self):
        occurrences = pd.DataFrame(
            {
                "_latitude": [0.1, 0.1],
                "_longitude": [0.1, 0.1],
            }
        )
        clusters = pd.DataFrame(
            {
                "detection_cluster_id": [1, 2],
                "island": ["alpha", "beta"],
                "latitude": [0.105, 0.5],
                "longitude": [0.1, 2.5],
            }
        )
        diagnostics, summary = diagnose_occurrence_anchors(
            occurrences,
            clusters,
            self.bounds,
            local_radius_km=2.0,
            tail_radius_km=5.0,
        )
        alpha = diagnostics.loc[diagnostics["island"] == "alpha"].iloc[0]
        beta = diagnostics.loc[diagnostics["island"] == "beta"].iloc[0]
        self.assertEqual(int(alpha["same_island_unique_anchor_count"]), 1)
        self.assertEqual(alpha["anchor_regime"], "local_continuation")
        self.assertEqual(int(beta["same_island_unique_anchor_count"]), 0)
        self.assertEqual(beta["anchor_regime"], "anchor_absent")
        self.assertEqual(summary["clusters_without_same_island_anchor"], 1)


if __name__ == "__main__":
    unittest.main()
