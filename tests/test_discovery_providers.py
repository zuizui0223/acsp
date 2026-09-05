from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acsp.discovery import rank_morton_dyadic_spatial_balance
from acsp.discovery.providers import (
    WORLD_COVER_2021_CLASS_NAMES,
    worldcover_2021_map_url,
    worldcover_tile_id,
    worldcover_tile_ids_for_bounds,
)


class DiscoveryProviderTests(unittest.TestCase):
    def test_worldcover_official_tile_grid_semantics(self) -> None:
        self.assertEqual(worldcover_tile_id(35.0, 139.0), "N33E138")
        self.assertEqual(worldcover_tile_id(-0.1, -0.1), "S03W003")
        self.assertEqual(
            worldcover_tile_ids_for_bounds((137.9, 34.9, 138.1, 35.1)),
            ("N33E135", "N33E138"),
        )
        self.assertTrue(
            worldcover_2021_map_url("N33E138").endswith(
                "/v200/2021/map/ESA_WorldCover_10m_2021_v200_N33E138_Map.tif"
            )
        )

    def test_worldcover_class_codes_match_frozen_structural_inputs(self) -> None:
        self.assertEqual(WORLD_COVER_2021_CLASS_NAMES[30], "grass")
        self.assertEqual(WORLD_COVER_2021_CLASS_NAMES[60], "bare")
        self.assertEqual(WORLD_COVER_2021_CLASS_NAMES[80], "water")
        self.assertEqual(WORLD_COVER_2021_CLASS_NAMES[90], "wetland")
        self.assertEqual(len(WORLD_COVER_2021_CLASS_NAMES), 11)

    def test_morton_dyadic_order_is_full_deterministic_permutation(self) -> None:
        rows = []
        for r in range(6):
            for c in range(7):
                rows.append(
                    {
                        "candidate_cell_id": f"r{r}c{c}",
                        "latitude": 35 + r * 0.001,
                        "longitude": 139 + c * 0.001,
                        "grid_row": r,
                        "grid_col": c,
                    }
                )
        frame = pd.DataFrame(rows)
        first, audit1 = rank_morton_dyadic_spatial_balance(frame)
        second, audit2 = rank_morton_dyadic_spatial_balance(frame.sample(frac=1.0, random_state=4))
        self.assertEqual(first["candidate_cell_id"].tolist(), second["candidate_cell_id"].tolist())
        self.assertEqual(set(first["candidate_cell_id"]), set(frame["candidate_cell_id"]))
        self.assertEqual(first["decision_rank"].tolist(), list(range(1, len(frame) + 1)))
        self.assertEqual(audit1.method, "MORTON_DYADIC_COVERAGE_ORDER_V1")
        self.assertEqual(audit1, audit2)
        self.assertEqual(audit1.memory_complexity, "O(n)")


if __name__ == "__main__":
    unittest.main()
