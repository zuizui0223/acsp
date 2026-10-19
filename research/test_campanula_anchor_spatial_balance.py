from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from evaluate_campanula_anchor_spatial_balance import (
    evaluate_anchor_spatial_balance,
    morton_order,
    systematic_morton_sample,
)


class AnchorSpatialBalanceTests(unittest.TestCase):
    def test_systematic_morton_sample_has_exact_unique_count(self):
        frame = pd.DataFrame(
            {
                "candidate_cell_id": np.arange(16),
                "latitude": np.repeat([0.0, 0.01, 0.02, 0.03], 4),
                "longitude": np.tile([0.0, 0.01, 0.02, 0.03], 4),
            }
        )
        order = morton_order(frame)
        self.assertEqual(len(order), 16)
        self.assertEqual(len(np.unique(order)), 16)

        selected = systematic_morton_sample(frame, 4)
        self.assertEqual(len(selected), 4)
        self.assertEqual(selected["candidate_cell_id"].nunique(), 4)
        # A systematic sample on the space-filling order must span more than one
        # row and column of this synthetic square rather than collapsing locally.
        self.assertGreater(selected["latitude"].nunique(), 1)
        self.assertGreater(selected["longitude"].nunique(), 1)

    def test_full_fraction_matches_complete_annulus_and_zero_random_lift(self):
        universe = pd.DataFrame(
            {
                "island": ["alpha"] * 7,
                "lat": [0.0] * 7,
                "lon": [0.006, 0.008, 0.010, 0.012, 0.014, 0.016, 0.018],
            }
        )
        clusters = pd.DataFrame(
            [
                {
                    "historical_cluster_id": 1,
                    "cluster_policy": "single_link",
                    "island": "alpha",
                    "latitude": 0.0,
                    "longitude": 0.0,
                },
                {
                    "historical_cluster_id": 2,
                    "cluster_policy": "single_link",
                    "island": "alpha",
                    "latitude": 0.0,
                    "longitude": 0.014,
                },
            ]
        )
        folds, aggregate, summary = evaluate_anchor_spatial_balance(
            universe,
            clusters,
            exclusion_radius_km=0.5,
            outer_radii_km=(2.0,),
            selection_fractions=(0.25, 1.0),
            recovery_radii_km=(0.25,),
        )
        full = folds.loc[folds["selection_fraction_of_annulus"].eq(1.0)]
        self.assertTrue(
            (
                full["selected_spatially_balanced_cells"]
                == full["annular_cells"]
            ).all()
        )
        full_aggregate = aggregate.loc[
            aggregate["selection_fraction_of_annulus"].eq(1.0)
        ].iloc[0]
        self.assertAlmostEqual(
            float(full_aggregate["mean_lift_over_matched_annulus_random"]),
            0.0,
        )
        self.assertFalse(summary["reads_2026_field_outcomes"])
        self.assertFalse(
            summary["hidden_cluster_coordinates_used_for_candidate_selection"]
        )

    def test_anchor_absent_fold_is_retained_with_zero_selection(self):
        universe = pd.DataFrame(
            {
                "island": ["alpha", "beta"],
                "latitude": [0.0, 0.0],
                "longitude": [0.01, 2.5],
            }
        )
        clusters = pd.DataFrame(
            [
                {
                    "historical_cluster_id": 1,
                    "cluster_policy": "single_link",
                    "island": "alpha",
                    "latitude": 0.0,
                    "longitude": 0.0,
                },
                {
                    "historical_cluster_id": 2,
                    "cluster_policy": "single_link",
                    "island": "beta",
                    "latitude": 0.0,
                    "longitude": 2.5,
                },
            ]
        )
        folds, _, _ = evaluate_anchor_spatial_balance(
            universe,
            clusters,
            exclusion_radius_km=0.5,
            outer_radii_km=(2.0,),
            selection_fractions=(1.0,),
            recovery_radii_km=(0.5,),
        )
        self.assertTrue(folds["anchor_absent"].astype(bool).all())
        self.assertEqual(
            int(folds["selected_spatially_balanced_cells"].sum()), 0
        )
        self.assertFalse(folds["recovered_0.5km"].astype(bool).any())

    def test_hidden_coordinate_changes_scoring_not_selection_count(self):
        universe = pd.DataFrame(
            {
                "island": ["alpha"] * 6,
                "latitude": [0.0] * 6,
                "longitude": [0.006, 0.008, 0.010, 0.012, 0.014, 0.016],
            }
        )
        first = pd.DataFrame(
            [
                {
                    "historical_cluster_id": 1,
                    "cluster_policy": "single_link",
                    "island": "alpha",
                    "latitude": 0.0,
                    "longitude": 0.0,
                },
                {
                    "historical_cluster_id": 2,
                    "cluster_policy": "single_link",
                    "island": "alpha",
                    "latitude": 0.0,
                    "longitude": 0.012,
                },
            ]
        )
        second = first.copy()
        second.loc[second["historical_cluster_id"].eq(2), "longitude"] = 0.016

        result_a, _, _ = evaluate_anchor_spatial_balance(
            universe,
            first,
            outer_radii_km=(2.0,),
            selection_fractions=(0.5,),
            recovery_radii_km=(0.25,),
        )
        result_b, _, _ = evaluate_anchor_spatial_balance(
            universe,
            second,
            outer_radii_km=(2.0,),
            selection_fractions=(0.5,),
            recovery_radii_km=(0.25,),
        )
        hidden_two_a = result_a.loc[result_a["hidden_cluster_id"].eq(2)].iloc[0]
        hidden_two_b = result_b.loc[result_b["hidden_cluster_id"].eq(2)].iloc[0]
        self.assertEqual(
            int(hidden_two_a["annular_cells"]),
            int(hidden_two_b["annular_cells"]),
        )
        self.assertEqual(
            int(hidden_two_a["selected_spatially_balanced_cells"]),
            int(hidden_two_b["selected_spatially_balanced_cells"]),
        )

    def test_fraction_validation(self):
        universe = pd.DataFrame(
            {"island": ["alpha"], "latitude": [0.0], "longitude": [0.01]}
        )
        clusters = pd.DataFrame(
            [
                {
                    "historical_cluster_id": 1,
                    "cluster_policy": "single_link",
                    "island": "alpha",
                    "latitude": 0.0,
                    "longitude": 0.0,
                }
            ]
        )
        with self.assertRaises(ValueError):
            evaluate_anchor_spatial_balance(
                universe, clusters, selection_fractions=(0.0,)
            )


if __name__ == "__main__":
    unittest.main()
