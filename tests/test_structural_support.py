from __future__ import annotations

import unittest

import pandas as pd

from acsp.structural_support import compose_structural_support


class StructuralSupportTests(unittest.TestCase):
    def test_uses_conjunctive_minimum_without_fitted_weights(self) -> None:
        frame = pd.DataFrame(
            {
                "wetland_water_adjacent_score": [0.9, 0.7],
                "topographic_moisture_score": [0.8, 0.6],
                "terrain_continuity_score": [0.2, 0.9],
            }
        )
        support, audit = compose_structural_support(
            frame, feature_family="WETLAND_MOISTURE_STRUCTURE"
        )
        self.assertEqual(support.tolist(), [0.2, 0.6])
        self.assertEqual(audit.composition_rule, "ROW_MIN_CONJUNCTIVE_SUPPORT")
        self.assertFalse(audit.fitted_feature_weights)
        self.assertFalse(audit.field_outcomes_used)
        self.assertFalse(audit.post_outcome_component_switch_allowed)

    def test_family_components_are_not_user_swappable(self) -> None:
        frame = pd.DataFrame(
            {
                "open_land_score": [0.8],
                "fragment_continuity_score": [0.7],
                "terrain_context_score": [0.6],
                "relative_relief_score": [1.0],
            }
        )
        support, audit = compose_structural_support(
            frame, feature_family="OPEN_GRASSLAND_STRUCTURE"
        )
        self.assertEqual(support.tolist(), [0.6])
        self.assertEqual(
            audit.component_columns,
            ("open_land_score", "fragment_continuity_score", "terrain_context_score"),
        )

    def test_missing_component_fails_closed(self) -> None:
        frame = pd.DataFrame(
            {
                "forest_edge_score": [0.8],
                "canopy_opening_transition_score": [0.7],
            }
        )
        with self.assertRaises(ValueError):
            compose_structural_support(frame, feature_family="FOREST_EDGE_STRUCTURE")

    def test_field_outcome_columns_fail_closed(self) -> None:
        frame = pd.DataFrame(
            {
                "shore_position_score": [0.8],
                "shore_landform_continuity_score": [0.7],
                "island_component_score": [0.9],
                "field_success": [True],
            }
        )
        with self.assertRaises(ValueError):
            compose_structural_support(frame, feature_family="COASTAL_ISLAND_STRUCTURE")

    def test_spatial_baseline_has_no_structural_composition(self) -> None:
        with self.assertRaises(ValueError):
            compose_structural_support(
                pd.DataFrame({"x": [1]}),
                feature_family="GENERAL_SPATIAL_BASELINE_ONLY",
            )


if __name__ == "__main__":
    unittest.main()
