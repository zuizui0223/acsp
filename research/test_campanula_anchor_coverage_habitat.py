from __future__ import annotations

import unittest

import pandas as pd

from evaluate_campanula_anchor_coverage_habitat import (
    coverage_constrained_habitat_sample,
    evaluate_anchor_coverage_habitat,
)
from evaluate_campanula_anchor_ndvi_filter import NDVI_FEATURES


def feature_row(value: float) -> dict[str, float]:
    return {name: float(value) for name in NDVI_FEATURES}


class CoverageConstrainedHabitatTests(unittest.TestCase):
    def test_selector_preserves_coverage_strata_and_prefers_habitat_within_each(self):
        frame = pd.DataFrame(
            [
                {"island": "alpha", "lat": 0.0, "lon": 0.001, "candidate_cell_id": 1, "environment_distance": 5.0},
                {"island": "alpha", "lat": 0.0, "lon": 0.002, "candidate_cell_id": 2, "environment_distance": 1.0},
                {"island": "alpha", "lat": 0.0, "lon": 0.003, "candidate_cell_id": 3, "environment_distance": 4.0},
                {"island": "alpha", "lat": 0.0, "lon": 0.020, "candidate_cell_id": 4, "environment_distance": 6.0},
                {"island": "alpha", "lat": 0.0, "lon": 0.021, "candidate_cell_id": 5, "environment_distance": 0.5},
                {"island": "alpha", "lat": 0.0, "lon": 0.022, "candidate_cell_id": 6, "environment_distance": 3.0},
            ]
        )
        selected = coverage_constrained_habitat_sample(frame, 2)
        self.assertEqual(len(selected), 2)
        self.assertEqual(set(selected["candidate_cell_id"].astype(int)), {2, 5})

    def test_hidden_cluster_features_do_not_affect_fold_selection(self):
        universe = pd.DataFrame(
            [
                {"island": "alpha", "lat": 0.0, "lon": 0.006, **feature_row(0.0)},
                {"island": "alpha", "lat": 0.0, "lon": 0.009, **feature_row(5.0)},
                {"island": "alpha", "lat": 0.0, "lon": 0.012, **feature_row(0.2)},
                {"island": "alpha", "lat": 0.0, "lon": 0.015, **feature_row(4.0)},
                {"island": "alpha", "lat": 0.0, "lon": 0.018, **feature_row(0.1)},
            ]
        )
        clusters = pd.DataFrame(
            [
                {
                    "historical_cluster_id": 1,
                    "cluster_policy": "single_link",
                    "island": "alpha",
                    "latitude": 0.0,
                    "longitude": 0.0,
                    **feature_row(0.0),
                },
                {
                    "historical_cluster_id": 2,
                    "cluster_policy": "single_link",
                    "island": "alpha",
                    "latitude": 0.0,
                    "longitude": 0.012,
                    **feature_row(1.0),
                },
            ]
        )
        changed = clusters.copy()
        for name in NDVI_FEATURES:
            changed.loc[changed["historical_cluster_id"].eq(2), name] = 999.0

        result_a, _, summary_a = evaluate_anchor_coverage_habitat(
            universe,
            clusters,
            outer_radii_km=(2.0,),
            selection_fractions=(0.4,),
            recovery_radii_km=(0.25,),
        )
        result_b, _, summary_b = evaluate_anchor_coverage_habitat(
            universe,
            changed,
            outer_radii_km=(2.0,),
            selection_fractions=(0.4,),
            recovery_radii_km=(0.25,),
        )
        columns = [
            "selected_coverage_habitat_cells",
            "nearest_selected_cell_km",
            "recovered_0.25km",
        ]
        pd.testing.assert_frame_equal(
            result_a[columns].reset_index(drop=True),
            result_b[columns].reset_index(drop=True),
        )
        self.assertFalse(summary_a["hidden_cluster_features_used_for_candidate_scoring"])
        self.assertFalse(summary_b["hidden_cluster_features_used_for_candidate_scoring"])

    def test_invalid_environment_distance_fails_closed(self):
        frame = pd.DataFrame(
            [
                {"island": "alpha", "lat": 0.0, "lon": 0.001, "candidate_cell_id": 1, "environment_distance": float("nan")},
                {"island": "alpha", "lat": 0.0, "lon": 0.002, "candidate_cell_id": 2, "environment_distance": 1.0},
            ]
        )
        with self.assertRaises(ValueError):
            coverage_constrained_habitat_sample(frame, 1)


if __name__ == "__main__":
    unittest.main()
