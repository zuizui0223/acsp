from __future__ import annotations

import unittest
from unittest.mock import patch

from shapely import wkt

import geoboundaries_v6_hk_technical_recovery as mod


def feature(name: str, *, group: str = "CHN", shape_type: str = "ADM1", x: float = 0.0):
    return {
        "type": "Feature",
        "properties": {
            "shapeName": name,
            "shapeGroup": group,
            "shapeType": shape_type,
            "shapeID": f"{group}-{name}",
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[x, 0], [x + 1, 0], [x + 1, 1], [x, 1], [x, 0]]],
        },
    }


class GeoBoundariesV6HKTechnicalRecoveryTests(unittest.TestCase):
    @patch("geoboundaries_v6_hk_technical_recovery.get_json")
    def test_hk_uses_exact_hong_kong_feature_from_same_pinned_release(self, get_json):
        get_json.return_value = {
            "type": "FeatureCollection",
            "features": [feature("Guangdong", x=0), feature("Hong Kong", x=2)],
        }
        result = mod.fetch_country_geometry_with_hk_recovery("hk")
        geometry = wkt.loads(result.land_geometry_wkt)
        self.assertEqual(result.country_code, "HK")
        self.assertEqual(result.source_id, mod.HK_RECOVERY_SOURCE_ID)
        self.assertAlmostEqual(geometry.area, 1.0)
        self.assertIn(mod.base.GEOBOUNDARIES_RELEASE_COMMIT, result.source_version)
        self.assertIn("iso3=HKG", result.source_version)
        self.assertIn("container_iso3=CHN", result.source_version)
        self.assertIn("container_adm=ADM1", result.source_version)
        self.assertIn("shapeName=Hong Kong", result.source_version)
        self.assertIn("canonical_geojson_sha256=", result.source_version)
        self.assertIn("license=CC BY 4.0", result.source_version)
        self.assertEqual(get_json.call_args.args[0], mod.HK_CHN_ADM1_URL)
        self.assertEqual(get_json.call_args.kwargs, {"timeout": 120, "attempts": 5})

    @patch("geoboundaries_v6_hk_technical_recovery.base.fetch_geoboundaries_country_geometry")
    def test_non_hk_delegates_without_changing_existing_provider(self, base_fetch):
        sentinel = object()
        base_fetch.return_value = sentinel
        self.assertIs(mod.fetch_country_geometry_with_hk_recovery("jp"), sentinel)
        base_fetch.assert_called_once_with("JP")

    @patch("geoboundaries_v6_hk_technical_recovery.get_json")
    def test_hk_requires_exactly_one_feature(self, get_json):
        get_json.return_value = {"type": "FeatureCollection", "features": [feature("Guangdong")]}
        with self.assertRaisesRegex(ValueError, "exactly one 'Hong Kong' feature"):
            mod.fetch_hk_geometry_from_pinned_china_adm1()

        get_json.return_value = {
            "type": "FeatureCollection",
            "features": [feature("Hong Kong"), feature("Hong Kong", x=2)],
        }
        with self.assertRaisesRegex(ValueError, "got 2"):
            mod.fetch_hk_geometry_from_pinned_china_adm1()

    @patch("geoboundaries_v6_hk_technical_recovery.get_json")
    def test_hk_rejects_container_identity_drift(self, get_json):
        get_json.return_value = {
            "type": "FeatureCollection",
            "features": [feature("Hong Kong", group="HKG")],
        }
        with self.assertRaisesRegex(ValueError, "shapeGroup drift"):
            mod.fetch_hk_geometry_from_pinned_china_adm1()

        get_json.return_value = {
            "type": "FeatureCollection",
            "features": [feature("Hong Kong", shape_type="ADM0")],
        }
        with self.assertRaisesRegex(ValueError, "shapeType drift"):
            mod.fetch_hk_geometry_from_pinned_china_adm1()

    @patch("geoboundaries_v6_hk_technical_recovery.get_json")
    def test_hk_rejects_non_polygon_geometry_without_repair(self, get_json):
        bad = feature("Hong Kong")
        bad["geometry"] = {"type": "Point", "coordinates": [114.1, 22.3]}
        get_json.return_value = {"type": "FeatureCollection", "features": [bad]}
        with self.assertRaisesRegex(ValueError, "non-polygonal geometry"):
            mod.fetch_hk_geometry_from_pinned_china_adm1()


if __name__ == "__main__":
    unittest.main()
