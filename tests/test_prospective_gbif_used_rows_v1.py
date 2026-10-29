"""Synthetic-only end-to-end new-cohort GBIF raw-to-cleaned used-row bridge tests."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

from research import freeze_prospective_gbif_search_source_v1 as snapshot
from research import verify_prospective_gbif_used_rows_v1 as bridge

KEY_A = "11111111-1111-1111-1111-111111111111"
KEY_B = "22222222-2222-2222-2222-222222222222"


class ProspectiveGbifUsedRecordBridgeTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        self.source = self.root / "raw"
        self.source.mkdir()
        self.private = self.root / "source.zip"
        self.source_receipt = self.root / "source_receipt.json"
        self.used = self.root / "used.txt"
        self.cleaned = self.root / "used_cleaned.csv"
        self.public = self.root / "used_receipt.json"
        self.query = {
            "taxonKey": 112233,
            "country": "JP",
            "limit": 3,
            "offset": 0,
            "hasCoordinate": "true",
            "hasGeospatialIssue": "false",
            "occurrenceStatus": "PRESENT",
        }
        self.records = [
            {"gbifID": 101, "datasetKey": KEY_A, "license": "CC0",
             "decimalLatitude": 35.122, "decimalLongitude": 139.345,
             "scientificName": "Invented species A", "eventDate": "2026-10-01",
             "basisOfRecord": "HUMAN_OBSERVATION", "countryCode": "JP"},
            {"gbifID": 102, "datasetKey": KEY_B, "license": "CC-BY",
             "decimalLatitude": 34.999, "decimalLongitude": 135.111,
             "scientificName": "Invented species A", "eventDate": "2026-10-02",
             "basisOfRecord": "HUMAN_OBSERVATION", "countryCode": "JP"},
            {"gbifID": 103, "datasetKey": KEY_A, "license": "CC0",
             "decimalLatitude": 36.000, "decimalLongitude": 140.222,
             "scientificName": "Invented species A", "eventDate": "2026-10-03",
             "basisOfRecord": "HUMAN_OBSERVATION", "countryCode": "JP"},
        ]
        self.manifest = {
            "schema_version": snapshot.SCHEMA,
            "purpose": snapshot.PURPOSE,
            "frozen_protocol_sha256": "c" * 64,
            "capture_time_declared_utc": "2026-10-29T08:00:00Z",
            "pages": [{"path": "raw1.json", "query": self.query}],
        }
        self.source_manifest = self.source / "capture_manifest.json"
        self.source_manifest.write_text(json.dumps(self.manifest), encoding="utf-8")
        (self.source / "raw1.json").write_text(json.dumps({
            "offset": 0, "limit": 3, "count": 3,
            "endOfRecords": True, "results": self.records
        }), encoding="utf-8")
        self.used.write_text("101\n103\n", encoding="utf-8")
        self.fields = [
            "_row_id", "_gbif_id", "_latitude", "_longitude",
            "datasetKey", "license", "scientificName", "eventDate",
            "basisOfRecord", "countryCode",
        ]
        self.rows = [
            {"_row_id": "0", "_gbif_id": "101", "_latitude": "35.122",
             "_longitude": "139.345", "datasetKey": KEY_A, "license": "CC0",
             "scientificName": "Invented species A", "eventDate": "2026-10-01",
             "basisOfRecord": "HUMAN_OBSERVATION", "countryCode": "JP"},
            {"_row_id": "2", "_gbif_id": "103", "_latitude": "36",
             "_longitude": "140.222", "datasetKey": KEY_A, "license": "CC0",
             "scientificName": "Invented species A", "eventDate": "2026-10-03",
             "basisOfRecord": "HUMAN_OBSERVATION", "countryCode": "JP"},
        ]
        self.write_rows()
        self.freeze_source()

    def write_rows(self):
        with self.cleaned.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.fields)
            writer.writeheader()
            writer.writerows(self.rows)

    def freeze_source(self, with_used=True):
        return snapshot.freeze(self.source_manifest, self.private,
                               self.source_receipt, self.used if with_used else None)

    def verify(self):
        return bridge.bridge(self.private, self.source_receipt,
                             self.cleaned, self.public)

    def test_exact_private_ids_coordinates_and_attribution(self):
        out = self.verify()
        self.assertEqual(out["status"], bridge.STATUS)
        self.assertEqual(out["cleaned_and_frozen_used_record_count"], 2)
        self.assertEqual(out["source_records_fetched"], 3)
        self.assertEqual(out["unique_source_datasets_for_used_records"], 1)
        self.assertTrue(out["all_cleaned_gbif_ids_match_frozen_used_id_set"])
        self.assertTrue(out["all_cleaned_coordinates_match_frozen_raw_records"])
        self.assertTrue(out["cleaned_dataset_keys_checked_if_present"])
        self.assertFalse(out["historical_2026_august_original_gbif_input_recovered"])
        self.assertFalse(out["provider_response_origin_independently_authenticated"])
        self.assertFalse(out["frozen_used_ids_independently_attested_pre_outcome"])
        serialized = self.public.read_text(encoding="utf-8")
        for forbidden in (KEY_A, KEY_B, "Invented species A", "139.345",
                          "140.222", '"_gbif_id"', "decimalLatitude", "countryCode"):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(json.loads(serialized), out)

    def test_matching_subset_but_unfrozen_used_inventory_is_rejected(self):
        self.private.unlink()
        self.source_receipt.unlink()
        self.freeze_source(with_used=False)
        with self.assertRaisesRegex(ValueError, "was not frozen"):
            self.verify()
        self.assertFalse(self.public.exists())

    def test_no_implicit_all_fetched_equals_all_used(self):
        self.rows[1]["_gbif_id"] = "102"
        self.rows[1]["_latitude"] = "34.999"
        self.rows[1]["_longitude"] = "135.111"
        self.rows[1]["datasetKey"] = KEY_B
        self.rows[1]["license"] = "CC-BY"
        self.rows[1]["eventDate"] = "2026-10-02"
        self.write_rows()
        with self.assertRaisesRegex(ValueError, "do not exactly match"):
            self.verify()
        self.assertFalse(self.public.exists())

    def test_moved_coordinate_is_detected(self):
        self.rows[1]["_latitude"] = "36.001"
        self.write_rows()
        with self.assertRaisesRegex(ValueError, "coordinate does not match"):
            self.verify()

    def test_wrong_dataset_key_is_detected(self):
        self.rows[0]["datasetKey"] = KEY_B
        self.write_rows()
        with self.assertRaisesRegex(ValueError, "datasetKey differs"):
            self.verify()

    def test_wrong_license_is_detected(self):
        self.rows[0]["license"] = "CC-BY"
        self.write_rows()
        with self.assertRaisesRegex(ValueError, "source license differs"):
            self.verify()

    def test_wrong_scientific_name_is_detected_when_present(self):
        self.rows[0]["scientificName"] = "Invented species B"
        self.write_rows()
        with self.assertRaisesRegex(ValueError, "source identity metadata differs"):
            self.verify()

    def test_same_record_twice_fails(self):
        self.rows[1]["_gbif_id"] = "101"
        self.rows[1]["_latitude"] = "35.122"
        self.rows[1]["_longitude"] = "139.345"
        self.rows[1]["eventDate"] = "2026-10-01"
        self.write_rows()
        with self.assertRaisesRegex(ValueError, "duplicate GBIF record"):
            self.verify()

    def test_duplicate_cleaned_row_ordinal_fails(self):
        self.rows[1]["_row_id"] = "0"
        self.write_rows()
        with self.assertRaisesRegex(ValueError, "duplicate cleaned source row ordinal"):
            self.verify()

    def test_two_conflicting_coordinate_aliases_fail(self):
        self.fields.extend(("latitude", "longitude"))
        for row in self.rows:
            row["latitude"] = row["_latitude"]
            row["longitude"] = row["_longitude"]
        self.rows[0]["latitude"] = "35.22"
        self.write_rows()
        with self.assertRaisesRegex(ValueError, "coordinate does not match"):
            self.verify()

    def test_partial_latitude_alias_pair_fails(self):
        self.fields.append("latitude")
        for row in self.rows:
            row["latitude"] = row["_latitude"]
        self.write_rows()
        with self.assertRaisesRegex(ValueError, "partial cleaned coordinate column pair"):
            self.verify()

    def test_raw_source_private_zip_tamper_is_detected(self):
        with self.private.open("ab") as handle:
            handle.write(b"spoof")
        with self.assertRaisesRegex(ValueError, "ZIP hash mismatch"):
            self.verify()

    def test_refuse_overwrite_of_result_receipt(self):
        self.verify()
        with self.assertRaisesRegex(ValueError, "must use a new JSON path"):
            self.verify()

    def test_invalid_source_gbif_decimal_float_id_is_detected(self):
        self.rows[0]["_gbif_id"] = "101.0"
        self.write_rows()
        with self.assertRaisesRegex(ValueError, "positive integer"):
            self.verify()

    def test_legacy_two_alias_id_fields_must_agree(self):
        self.fields.append("gbifID")
        for row in self.rows:
            row["gbifID"] = row["_gbif_id"]
        self.rows[0]["gbifID"] = "103"
        self.write_rows()
        with self.assertRaisesRegex(ValueError, "identifier aliases disagree"):
            self.verify()

    def test_exact_source_bytes_and_cleaned_csv_hashes_in_receipt(self):
        out = self.verify()
        self.assertEqual(
            out["cleaned_used_row_csv_sha256"],
            bridge.hashlib.sha256(self.cleaned.read_bytes()).hexdigest()
        )
        self.assertEqual(out["source_private_zip_sha256"],
                         snapshot.verify_archive(self.private, self.source_receipt)
                         ["private_archive_sha256"])


if __name__ == "__main__":
    unittest.main()
