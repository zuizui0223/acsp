import unittest
from unittest.mock import patch

import pandas as pd

from gbif_fieldmap_builder_app import build_automatic_discover_bundle, build_default_short_trip_plans


class AutomaticHierarchyTests(unittest.TestCase):
    def test_short_trip_builder_reduces_unrealistic_eight_cell_plan(self):
        candidate_types = (
            ["Occurrence-supported survey range"] * 3
            + ["Habitat-match"] * 3
            + ["Environmental-test"] * 2
        )
        candidates = pd.DataFrame({
            "site_id": range(1, 9),
            "candidate_type": candidate_types,
            "latitude": [35.00, 35.25, 35.50, 35.05, 35.30, 35.55, 35.15, 35.45],
            "longitude": [139.00, 139.35, 139.00, 139.40, 139.05, 139.40, 139.20, 139.20],
            "analogue_score": [0.7] * 8,
            "access_score": [0.8] * 8,
            "environmental_novelty": [0.2] * 6 + [0.9] * 2,
            "survey_gap_score": [0.2] * 3 + [0.8] * 3 + [0.4] * 2,
        })
        plans, estimate, requested = build_default_short_trip_plans(
            candidates, 35.275, 139.20, target_days=2, max_cells=8
        )
        self.assertEqual(requested, 8)
        self.assertLess(len(plans["Balanced"]), requested)
        self.assertLessEqual(estimate["estimated_days"], 2)
        self.assertGreater(estimate["estimated_road_km"], 0)

    def test_automatic_bundle_uses_region_hierarchy_without_network(self):
        points = []
        for cluster in range(8):
            base_lon = 139.0 + cluster * 0.045
            points.extend([(35.0, base_lon), (35.0005, base_lon + 0.0005)])
        occurrences = pd.DataFrame({
            "_row_id": range(len(points)),
            "_latitude": [point[0] for point in points],
            "_longitude": [point[1] for point in points],
            "_event_date": ["2024-05-01"] * len(points),
            "_year": [2024] * len(points),
            "_species": ["Example species"] * len(points),
            "_media_url": [""] * len(points),
            "_gbif_id": [str(i) for i in range(len(points))],
            "_locality": ["Example area"] * len(points),
            "_coordinate_uncertainty_m": [30.0] * len(points),
        })
        with (
            patch("gbif_fieldmap_builder_app.app_provided_habitat_layers", return_value={}),
            patch("gbif_fieldmap_builder_app.make_potential_survey_site_candidates", return_value=pd.DataFrame()),
            patch("gbif_fieldmap_builder_app.filter_to_land", side_effect=lambda frame, *args, **kwargs: frame),
        ):
            bundle = build_automatic_discover_bundle(
                "Example species", occurrences, "synthetic records", "Test"
            )
        self.assertEqual(bundle["distribution_summary"]["distribution_regime"], "narrow/local")
        self.assertEqual(len(bundle["region_cards"]), 1)
        self.assertLessEqual(bundle["trip_estimate"]["estimated_days"], 2)
        self.assertTrue(bundle["warnings"])


if __name__ == "__main__":
    unittest.main()
