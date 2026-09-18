from __future__ import annotations

import unittest

import pandas as pd

from evaluate_campanula_anchor_ndvi_filter import (
    NDVI_FEATURES,
    evaluate_anchor_ndvi_filter,
)


def feature_row(value: float) -> dict[str, float]:
    return {name: float(value) for name in NDVI_FEATURES}


class AnchorNdviFilterTests(unittest.TestCase):
    def test_retained_ndvi_support_can_select_hidden_neighbour(self):
        universe_rows = []
        # Retained anchor at longitude 0; hidden cluster at about 1.33 km.
        # The candidate near the hidden location shares the retained NDVI state,
        # whereas spatially competing cells do not.
        for lon, value in [
            (0.006, 10.0),
            (0.009, 8.0),
            (0.0118, 0.1),
            (0.014, 9.0),
            (0.018, 7.0),
        ]:
            universe_rows.append(
                {"island": "alpha", "lat": 0.0, "lon": lon, **feature_row(value)}
            )
        universe_rows.append(
            {"island": "beta", "lat": 0.0, "lon": 2.5, **feature_row(0.0)}
        )
        universe = pd.DataFrame(universe_rows)
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
                    **feature_row(999.0),
                },
                {
                    "historical_cluster_id": 3,
                    "cluster_policy": "single_link",
                    "island": "beta",
                    "latitude": 0.0,
                    "longitude": 2.5,
                    **feature_row(0.0),
                },
            ]
        )
        folds, aggregate, summary = evaluate_anchor_ndvi_filter(
            universe,
            clusters,
            exclusion_radius_km=0.5,
            outer_radii_km=(2.0,),
            selection_fractions=(0.2, 1.0),
            recovery_radii_km=(0.1, 0.25),
        )
        row = folds.loc[
            folds["hidden_cluster_id"].eq(2)
            & folds["selection_fraction_of_complete_annulus"].eq(0.2)
        ].iloc[0]
        self.assertTrue(bool(row["recovered_0.1km"]))
        self.assertGreater(
            float(row["lift_over_matched_annulus_random_0.1km"]), 0.0
        )
        beta = folds.loc[folds["island"].eq("beta")]
        self.assertTrue(beta["anchor_absent"].astype(bool).all())
        self.assertFalse(summary["hidden_cluster_features_used_for_candidate_scoring"])
        full = aggregate.loc[
            aggregate["selection_fraction_of_complete_annulus"].eq(1.0)
            & aggregate["recovery_radius_km"].eq(0.25)
        ].iloc[0]
        self.assertAlmostEqual(
            float(full["mean_lift_over_matched_annulus_random"]), 0.0
        )

    def test_hidden_feature_value_does_not_change_selection(self):
        universe = pd.DataFrame(
            [
                {
                    "island": "alpha",
                    "lat": 0.0,
                    "lon": 0.006,
                    **feature_row(0.0),
                },
                {
                    "island": "alpha",
                    "lat": 0.0,
                    "lon": 0.012,
                    **feature_row(1.0),
                },
            ]
        )
        base = [
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
        first = pd.DataFrame(base)
        second = pd.DataFrame(base)
        for name in NDVI_FEATURES:
            second.loc[second["historical_cluster_id"].eq(2), name] = 999.0
        result_a, _, _ = evaluate_anchor_ndvi_filter(
            universe,
            first,
            outer_radii_km=(2.0,),
            selection_fractions=(0.5,),
            recovery_radii_km=(0.25,),
        )
        result_b, _, _ = evaluate_anchor_ndvi_filter(
            universe,
            second,
            outer_radii_km=(2.0,),
            selection_fractions=(0.5,),
            recovery_radii_km=(0.25,),
        )
        columns = [
            "selected_ndvi_cells",
            "nearest_selected_cell_km",
            "recovered_0.25km",
        ]
        pd.testing.assert_frame_equal(
            result_a[columns].reset_index(drop=True),
            result_b[columns].reset_index(drop=True),
        )

    def test_selection_fraction_validation(self):
        universe = pd.DataFrame(
            [
                {
                    "island": "alpha",
                    "lat": 0.0,
                    "lon": 0.01,
                    **feature_row(0.0),
                }
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
                }
            ]
        )
        with self.assertRaises(ValueError):
            evaluate_anchor_ndvi_filter(
                universe,
                clusters,
                selection_fractions=(0.0,),
            )


if __name__ == "__main__":
    unittest.main()
