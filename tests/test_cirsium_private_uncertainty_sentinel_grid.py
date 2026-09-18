import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin
from shapely.geometry import Polygon, mapping
from shapely.ops import transform as shapely_transform

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.build_cirsium_private_uncertainty_sentinel_grid_v1 import build_uncertainty_sentinel_raw_grid  # noqa: E402


class PrivateUncertaintySentinelGridTests(unittest.TestCase):
    def test_builds_clipped_uncertainty_footprint_grid_with_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metric = "EPSG:32654"
            to_metric = Transformer.from_crs("EPSG:4326", metric, always_xy=True)
            to_wgs = Transformer.from_crs(metric, "EPSG:4326", always_xy=True)
            cx, cy = to_metric.transform(140.5, 40.7)

            sector_m = Polygon([
                (cx - 3000, cy - 3000), (cx + 3000, cy - 3000),
                (cx + 3000, cy + 3000), (cx - 3000, cy + 3000),
            ])
            sector_wgs = shapely_transform(to_wgs.transform, sector_m)
            sector_path = root / "sector.geojson"
            sector_path.write_text(
                json.dumps({"type": "Feature", "properties": {}, "geometry": mapping(sector_wgs)}),
                encoding="utf-8",
            )

            lon, lat = to_wgs.transform(cx, cy)
            evidence_path = root / "sentinel.csv"
            pd.DataFrame({
                "latitude": [lat, lat],
                "longitude": [lon, lon],
                "coordinate_uncertainty_m": [1500.0, 1500.0],
            }).to_csv(evidence_path, index=False)

            dem_path = root / "dem.tif"
            width = height = 480
            resolution = 25.0
            dem_transform = from_origin(cx - 6000, cy + 6000, resolution, resolution)
            rr, cc = np.meshgrid(np.arange(height), np.arange(width), indexing="ij")
            elevation = (250.0 + 0.1 * rr + 0.05 * cc).astype("float32")
            with rasterio.open(
                dem_path, "w", driver="GTiff", height=height, width=width,
                count=1, dtype="float32", crs=metric, transform=dem_transform, nodata=-9999.0,
            ) as dst:
                dst.write(elevation, 1)

            wc_path = root / "worldcover.tif"
            west, south, east, north = sector_wgs.bounds
            margin = 0.04
            pixel = 0.0001
            wc_width = int(np.ceil((east - west + 2 * margin) / pixel))
            wc_height = int(np.ceil((north - south + 2 * margin) / pixel))
            wc_transform = from_origin(west - margin, north + margin, pixel, pixel)
            wc = np.full((wc_height, wc_width), 90, dtype="uint8")
            wc[:, wc_width // 2 :] = 80
            with rasterio.open(
                wc_path, "w", driver="GTiff", height=wc_height, width=wc_width,
                count=1, dtype="uint8", crs="EPSG:4326", transform=wc_transform, nodata=0,
            ) as dst:
                dst.write(wc, 1)

            frame, summary = build_uncertainty_sentinel_raw_grid(
                sector_path, evidence_path, dem_path, wc_path, unit_id="CIR02"
            )
            self.assertGreater(len(frame), 0)
            self.assertLess(len(frame), summary["range_sector_grid_rows_before_footprint_clip"])
            self.assertTrue(frame["candidate_cell_id"].is_unique)
            self.assertTrue(frame["broad_sentinel_support"].between(0.0, 1.0).all())
            self.assertTrue(np.isfinite(frame["elev"].to_numpy(float)).all())
            self.assertTrue(np.isfinite(frame["slope100"].to_numpy(float)).all())
            self.assertIn("wc_water_frac_250m", frame.columns)
            self.assertIn("wc_wetland_frac_250m", frame.columns)
            self.assertEqual(summary["unique_uncertainty_footprints"], 1)
            self.assertEqual(summary["sentinel_subregime"], "UNCERTAINTY_FOOTPRINT")
            self.assertIs(summary["distance_preference_inside_uncertainty_footprint"], False)
            self.assertIs(summary["field_outcomes_used"], False)

    def test_rejects_pseudo_exact_uncertainty(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence_path = root / "sentinel.csv"
            pd.DataFrame({
                "latitude": [40.0], "longitude": [140.0], "coordinate_uncertainty_m": [500.0]
            }).to_csv(evidence_path, index=False)
            from research.build_cirsium_private_uncertainty_sentinel_grid_v1 import _validate_uncertainty_evidence
            with self.assertRaisesRegex(ValueError, "strictly above"):
                _validate_uncertainty_evidence(pd.read_csv(evidence_path))


if __name__ == "__main__":
    unittest.main()
