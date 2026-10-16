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

from acsp.discovery import partition_candidate_components
from acsp.discovery.providers import attach_worldcover_component_ids


class WorldCoverComponentProviderTests(unittest.TestCase):
    def _write_worldcover(self, path: Path, array: np.ndarray):
        transform = from_origin(139.0, 35.1, 0.001, 0.001)
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=array.shape[0],
            width=array.shape[1],
            count=1,
            dtype=array.dtype,
            crs="EPSG:4326",
            transform=transform,
        ) as dst:
            dst.write(array, 1)
        return transform

    def _point(self, transform, row: int, col: int) -> tuple[float, float]:
        lon, lat = xy(transform, row, col, offset="center")
        return float(lat), float(lon)

    def test_component_adapter_keeps_multiple_historical_components_without_rescue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wc.tif"
            array = np.full((60, 100), 30, dtype=np.uint8)
            array[:, 45:55] = 80
            transform = self._write_worldcover(path, array)
            left = self._point(transform, 20, 20)
            right = self._point(transform, 20, 80)
            water = self._point(transform, 20, 50)
            anchors = pd.DataFrame(
                {"latitude": [left[0], right[0]], "longitude": [left[1], right[1]]}
            )
            candidates = pd.DataFrame(
                [
                    {"candidate_cell_id": "left", "latitude": left[0], "longitude": left[1], "grid_row": 0, "grid_col": 0},
                    {"candidate_cell_id": "right", "latitude": right[0], "longitude": right[1], "grid_row": 0, "grid_col": 1},
                    {"candidate_cell_id": "water", "latitude": water[0], "longitude": water[1], "grid_row": 0, "grid_col": 2},
                ]
            )
            retained, audit = attach_worldcover_component_ids(candidates, anchors, path)
            self.assertEqual(set(retained["candidate_cell_id"]), {"left", "right"})
            self.assertEqual(audit.anchored_component_count, 2)
            self.assertEqual(len(audit.anchored_component_ids), 2)
            self.assertFalse(audit.distance_threshold_used)
            local, detached, partition = partition_candidate_components(
                retained,
                anchored_component_ids=[audit.anchored_component_ids[0]],
            )
            self.assertEqual(len(local), 1)
            self.assertEqual(len(detached), 1)
            self.assertEqual(partition.detached_component_count, 1)
            self.assertFalse(partition.distance_threshold_used)


if __name__ == "__main__":
    unittest.main()
