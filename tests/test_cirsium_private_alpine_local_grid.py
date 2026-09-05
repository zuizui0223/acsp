import json
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

from research.build_cirsium_private_alpine_local_grid_v1 import build_alpine_local_raw_grid


class PrivateAlpineLocalGridTests(unittest.TestCase):
    def test_builds_frozen_100m_annulus_with_required_terrain(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metric_crs = "EPSG:32654"
            to_metric = Transformer.from_crs("EPSG:4326", metric_crs, always_xy=True)
            to_wgs = Transformer.from_crs(metric_crs, "EPSG:4326", always_xy=True)
            cx, cy = to_metric.transform(141.0, 40.0)

            sector_m = Polygon([
                (cx - 2500, cy - 2500),
                (cx + 2500, cy - 2500),
                (cx + 2500, cy + 2500),
                (cx - 2500, cy + 2500),
            ])
            sector_wgs = shapely_transform(to_wgs.transform, sector_m)
            sector_path = root / "sector.geojson"
            sector_path.write_text(
                json.dumps({"type": "Feature", "properties": {}, "geometry": mapping(sector_wgs)}),
                encoding="utf-8",
            )

            anchor_lon, anchor_lat = to_wgs.transform(cx, cy)
            anchor_path = root / "anchors.csv"
            pd.DataFrame({"latitude": [anchor_lat], "longitude": [anchor_lon]}).to_csv(anchor_path, index=False)

            dem_path = root / "dem.tif"
            width = height = 400
            resolution = 25.0
            transform = from_origin(cx - 5000, cy + 5000, resolution, resolution)
            rr, cc = np.meshgrid(np.arange(height), np.arange(width), indexing="ij")
            elevation = (1000.0 + 0.5 * rr + 0.2 * cc).astype("float32")
            with rasterio.open(
                dem_path,
                "w",
                driver="GTiff",
                height=height,
                width=width,
                count=1,
                dtype="float32",
                crs=metric_crs,
                transform=transform,
                nodata=-9999.0,
            ) as dst:
                dst.write(elevation, 1)

            frame, summary = build_alpine_local_raw_grid(
                sector_path,
                anchor_path,
                dem_path,
                unit_id="CIR03",
            )

            self.assertGreater(len(frame), 0)
            self.assertTrue(frame["candidate_cell_id"].is_unique)
            self.assertGreaterEqual(float(frame["nearest_anchor_km"].min()), 0.5 - 1e-6)
            self.assertLessEqual(float(frame["nearest_anchor_km"].max()), 2.0 + 1e-6)
            for column in ("elev", "slope100", "tpi300", "rough300"):
                self.assertIn(column, frame.columns)
                self.assertTrue(np.isfinite(frame[column].to_numpy(float)).all())
            self.assertEqual(summary["grid_spacing_m"], 100.0)
            self.assertEqual(summary["known_point_exclusion_km"], 0.5)
            self.assertEqual(summary["outer_radius_km"], 2.0)
            self.assertIs(summary["field_outcomes_used"], False)
            self.assertIs(summary["human_access_used"], False)

    def test_requires_latitude_longitude_anchor_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sector_path = root / "sector.geojson"
            sector_path.write_text(
                json.dumps({
                    "type": "Polygon",
                    "coordinates": [[[140.9, 39.9], [141.1, 39.9], [141.1, 40.1], [140.9, 40.1], [140.9, 39.9]]],
                }),
                encoding="utf-8",
            )
            anchor_path = root / "anchors.csv"
            pd.DataFrame({"lat": [40.0], "lon": [141.0]}).to_csv(anchor_path, index=False)
            dem_path = root / "unused.tif"
            dem_path.write_bytes(b"not-read-before-anchor-validation")
            with self.assertRaisesRegex(ValueError, "primary-anchor table missing columns"):
                build_alpine_local_raw_grid(sector_path, anchor_path, dem_path, unit_id="CIR03")


if __name__ == "__main__":
    unittest.main()
