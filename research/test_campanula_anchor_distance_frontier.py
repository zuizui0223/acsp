from __future__ import annotations

import unittest

import pandas as pd

from evaluate_campanula_anchor_distance_frontier import (
    evaluate_anchor_distance_frontier,
)


class AnchorDistanceFrontierTests(unittest.TestCase):
    def test_frontier_selects_nearest_cells_after_exclusion(self):
        universe = pd.DataFrame(
            {
                "island": ["alpha"] * 5 + ["beta"],
                "lat": [0.0] * 6,
                "lon": [0.004, 0.006, 0.010, 0.014, 0.018, 2.5],
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
                    "longitude": 0.008,
                },
                {
                    "historical_cluster_id": 3,
                    "cluster_policy": "single_link",
                    "island": "beta",
                    "latitude": 0.0,
                    "longitude": 2.5,
                },
            ]
        )
        folds, aggregate, summary = evaluate_anchor_distance_frontier(
            universe,
            clusters,
            exclusion_radius_km=0.5,
            outer_radii_km=(2.0,),
            selection_fractions=(0.25, 1.0),
            recovery_radii_km=(0.25, 0.5),
        )
        hidden_two = folds.loc[
            folds["hidden_cluster_id"].eq(2)
            & folds["selection_fraction_of_annulus"].eq(0.25)
        ].iloc[0]
        self.assertEqual(int(hidden_two["selected_frontier_cells"]), 1)
        self.assertTrue(bool(hidden_two["recovered_0.25km"]))
        self.assertGreater(
            float(hidden_two["lift_over_matched_annulus_random_0.25km"]), 0.0
        )
        beta = folds.loc[folds["island"].eq("beta")]
        self.assertTrue(beta["anchor_absent"].astype(bool).all())
        self.assertEqual(int(beta["selected_frontier_cells"].sum()), 0)
        self.assertFalse(summary["hidden_cluster_coordinates_used_for_candidate_scoring"])
        self.assertFalse(aggregate.empty)

    def test_far_hidden_cluster_is_not_leaked_into_prefix(self):
        universe = pd.DataFrame(
            {
                "island": ["alpha"] * 4,
                "latitude": [0.0] * 4,
                "longitude": [0.006, 0.010, 0.014, 0.018],
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
                    "longitude": 0.018,
                },
            ]
        )
        folds, _, _ = evaluate_anchor_distance_frontier(
            universe,
            clusters,
            exclusion_radius_km=0.5,
            outer_radii_km=(2.5,),
            selection_fractions=(0.25,),
            recovery_radii_km=(0.25,),
        )
        hidden_two = folds.loc[folds["hidden_cluster_id"].eq(2)].iloc[0]
        self.assertFalse(bool(hidden_two["recovered_0.25km"]))
        self.assertLess(
            float(hidden_two["effective_selected_frontier_outer_km"]),
            float(hidden_two["nearest_retained_anchor_km"]),
        )

    def test_fraction_validation(self):
        universe = pd.DataFrame(
            {"island": ["alpha"], "lat": [0.0], "lon": [0.01]}
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
            evaluate_anchor_distance_frontier(
                universe, clusters, selection_fractions=(1.1,)
            )


if __name__ == "__main__":
    unittest.main()
