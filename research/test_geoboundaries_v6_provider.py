import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from shapely import wkt

from geoboundaries_v6_provider import (
    GEOBOUNDARIES_LICENSE,
    GEOBOUNDARIES_LICENSE_BLOB_SHA,
    GEOBOUNDARIES_RELEASE_COMMIT,
    GEOBOUNDARIES_RELEASE_TAG,
    GEOBOUNDARIES_SOURCE_ID,
    ISO_MAPPING_PATH,
    alpha3_for_country,
    fetch_geoboundaries_country_geometry,
    geoboundaries_url,
    load_iso_alpha2_to_alpha3,
)

ROOT = Path(__file__).resolve().parents[1]
FREEZE_PATH = ROOT / "validation" / "acsp_country_geometry_geoboundaries_v6_freeze_v1.json"
EXPECTED_FREEZE_FINGERPRINT = "d0f9c9b2dfe939ffd91984b8a291442553f11b962ff64de4da2ed88d07f49589"
EXPECTED_MAPPING_SHA256 = "f77ba13da1e25967d759805f5eda8562f577bf4dc70f9fd3519f2edafdd0f26e"


class GeoBoundariesV6ProviderTests(unittest.TestCase):
    def test_provider_freeze_and_mapping_are_byte_pinned(self):
        freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
        stored = freeze.pop("provider_freeze_fingerprint")
        calculated = hashlib.sha256(
            json.dumps(
                freeze,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(stored, EXPECTED_FREEZE_FINGERPRINT)
        self.assertEqual(calculated, EXPECTED_FREEZE_FINGERPRINT)
        self.assertEqual(
            hashlib.sha256(ISO_MAPPING_PATH.read_bytes()).hexdigest(),
            EXPECTED_MAPPING_SHA256,
        )
        self.assertEqual(freeze["provider"]["release_tag"], GEOBOUNDARIES_RELEASE_TAG)
        self.assertEqual(freeze["provider"]["release_commit"], GEOBOUNDARIES_RELEASE_COMMIT)
        self.assertEqual(freeze["provider"]["license"], GEOBOUNDARIES_LICENSE)
        self.assertEqual(
            freeze["provider"]["license_blob_sha"],
            GEOBOUNDARIES_LICENSE_BLOB_SHA,
        )
        self.assertTrue(freeze["scientific_boundary"]["provider_frozen_before_integration_outcomes"])
        self.assertFalse(freeze["scientific_boundary"]["integrated_ecological_outcomes_opened"])
        self.assertFalse(freeze["geometry_contract"]["bbox_fallback"])
        self.assertFalse(freeze["geometry_contract"]["alternate_provider_fallback"])

    def test_static_country_mapping_is_complete_and_runtime_pycountry_free(self):
        mapping = load_iso_alpha2_to_alpha3()
        self.assertEqual(len(mapping), 249)
        self.assertEqual(mapping["JP"], "JPN")
        self.assertEqual(mapping["US"], "USA")
        self.assertEqual(mapping["KR"], "KOR")
        self.assertEqual(alpha3_for_country("jp"), "JPN")
        with self.assertRaisesRegex(ValueError, "absent from the frozen ISO mapping"):
            alpha3_for_country("XK")
        with self.assertRaisesRegex(ValueError, "invalid two-letter country code"):
            alpha3_for_country("JPN")

    def test_url_is_commit_pinned_not_live_tag_or_api(self):
        iso3, url = geoboundaries_url("JP")
        self.assertEqual(iso3, "JPN")
        self.assertIn(GEOBOUNDARIES_RELEASE_COMMIT, url)
        self.assertNotIn("/v6.0.0/", url)
        self.assertNotIn("api.geoboundaries", url)
        self.assertTrue(url.endswith("/JPN/ADM0/geoBoundaries-JPN-ADM0_simplified.geojson"))

    @patch("geoboundaries_v6_provider.get_json")
    def test_provider_unions_only_polygonal_features_and_records_payload_digest(self, mock_get_json):
        mock_get_json.return_value = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"shapeName": "A"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                    },
                },
                {
                    "type": "Feature",
                    "properties": {"shapeName": "B"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[2, 0], [3, 0], [3, 1], [2, 1], [2, 0]]],
                    },
                },
            ],
        }
        result = fetch_geoboundaries_country_geometry("JP")
        geometry = wkt.loads(result.land_geometry_wkt)
        self.assertEqual(result.country_code, "JP")
        self.assertEqual(result.source_id, GEOBOUNDARIES_SOURCE_ID)
        self.assertEqual(geometry.geom_type, "MultiPolygon")
        self.assertAlmostEqual(geometry.area, 2.0)
        self.assertIn("v6.0.0@1289e40e366c7b320550be1ee0614a9472d572d4", result.source_version)
        self.assertIn("iso3=JPN", result.source_version)
        self.assertIn("canonical_geojson_sha256=", result.source_version)
        self.assertIn("license=CC BY 4.0", result.source_version)
        called_url = mock_get_json.call_args.args[0]
        self.assertIn(GEOBOUNDARIES_RELEASE_COMMIT, called_url)
        self.assertEqual(mock_get_json.call_args.kwargs, {"timeout": 120, "attempts": 5})

    @patch("geoboundaries_v6_provider.get_json")
    def test_provider_rejects_non_polygon_payload_without_repair_or_fallback(self, mock_get_json):
        mock_get_json.return_value = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {"type": "Point", "coordinates": [139.0, 35.0]},
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "non-polygonal geometry"):
            fetch_geoboundaries_country_geometry("JP")
        self.assertEqual(mock_get_json.call_count, 1)

    @patch("geoboundaries_v6_provider.get_json")
    def test_provider_rejects_empty_feature_collection_without_second_provider(self, mock_get_json):
        mock_get_json.return_value = {"type": "FeatureCollection", "features": []}
        with self.assertRaisesRegex(ValueError, "contains no features"):
            fetch_geoboundaries_country_geometry("JP")
        self.assertEqual(mock_get_json.call_count, 1)


if __name__ == "__main__":
    unittest.main()
