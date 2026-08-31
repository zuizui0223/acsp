from __future__ import annotations

import unittest

import pandas as pd

from evaluate_campanula_anchor_selector_comparison import compare_selector_aggregates


class SelectorComparisonTests(unittest.TestCase):
    def _spatial(self):
        return pd.DataFrame(
            [
                {
                    "cluster_policy": "single_link",
                    "outer_radius_km": 2.0,
                    "selection_fraction_of_annulus": 0.1,
                    "recovery_radius_km": 0.5,
                    "anchor_conditioned_recall": 0.5,
                    "median_selected_spatially_balanced_cells": 10.0,
                },
                {
                    "cluster_policy": "complete_link",
                    "outer_radius_km": 2.0,
                    "selection_fraction_of_annulus": 0.1,
                    "recovery_radius_km": 0.5,
                    "anchor_conditioned_recall": 0.6,
                    "median_selected_spatially_balanced_cells": 10.0,
                },
            ]
        )

    def _ndvi(self):
        return pd.DataFrame(
            [
                {
                    "cluster_policy": "single_link",
                    "outer_radius_km": 2.0,
                    "selection_fraction_of_complete_annulus": 0.1,
                    "recovery_radius_km": 0.5,
                    "anchor_conditioned_recall": 0.4,
                    "median_selected_ndvi_cells": 10.0,
                },
                {
                    "cluster_policy": "complete_link",
                    "outer_radius_km": 2.0,
                    "selection_fraction_of_complete_annulus": 0.1,
                    "recovery_radius_km": 0.5,
                    "anchor_conditioned_recall": 0.7,
                    "median_selected_ndvi_cells": 10.0,
                },
            ]
        )

    def _coverage(self):
        return pd.DataFrame(
            [
                {
                    "cluster_policy": "single_link",
                    "outer_radius_km": 2.0,
                    "selection_fraction_of_complete_annulus": 0.1,
                    "recovery_radius_km": 0.5,
                    "anchor_conditioned_recall": 0.7,
                    "median_selected_coverage_habitat_cells": 10.0,
                },
                {
                    "cluster_policy": "complete_link",
                    "outer_radius_km": 2.0,
                    "selection_fraction_of_complete_annulus": 0.1,
                    "recovery_radius_km": 0.5,
                    "anchor_conditioned_recall": 0.6,
                    "median_selected_coverage_habitat_cells": 10.0,
                },
            ]
        )

    def test_tallies_exact_matched_wins_ties_losses(self):
        merged, summary = compare_selector_aggregates(
            self._spatial(), self._ndvi(), self._coverage()
        )
        self.assertTrue(merged["exact_median_cell_count_match"].all())
        self.assertEqual(
            summary["coverage_habitat_vs_spatial_all"],
            {"win": 1, "tie": 1, "loss": 0},
        )
        self.assertEqual(
            summary["coverage_habitat_vs_ndvi_all"],
            {"win": 1, "tie": 0, "loss": 1},
        )
        self.assertEqual(
            summary["coverage_habitat_vs_spatial_primary_policy"],
            {"win": 1, "tie": 0, "loss": 0},
        )

    def test_mismatched_cell_counts_are_not_comparable(self):
        coverage = self._coverage()
        coverage.loc[0, "median_selected_coverage_habitat_cells"] = 9.0
        merged, summary = compare_selector_aggregates(
            self._spatial(), self._ndvi(), coverage
        )
        self.assertFalse(bool(merged.iloc[0]["exact_median_cell_count_match"]))
        self.assertEqual(summary["comparable_rows"], 1)

    def test_missing_configuration_fails_closed(self):
        with self.assertRaises(ValueError):
            compare_selector_aggregates(
                self._spatial().iloc[:1].copy(), self._ndvi(), self._coverage()
            )


if __name__ == "__main__":
    unittest.main()
