from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acsp.discovery.recipes import get_structural_recipe, rank_structural_recipe
from acsp.discovery.structural import build_structural_support_order


class DiscoveryRecipeParityTests(unittest.TestCase):
    def raw_frame(self) -> pd.DataFrame:
        rows = []
        for r in range(4):
            for c in range(5):
                x = r * 5 + c
                rows.append(
                    {
                        "candidate_cell_id": f"cell-{r}-{c}",
                        "latitude": 35.0 + r * 0.001,
                        "longitude": 139.0 + c * 0.001,
                        "grid_row": r,
                        "grid_col": c,
                        "elev": 700.0 + 37.0 * r + 13.0 * c,
                        "slope100": 2.0 + 0.8 * r + 0.3 * c,
                        "tpi300": -4.0 + 1.7 * r - 0.6 * c,
                        "rough300": 3.0 + 0.5 * r + 0.9 * c,
                        "wc_tree_frac_250m": ((x * 7) % 19) / 18.0,
                        "wc_grass_frac_250m": ((x * 5 + 3) % 17) / 16.0,
                        "wc_bare_frac_250m": ((x * 3 + 1) % 13) / 12.0,
                        "wc_water_frac_250m": ((x * 2) % 11) / 20.0,
                        "wc_wetland_frac_250m": ((x * 4 + 1) % 9) / 20.0,
                        "wc_edge_mix_250m": ((x * 11 + 2) % 23) / 22.0,
                        "coast_distance_m": 50.0 + 120.0 * c + 40.0 * r,
                        "ecological_component_id": "target" if not (r == 3 and c == 4) else "other",
                    }
                )
        return pd.DataFrame(rows)

    def assert_family_parity(self, family: str, target_component_id: str | None = None) -> None:
        raw = self.raw_frame()
        old, old_audit = build_structural_support_order(
            raw,
            feature_family=family,
            source_provenance={"source": "synthetic-parity"},
            target_component_id=target_component_id,
            graph_radius_cells=1,
        )
        new, recipe_audit = rank_structural_recipe(
            raw,
            recipe_id=family,
            target_component_id=target_component_id,
            graph_radius_cells=1,
        )
        np.testing.assert_allclose(
            old["structural_support"].to_numpy(float),
            new["structural_support"].to_numpy(float),
            atol=1e-12,
            rtol=0.0,
        )
        self.assertEqual(old["candidate_cell_id"].tolist(), new["candidate_cell_id"].tolist())
        self.assertEqual(old["decision_rank"].tolist(), new["decision_rank"].tolist())
        self.assertEqual(tuple(old_audit.support_audit["component_columns"]), recipe_audit.support_components)
        self.assertEqual(recipe_audit.composition_rule, "ROW_MIN_CONJUNCTIVE_SUPPORT")
        self.assertFalse(recipe_audit.field_outcomes_used)
        self.assertFalse(recipe_audit.fitted_feature_weights)

    def test_all_existing_structural_families_have_declarative_recipe(self) -> None:
        expected = {
            "WETLAND_MOISTURE_STRUCTURE",
            "ALPINE_TOPOGRAPHIC_STRUCTURE",
            "OPEN_GRASSLAND_STRUCTURE",
            "COASTAL_ISLAND_STRUCTURE",
            "FOREST_EDGE_STRUCTURE",
        }
        for family in expected:
            self.assertEqual(get_structural_recipe(family).recipe_id, family)

    def test_wetland_recipe_parity(self) -> None:
        self.assert_family_parity("WETLAND_MOISTURE_STRUCTURE")

    def test_alpine_recipe_parity(self) -> None:
        self.assert_family_parity("ALPINE_TOPOGRAPHIC_STRUCTURE")

    def test_grassland_recipe_parity(self) -> None:
        self.assert_family_parity("OPEN_GRASSLAND_STRUCTURE")

    def test_coastal_recipe_parity(self) -> None:
        self.assert_family_parity("COASTAL_ISLAND_STRUCTURE", target_component_id="target")

    def test_forest_edge_recipe_parity(self) -> None:
        self.assert_family_parity("FOREST_EDGE_STRUCTURE")


if __name__ == "__main__":
    unittest.main()
