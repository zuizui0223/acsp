from __future__ import annotations

import unittest

import pandas as pd

from evaluate_campanula_occurrence_anchor_loco import (
    annular_baseline_curve,
    cluster_occurrence_points,
    evaluate_occurrence_anchor_loco,
    leave_one_cluster_out_distances,
)


class CampanulaOccurrenceAnchorLocoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bounds = {
            "alpha": [0.0, 0.0, 1.0, 1.0],
            "beta": [2.0, 0.0, 3.0, 1.0],
        }

    def test_single_link_chain_is_audited_and_complete_link_splits(self):
        points = pd.DataFrame(
            {
                "source_occurrence_id": ["1", "2", "3"],
                "island": ["alpha"] * 3,
                "latitude": [0.0, 0.0, 0.0],
                "longitude": [0.0, 0.004, 0.008],
            }
        )
        single = cluster_occurrence_points(
            points, cluster_radius_m=500.0, policy="single_link"
        )
        complete = cluster_occurrence_points(
            points, cluster_radius_m=500.0, policy="complete_link"
        )
        self.assertEqual(len(single), 1)
        self.assertTrue(bool(single.iloc[0]["single_link_chain_warning"]))
        self.assertEqual(len(complete), 2)
        self.assertTrue((complete["cluster_diameter_m"] <= 500.0 + 1e-9).all())

    def test_whole_cluster_holdout_prevents_duplicate_leakage(self):
        occurrences = pd.DataFrame(
            {
                "_latitude": [0.1, 0.1, 0.1],
                "_longitude": [0.1, 0.1, 0.12],
                "_row_id": [1, 2, 3],
            }
        )
        clusters, folds, curve, summary = evaluate_occurrence_anchor_loco(
            occurrences,
            self.bounds,
            cluster_radius_m=500.0,
            exclusion_radius_km=0.5,
            outer_radii_km=(1.0, 3.0),
        )
        primary = clusters.loc[clusters["cluster_policy"].eq("single_link")]
        self.assertEqual(len(primary), 2)
        duplicate_cluster = primary.loc[primary["n_source_rows"].eq(2)].iloc[0]
        fold = folds.loc[
            folds["cluster_policy"].eq("single_link")
            & folds["hidden_cluster_id"].eq(
                duplicate_cluster["historical_cluster_id"]
            )
        ].iloc[0]
        self.assertEqual(int(fold["retained_same_island_anchor_count"]), 1)
        self.assertGreater(float(fold["nearest_retained_anchor_km"]), 0.5)
        self.assertEqual(summary["historical_rows_inside_five_islands"], 3)
        self.assertFalse(summary["reads_2026_field_outcomes"])
        self.assertFalse(curve.empty)

    def test_anchor_absent_fold_is_retained_as_zero(self):
        clusters = pd.DataFrame(
            {
                "historical_cluster_id": [1],
                "cluster_policy": ["single_link"],
                "island": ["alpha"],
                "latitude": [0.1],
                "longitude": [0.1],
            }
        )
        folds = leave_one_cluster_out_distances(
            clusters, exclusion_radius_km=0.5, outer_radii_km=(1.0, 2.0)
        )
        self.assertTrue(bool(folds.iloc[0]["anchor_absent"]))
        self.assertFalse(bool(folds.iloc[0]["recovered_annulus_2km"]))
        curve = annular_baseline_curve(folds, outer_radii_km=(1.0, 2.0))
        self.assertEqual(int(curve.iloc[0]["anchor_absent_folds"]), 1)
        self.assertEqual(float(curve.iloc[0]["intention_to_evaluate_recall"]), 0.0)

    def test_outer_radius_must_exceed_exclusion(self):
        clusters = pd.DataFrame(
            {
                "historical_cluster_id": [1],
                "cluster_policy": ["single_link"],
                "island": ["alpha"],
                "latitude": [0.1],
                "longitude": [0.1],
            }
        )
        with self.assertRaises(ValueError):
            leave_one_cluster_out_distances(
                clusters, exclusion_radius_km=0.5, outer_radii_km=(0.5,)
            )


if __name__ == "__main__":
    unittest.main()
