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
from shapely.geometry import LineString, Polygon, mapping
from shapely.ops import transform as shapely_transform

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.build_cirsium_private_coastal_local_grid_v1 import build_coastal_local_raw_grid  # noqa: E402


class PrivateCoastalLocalGridTests(unittest.TestCase):
    def test_builds_worldcover_coast_and_component_raw_grid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metric = "EPSG:32652"
            to_metric = Transformer.from_crs("EPSG:4326", metric, always_xy=True)
            to_wgs = Transformer.from_crs(metric, "EPSG:4326", always_xy=True)
            cx, cy = to_metric.transform(127.8, 26.3)

            sector_m = Polygon([
                (cx - 2500, cy - 2500), (cx + 2500, cy - 2500),
                (cx + 2500, cy + 2500), (cx - 2500, cy + 2500),
            ])
            sector_wgs = shapely_transform(to_wgs.transform, sector_m)
            sector_path = root / "sector.geojson"
            sector_path.write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": mapping(sector_wgs)}), encoding="utf-8")

            anchor_lon, anchor_lat = to_wgs.transform(cx, cy)
            anchor_path = root / "anchors.csv"
            pd.DataFrame({"latitude": [anchor_lat], "longitude": [anchor_lon]}).to_csv(anchor_path, index=False)

            component_path = root / "components.geojson"
            component_path.write_text(
                json.dumps({
                    "type": "FeatureCollection",
                    "features": [{
                        "type": "Feature",
                        "properties": {"ecological_component_id": "OKINAWA_TARGET"},
                        "geometry": mapping(sector_wgs),
                    }],
                }),
                encoding="utf-8",
            )

            coast_m = LineString([(cx - 1000, cy - 3000), (cx - 1000, cy + 3000)])
            coast_wgs = shapely_transform(to_wgs.transform, coast_m)
            coast_path = root / "coast.geojson"
            coast_path.write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": mapping(coast_wgs)}), encoding="utf-8")

            worldcover_path = root / "worldcover.tif"
            west, south, east, north = sector_wgs.bounds
            margin = 0.03
            pixel = 0.0001
            width = int(np.ceil((east - west + 2 * margin) / pixel))
            height = int(np.ceil((north - south + 2 * margin) / pixel))
            transform = from_origin(west - margin, north + margin, pixel, pixel)
            values = np.full((height, width), 30, dtype="uint8")
            values[:, : width // 3] = 60
            with rasterio.open(
                worldcover_path, "w", driver="GTiff", height=height, width=width,
                count=1, dtype="uint8", crs="EPSG:4326", transform=transform, nodata=0,
            ) as dst:
                dst.write(values, 1)

            frame, summary = build_coastal_local_raw_grid(
                sector_path,
                anchor_path,
                worldcover_path,
                coast_path,
                component_path,
                target_component_id="OKINAWA_TARGET",
                unit_id="CIR08",
            )
            self.assertGreater(len(frame), 0)
            self.assertTrue(frame["candidate_cell_id"].is_unique)
            self.assertTrue(np.isfinite(frame["coast_distance_m"].to_numpy(float)).all())
            self.assertEqual(set(frame["ecological_component_id"]), {"OKINAWA_TARGET"})
            for column in ("wc_grass_frac_250m", "wc_bare_frac_250m", "wc_edge_mix_250m"):
                self.assertIn(column, frame.columns)
                self.assertTrue(np.isfinite(frame[column].to_numpy(float)).all())
            self.assertEqual(summary["target_component_id"], "OKINAWA_TARGET")
            self.assertIs(summary["field_outcomes_used"], False)
            self.assertIs(summary["human_access_used"], False)

    def test_target_component_must_intersect_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # Input validation reaches target-component requirement before any output is written.
            component_path = root / "empty_components.geojson"
            component_path.write_text(json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "contains no usable features"):
                from research.build_cirsium_private_coastal_local_grid_v1 import _load_components
                _load_components(component_path, "ecological_component_id")


if __name__ == "__main__":
    unittest.main()
