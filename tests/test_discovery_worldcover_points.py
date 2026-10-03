from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acsp.discovery.providers.worldcover_points import retain_worldcover_land_points


class WorldCoverPointSamplingTests(unittest.TestCase):
    def _write_raster(self, path: Path) -> None:
        data = np.full((6, 6), 30, dtype=np.uint8)
        data[0, 1] = 80
        data[0, 2] = 0
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=6,
            width=6,
            count=1,
            dtype="uint8",
            crs="EPSG:4326",
            transform=from_origin(132.0, 36.0, 0.5, 0.5),
            nodata=0,
        ) as dst:
            dst.write(data, 1)

    def _frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"candidate_cell_id": "land", "latitude": 35.75, "longitude": 132.25, "grid_row": 0, "grid_col": 0},
                {"candidate_cell_id": "water", "latitude": 35.75, "longitude": 132.75, "grid_row": 0, "grid_col": 1},
                {"candidate_cell_id": "nodata", "latitude": 35.75, "longitude": 133.25, "grid_row": 0, "grid_col": 2},
            ]
        )

    def test_land_water_and_nodata_are_separated_without_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raster = Path(tmp) / "worldcover.tif"
            self._write_raster(raster)
            opener = lambda _url: rasterio.open(raster)
            retained, audit = retain_worldcover_land_points(self._frame(), dataset_opener=opener)
            self.assertEqual(retained["candidate_cell_id"].tolist(), ["land"])
            self.assertEqual(retained["worldcover_class"].tolist(), [30])
            self.assertEqual(audit.candidate_rows_input, 3)
            self.assertEqual(audit.sampled_rows, 2)
            self.assertEqual(audit.land_rows_retained, 1)
            self.assertEqual(audit.water_rows_removed, 1)
            self.assertEqual(audit.invalid_or_nodata_rows_removed, 1)
            self.assertFalse(audit.field_outcomes_used)
            self.assertFalse(audit.human_access_used)
            self.assertFalse(audit.component_segmentation_used)

    def test_sample_digest_is_stable_to_candidate_row_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raster = Path(tmp) / "worldcover.tif"
            self._write_raster(raster)
            opener = lambda _url: rasterio.open(raster)
            _, audit_a = retain_worldcover_land_points(self._frame(), dataset_opener=opener)
            _, audit_b = retain_worldcover_land_points(
                self._frame().iloc[::-1].reset_index(drop=True),
                dataset_opener=opener,
            )
            self.assertEqual(audit_a.sample_classification_sha256, audit_b.sample_classification_sha256)
            self.assertEqual(audit_a.source_tile_ids, ("N33E132",))

    def test_duplicate_candidate_ids_fail_closed(self) -> None:
        frame = self._frame()
        frame.loc[1, "candidate_cell_id"] = "land"
        with self.assertRaisesRegex(ValueError, "candidate_cell_id must be unique"):
            retain_worldcover_land_points(frame, dataset_opener=lambda _url: None)


if __name__ == "__main__":
    unittest.main()
