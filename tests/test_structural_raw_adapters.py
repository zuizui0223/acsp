from __future__ import annotations

import math
import unittest

import pandas as pd

from acsp.structural_raw_adapters import adapt_structural_components
from acsp.structural_support import compose_structural_support


class StructuralRawAdapterTests(unittest.TestCase):
    def test_wetland_adapter_is_outcome_blind_and_bounded(self) -> None:
        frame = pd.DataFrame(
            {
                "candidate_cell_id": ["a", "b", "c", "d"],
                "wc_water_frac_250m": [0.0, 0.2, 0.4, 0.8],
                "wc_wetland_frac_250m": [0.1, 0.2, 0.4, 0.4],
                "slope100": [20.0, 10.0, 5.0, 1.0],
                "tpi300": [30.0, 10.0, -10.0, -30.0],
                "terrain_continuity_score_raw": [0.2, 0.4, 0.8, 1.0],
            }
        )
        adapted, audit = adapt_structural_components(frame, feature_family="WETLAND_MOISTURE_STRUCTURE")
        self.assertEqual(audit.frame_relative_ranks_used, ("tpi300:low", "slope100:low"))
        self.assertEqual(audit.pass_through_graph_components, ("terrain_continuity_score_raw",))
        self.assertTrue(adapted["wetland_water_adjacent_score"].between(0, 1).all())
        self.assertTrue(adapted["topographic_moisture_score"].between(0, 1).all())
        support, _ = compose_structural_support(adapted, feature_family="WETLAND_MOISTURE_STRUCTURE")
        self.assertTrue(support.between(0, 1).all())
        self.assertGreater(float(support.iloc[-1]), float(support.iloc[0]))

    def test_alpine_uses_relative_elevation_but_requires_graph_continuity(self) -> None:
        frame = pd.DataFrame(
            {
                "elev": [100.0, 500.0, 1000.0],
                "landform_continuity_score_raw": [0.6, 0.7, 0.8],
                "ridge_valley_continuity_score_raw": [0.9, 0.7, 0.5],
            }
        )
        adapted, audit = adapt_structural_components(frame, feature_family="ALPINE_TOPOGRAPHIC_STRUCTURE")
        self.assertEqual(audit.frame_relative_ranks_used, ("elev:high",))
        self.assertLess(float(adapted.loc[0, "relative_relief_score"]), float(adapted.loc[2, "relative_relief_score"]))
        with self.assertRaises(ValueError):
            adapt_structural_components(frame.drop(columns=["landform_continuity_score_raw"]), feature_family="ALPINE_TOPOGRAPHIC_STRUCTURE")

    def test_grassland_does_not_invent_fragment_connectivity(self) -> None:
        frame = pd.DataFrame(
            {
                "wc_grass_frac_250m": [0.1, 0.8],
                "fragment_continuity_score_raw": [0.9, 0.3],
                "terrain_context_score_raw": [0.5, 0.6],
            }
        )
        adapted, audit = adapt_structural_components(frame, feature_family="OPEN_GRASSLAND_STRUCTURE")
        self.assertEqual(adapted["open_land_score"].tolist(), [0.1, 0.8])
        self.assertIn("fragment_continuity_score_raw", audit.pass_through_graph_components)

    def test_coastal_transform_is_fixed_monotone(self) -> None:
        frame = pd.DataFrame(
            {
                "coast_distance_m": [0.0, 1000.0, 2000.0],
                "shore_landform_continuity_score_raw": [1.0, 1.0, 1.0],
                "island_component_score_raw": [1.0, 1.0, 1.0],
            }
        )
        adapted, _ = adapt_structural_components(frame, feature_family="COASTAL_ISLAND_STRUCTURE")
        expected = [1.0, math.exp(-1.0), math.exp(-2.0)]
        for observed, exp in zip(adapted["shore_position_score"], expected):
            self.assertAlmostEqual(float(observed), exp, places=12)

    def test_forest_edge_is_maximal_near_half_tree_fraction(self) -> None:
        frame = pd.DataFrame(
            {
                "wc_tree_frac_250m": [0.0, 0.5, 1.0],
                "wc_edge_mix_250m": [0.2, 0.9, 0.2],
                "terrain_component_score_raw": [1.0, 1.0, 1.0],
            }
        )
        adapted, _ = adapt_structural_components(frame, feature_family="FOREST_EDGE_STRUCTURE")
        self.assertEqual(adapted["forest_edge_score"].tolist(), [0.0, 1.0, 0.0])

    def test_field_outcome_columns_fail_closed(self) -> None:
        frame = pd.DataFrame(
            {
                "wc_grass_frac_250m": [0.8],
                "fragment_continuity_score_raw": [0.9],
                "terrain_context_score_raw": [0.5],
                "field_outcome_state": ["SEARCH_COMPLETED_DETECTED_VERIFIED"],
            }
        )
        with self.assertRaises(ValueError):
            adapt_structural_components(frame, feature_family="OPEN_GRASSLAND_STRUCTURE")

    def test_baseline_family_has_no_adapter(self) -> None:
        with self.assertRaises(ValueError):
            adapt_structural_components(pd.DataFrame({"x": [1]}), feature_family="GENERAL_SPATIAL_BASELINE_ONLY")


if __name__ == "__main__":
    unittest.main()
