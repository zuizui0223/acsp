from __future__ import annotations

import tempfile
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin, xy

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acsp.discovery import rank_morton_dyadic_spatial_balance
from acsp.discovery.providers import (
    WORLD_COVER_2021_CLASS_NAMES,
    attach_worldcover_coastal_features,
    worldcover_2021_map_url,
    worldcover_tile_id,
    worldcover_tile_ids_for_bounds,
)


class DiscoveryProviderTests(unittest.TestCase):
    def test_worldcover_official_tile_grid_semantics(self) -> None:
        self.assertEqual(worldcover_tile_id(35.0, 139.0), "N33E138")
        self.assertEqual(worldcover_tile_id(-0.1, -0.1), "S03W003")
        self.assertEqual(worldcover_tile_ids_for_bounds((137.9, 34.9, 138.1, 35.1)), ("N33E135", "N33E138"))
        self.assertTrue(worldcover_2021_map_url("N33E138").endswith("/v200/2021/map/ESA_WorldCover_10m_2021_v200_N33E138_Map.tif"))

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
                rows.append({"candidate_cell_id": f"r{r}c{c}", "latitude": 35 + r * 0.001, "longitude": 139 + c * 0.001, "grid_row": r, "grid_col": c})
        frame = pd.DataFrame(rows)
        first, audit1 = rank_morton_dyadic_spatial_balance(frame)
        second, audit2 = rank_morton_dyadic_spatial_balance(frame.sample(frac=1.0, random_state=4))
        self.assertEqual(first["candidate_cell_id"].tolist(), second["candidate_cell_id"].tolist())
        self.assertEqual(set(first["candidate_cell_id"]), set(frame["candidate_cell_id"]))
        self.assertEqual(first["decision_rank"].tolist(), list(range(1, len(frame) + 1)))
        self.assertEqual(audit1.method, "MORTON_DYADIC_COVERAGE_ORDER_V1")
        self.assertEqual(audit1, audit2)
        self.assertEqual(audit1.memory_complexity, "O(n)")

    def _write_worldcover(self, path: Path, array: np.ndarray):
        transform = from_origin(139.0, 35.1, 0.001, 0.001)
        with rasterio.open(path, "w", driver="GTiff", height=array.shape[0], width=array.shape[1], count=1, dtype=array.dtype, crs="EPSG:4326", transform=transform) as dst:
            dst.write(array, 1)
        return transform

    def _point(self, transform, row: int, col: int) -> tuple[float, float]:
        lon, lat = xy(transform, row, col, offset="center")
        return float(lat), float(lon)

    def test_portable_coastal_features_remove_water_and_pin_one_component(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wc.tif"
            array = np.full((80, 100), 30, dtype=np.uint8)
            array[:, :20] = 80
            array[30:50, 40:55] = 60
            transform = self._write_worldcover(path, array)
            a1 = self._point(transform, 20, 40)
            a2 = self._point(transform, 50, 70)
            water = self._point(transform, 20, 10)
            land = self._point(transform, 25, 30)
            anchors = pd.DataFrame({"latitude": [a1[0], a2[0]], "longitude": [a1[1], a2[1]]})
            candidates = pd.DataFrame(
                [
                    {"candidate_cell_id": "land", "latitude": land[0], "longitude": land[1], "grid_row": 0, "grid_col": 0},
                    {"candidate_cell_id": "water", "latitude": water[0], "longitude": water[1], "grid_row": 0, "grid_col": 1},
                ]
            )
            enriched, audit = attach_worldcover_coastal_features(candidates, anchors, path)
            self.assertEqual(enriched["candidate_cell_id"].tolist(), ["land"])
            self.assertGreater(float(enriched.iloc[0]["coast_distance_m"]), 0.0)
            self.assertTrue(0.0 <= float(enriched.iloc[0]["wc_grass_frac_250m"]) <= 1.0)
            self.assertTrue(0.0 <= float(enriched.iloc[0]["wc_bare_frac_250m"]) <= 1.0)
            self.assertEqual(enriched.iloc[0]["ecological_component_id"], audit.target_component_id)
            self.assertEqual(audit.historical_anchor_component_count, 1)
            self.assertFalse(audit.field_outcomes_used)

    def test_portable_coastal_features_abstain_on_multiple_anchor_components(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wc.tif"
            array = np.full((60, 100), 30, dtype=np.uint8)
            array[:, 45:55] = 80
            transform = self._write_worldcover(path, array)
            left = self._point(transform, 20, 20)
            right = self._point(transform, 20, 80)
            anchors = pd.DataFrame({"latitude": [left[0], right[0]], "longitude": [left[1], right[1]]})
            candidates = pd.DataFrame([{"candidate_cell_id": "x", "latitude": left[0], "longitude": left[1], "grid_row": 0, "grid_col": 0}])
            with self.assertRaisesRegex(ValueError, "MULTIPLE_HISTORICAL_LAND_COMPONENTS"):
                attach_worldcover_coastal_features(candidates, anchors, path)


if __name__ == "__main__":
    unittest.main()
