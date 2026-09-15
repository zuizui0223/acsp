from __future__ import annotations

import unittest

import pandas as pd

from acsp.structural_graph import build_structural_graph_primitives, grid_local_mean, grid_local_similarity


class StructuralGraphTests(unittest.TestCase):
    def grid(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "grid_row": [0, 0, 1, 1],
                "grid_col": [0, 1, 0, 1],
                "elev": [100.0, 110.0, 400.0, 420.0],
                "slope100": [2.0, 3.0, 15.0, 16.0],
                "tpi300": [-10.0, -8.0, 20.0, 22.0],
                "rough300": [1.0, 1.2, 4.0, 4.2],
                "wc_grass_frac_250m": [0.8, 0.7, 0.2, 0.1],
                "wc_bare_frac_250m": [0.1, 0.2, 0.7, 0.8],
                "coast_distance_m": [50.0, 100.0, 500.0, 1000.0],
                "ecological_component_id": ["island-a", "island-a", "island-b", "island-b"],
            }
        )

    def test_grid_local_mean_uses_self_and_existing_neighbours(self) -> None:
        frame = self.grid()
        value = pd.Series([1.0, 1.0, 0.0, 0.0])
        result = grid_local_mean(frame, value, radius=1)
        self.assertEqual(len(result), 4)
        self.assertTrue(result.between(0, 1).all())
        # On a 2x2 Moore grid every cell sees all four cells including self.
        self.assertTrue(all(abs(float(v) - 0.5) < 1e-12 for v in result))

    def test_local_similarity_is_bounded_and_outcome_blind(self) -> None:
        frame = self.grid()
        similarity = grid_local_similarity(frame, ("elev", "slope100", "tpi300", "rough300"))
        self.assertTrue(similarity.between(0, 1).all())
        contaminated = frame.assign(field_outcome_state="SEARCH_COMPLETED_DETECTED_VERIFIED")
        with self.assertRaises(ValueError):
            grid_local_similarity(contaminated, ("elev", "slope100"))

    def test_wetland_graph_builds_only_continuity_raw(self) -> None:
        frame = self.grid()
        out, audit = build_structural_graph_primitives(frame, feature_family="WETLAND_MOISTURE_STRUCTURE")
        self.assertIn("terrain_continuity_score_raw", out)
        self.assertFalse(audit.human_access_used)
        self.assertFalse(audit.fitted_thresholds)

    def test_alpine_graph_requires_declared_terrain_features(self) -> None:
        frame = self.grid()
        out, _ = build_structural_graph_primitives(frame, feature_family="ALPINE_TOPOGRAPHIC_STRUCTURE")
        self.assertTrue(out["landform_continuity_score_raw"].between(0, 1).all())
        self.assertTrue(out["ridge_valley_continuity_score_raw"].between(0, 1).all())

    def test_grassland_fragment_continuity_follows_local_grass_support(self) -> None:
        frame = self.grid()
        out, _ = build_structural_graph_primitives(frame, feature_family="OPEN_GRASSLAND_STRUCTURE")
        self.assertTrue(out["fragment_continuity_score_raw"].between(0, 1).all())
        self.assertTrue(out["terrain_context_score_raw"].between(0, 1).all())

    def test_coastal_component_is_fail_closed_and_target_specific(self) -> None:
        frame = self.grid()
        with self.assertRaises(ValueError):
            build_structural_graph_primitives(frame, feature_family="COASTAL_ISLAND_STRUCTURE")
        out, _ = build_structural_graph_primitives(
            frame,
            feature_family="COASTAL_ISLAND_STRUCTURE",
            target_component_id="island-a",
        )
        self.assertEqual(out["island_component_score_raw"].tolist(), [1.0, 1.0, 0.0, 0.0])
        self.assertTrue(out["shore_landform_continuity_score_raw"].between(0, 1).all())

    def test_duplicate_grid_cells_fail_closed(self) -> None:
        frame = self.grid()
        frame.loc[3, ["grid_row", "grid_col"]] = [1, 0]
        with self.assertRaises(ValueError):
            build_structural_graph_primitives(frame, feature_family="OPEN_GRASSLAND_STRUCTURE")


if __name__ == "__main__":
    unittest.main()
