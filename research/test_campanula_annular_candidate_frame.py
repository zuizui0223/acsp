from __future__ import annotations

import unittest

import pandas as pd

from evaluate_campanula_annular_candidate_frame import (
    _matched_random_recovery_probability,
    evaluate_annular_candidate_frame,
    prepare_candidate_universe,
)


class CampanulaAnnularCandidateFrameTests(unittest.TestCase):
    def test_candidate_aliases_are_normalized(self):
        universe = pd.DataFrame(
            {"island": ["Alpha"], "lat": [0.1], "lon": [0.2]}
        )
        out = prepare_candidate_universe(universe)
        self.assertEqual(out.iloc[0]["island"], "alpha")
        self.assertEqual(int(out.iloc[0]["candidate_cell_id"]), 0)

    def test_exact_random_probability_boundaries(self):
        self.assertEqual(_matched_random_recovery_probability(10, 0, 5), 0.0)
        self.assertEqual(_matched_random_recovery_probability(10, 3, 0), 0.0)
        self.assertEqual(_matched_random_recovery_probability(10, 3, 8), 1.0)
        expected = 1.0 - (6.0 / 10.0) * (5.0 / 9.0)
        self.assertAlmostEqual(
            _matched_random_recovery_probability(10, 4, 2), expected
        )

    def test_annular_frame_uses_retained_anchors_and_keeps_absent_fold(self):
        universe = pd.DataFrame(
            {
                "island": ["alpha"] * 7 + ["beta"],
                "lat": [0.0] * 8,
                "lon": [0.000, 0.0045, 0.009, 0.0135, 0.018, 0.0225, 0.027, 2.5],
            }
        )
        clusters = pd.DataFrame(
            {
                "historical_cluster_id": [1, 2, 3],
                "cluster_policy": ["single_link", "single_link", "single_link"],
                "island": ["alpha", "alpha", "beta"],
                "latitude": [0.0, 0.0, 0.0],
                "longitude": [0.0, 0.018, 2.5],
            }
        )
        folds, aggregate, summary = evaluate_annular_candidate_frame(
            universe,
            clusters,
            exclusion_radius_km=0.5,
            outer_radii_km=(1.0, 3.0),
            recovery_radii_km=(0.25, 0.5),
        )
        alpha_hidden_2 = folds.loc[
            folds["cluster_policy"].eq("single_link")
            & folds["hidden_cluster_id"].eq(2)
            & folds["outer_radius_km"].eq(3.0)
        ].iloc[0]
        self.assertEqual(int(alpha_hidden_2["retained_same_island_anchor_count"]), 1)
        self.assertGreater(int(alpha_hidden_2["selected_annular_cells"]), 0)
        self.assertTrue(bool(alpha_hidden_2["recovered_0.25km"]))

        beta = folds.loc[folds["island"].eq("beta")]
        self.assertTrue(beta["anchor_absent"].astype(bool).all())
        self.assertEqual(int(beta["selected_annular_cells"].sum()), 0)
        self.assertFalse(beta["recovered_0.5km"].astype(bool).any())
        self.assertEqual(summary["candidate_universe_rows"], 8)
        self.assertFalse(summary["reads_2026_field_outcomes"])
        self.assertFalse(aggregate.empty)

    def test_known_point_exclusion_removes_trivial_cells(self):
        universe = pd.DataFrame(
            {
                "island": ["alpha"] * 3,
                "latitude": [0.0, 0.0, 0.0],
                "longitude": [0.0, 0.004, 0.012],
            }
        )
        clusters = pd.DataFrame(
            {
                "historical_cluster_id": [1, 2],
                "cluster_policy": ["single_link", "single_link"],
                "island": ["alpha", "alpha"],
                "latitude": [0.0, 0.0],
                "longitude": [0.0, 0.012],
            }
        )
        folds, _, _ = evaluate_annular_candidate_frame(
            universe,
            clusters,
            exclusion_radius_km=0.5,
            outer_radii_km=(2.0,),
            recovery_radii_km=(0.25,),
        )
        hidden_two = folds.loc[folds["hidden_cluster_id"].eq(2)].iloc[0]
        self.assertEqual(int(hidden_two["eligible_cells_outside_exclusion"]), 1)
        self.assertEqual(int(hidden_two["selected_annular_cells"]), 1)


if __name__ == "__main__":
    unittest.main()
