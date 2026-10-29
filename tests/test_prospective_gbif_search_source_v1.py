"""Synthetic-only tests for future GBIF source bytes and private/public separation."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from research import freeze_prospective_gbif_search_source_v1 as capture

KEY_A = "11111111-1111-1111-1111-111111111111"
KEY_B = "22222222-2222-2222-2222-222222222222"


class ProspectiveGbifSearchSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.dir = Path(self.temporary.name)
        self.raw_dir = self.dir / "raw"
        self.raw_dir.mkdir()
        self.private = self.dir / "private.zip"
        self.public = self.dir / "receipt.json"
        self.used = self.dir / "used_ids.txt"
        self.query = {
            "taxonKey": 12345,
            "country": "JP",
            "limit": 2,
            "offset": 0,
            "hasCoordinate": "true",
            "hasGeospatialIssue": "false",
            "occurrenceStatus": "PRESENT",
        }
        self.records = [
            {"gbifID": 101, "datasetKey": KEY_A, "license": "CC0_1_0",
             "decimalLatitude": 35.123, "decimalLongitude": 139.456,
             "scientificName": "FAKE_A"},
            {"gbifID": 102, "datasetKey": KEY_B, "license": "CC_BY_4_0",
             "decimalLatitude": 34.5, "decimalLongitude": 135.4,
             "scientificName": "FAKE_B"},
        ]
        self.payload = {"offset": 0, "limit": 2, "count": 22,
                        "endOfRecords": False, "results": self.records}
        self.manifest = {
            "schema_version": capture.SCHEMA,
            "purpose": capture.PURPOSE,
            "frozen_protocol_sha256": "a" * 64,
            "capture_time_declared_utc": "2026-10-29T01:00:00Z",
            "pages": [{"path": "page_001.json", "query": self.query}],
        }
        self._write()

    def _write(self) -> None:
        (self.raw_dir / "capture_manifest.json").write_text(
            json.dumps(self.manifest), encoding="utf-8")
        (self.raw_dir / "page_001.json").write_text(
            json.dumps(self.payload), encoding="utf-8")

    def _freeze(self, *, used: bool = False):
        return capture.freeze(
            self.raw_dir / "capture_manifest.json",
            self.private,
            self.public,
            self.used if used else None,
        )

    def test_private_original_bytes_and_public_coordinate_free_receipt(self):
        original = (self.raw_dir / "page_001.json").read_bytes()
        result = self._freeze()
        self.assertEqual(result["status"],
                         "NEW_COHORT_RAW_SOURCE_SNAPSHOTTED_NOT_ORIGIN_ATTESTED")
        self.assertEqual(result["source_records_fetched"], 2)
        self.assertEqual(result["source_dataset_keys_count"], 2)
        self.assertEqual(result["pages_captured"], 1)
        self.assertFalse(result["explicit_analysis_used_id_set_archived_privately"])
        self.assertTrue(result["exact_analysis_used_record_set_not_confirmed_without_ids"])
        self.assertFalse(result["original_2026_august_96pair_source_recovered"])
        self.assertFalse(result["gbif_derived_dataset_doi_issued"])
        self.assertEqual(capture.verify_archive(self.private, self.public), result)
        exposed = self.public.read_text(encoding="utf-8")
        for secret in ("FAKE_A", "FAKE_B", KEY_A, KEY_B, "35.123",
                       "139.456", "101", "102", "12345", "JP"):
            self.assertNotIn('"' + secret + '"', exposed)
        with zipfile.ZipFile(self.private) as z:
            self.assertEqual(z.read("raw_pages/page_001.json"), original)
            self.assertIn(KEY_A.encode(), z.read("private_attribution.json"))
            self.assertNotIn("analysis_used_gbif_ids.txt", z.namelist())

    def test_explicit_used_record_ids_are_checked_and_counted_privately(self):
        self.used.write_text("101\n", encoding="utf-8")
        result = self._freeze(used=True)
        self.assertTrue(result["explicit_analysis_used_id_set_archived_privately"])
        self.assertEqual(result["analysis_used_id_count_if_supplied"], 1)
        self.assertEqual(result["source_dataset_keys_for_used_ids_count_if_supplied"], 1)
        with zipfile.ZipFile(self.private) as z:
            private = json.loads(z.read("private_attribution.json"))
            self.assertEqual(private["dataset_key_counts_analysis_used_if_supplied"],
                             {KEY_A: 1})
            self.assertEqual(z.read("analysis_used_gbif_ids.txt"), b"101\n")
        self.assertNotIn(KEY_A, self.public.read_text())

    def test_refuse_used_ids_not_present_in_raw_source(self):
        self.used.write_text("999\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not in frozen raw source"):
            self._freeze(used=True)
        self.assertFalse(self.private.exists())

    def test_refuse_duplicate_used_ids(self):
        self.used.write_text("101\n101\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicates"):
            self._freeze(used=True)

    def test_refuse_missing_dataset_key_and_no_partial_snapshot(self):
        del self.records[0]["datasetKey"]
        self._write()
        with self.assertRaisesRegex(ValueError, "datasetKey UUID missing"):
            self._freeze()
        self.assertFalse(self.private.exists())
        self.assertFalse(self.public.exists())

    def test_refuse_duplicate_gbif_id_across_search_pages(self):
        second_query = dict(self.query)
        second_query["country"] = "KR"
        second_record = dict(self.records[0], decimalLatitude=37.2,
                             decimalLongitude=127.1)
        second_page = {"offset": 0, "limit": 2, "count": 1,
                       "endOfRecords": True, "results": [second_record]}
        self.manifest["pages"].append(
            {"path": "page_002.json", "query": second_query})
        (self.raw_dir / "page_002.json").write_text(json.dumps(second_page))
        self._write()
        with self.assertRaisesRegex(ValueError, "repeated GBIF ID"):
            self._freeze()

    def test_refuse_response_offset_mismatch(self):
        self.payload["offset"] = 7
        self._write()
        with self.assertRaisesRegex(ValueError, "offset or limit"):
            self._freeze()

    def test_refuse_historical_2026_relabel(self):
        self.manifest["purpose"] = "historical-acsp-2026-08-20"
        self._write()
        with self.assertRaisesRegex(ValueError, "must never be relabeled"):
            self._freeze()

    def test_refuse_old_date_as_a_new_source(self):
        self.manifest["capture_time_declared_utc"] = "2026-08-20T06:00:00Z"
        self._write()
        with self.assertRaisesRegex(ValueError, "cannot represent historical August"):
            self._freeze()

    def test_refuse_incomplete_request_filter(self):
        del self.query["hasGeospatialIssue"]
        self._write()
        with self.assertRaisesRegex(ValueError, "mandatory original GBIF"):
            self._freeze()

    def test_refuse_duplicate_first_page_request(self):
        self.manifest["pages"].append(
            {"path": "page_002.json", "query": dict(self.query)})
        (self.raw_dir / "page_002.json").write_text(json.dumps(self.payload))
        self._write()
        with self.assertRaisesRegex(ValueError, "duplicate GBIF search request"):
            self._freeze()

    def test_refuse_private_archive_inside_public_repo(self):
        candidate = capture.ROOT / "never_create_private_snapshot.zip"
        self.assertFalse(candidate.exists())
        with self.assertRaisesRegex(ValueError, "OUTSIDE the public Git checkout"):
            capture.freeze(self.raw_dir / "capture_manifest.json", candidate, self.public)
        self.assertFalse(candidate.exists())

    def test_nonoverwrite_and_snapshot_zip_integrity(self):
        self._freeze()
        with self.assertRaisesRegex(ValueError, "never overwrite"):
            self._freeze()
        with self.private.open("ab") as f:
            f.write(b"tamper")
        with self.assertRaisesRegex(ValueError, "ZIP hash mismatch"):
            capture.verify_archive(self.private, self.public)

    def test_reject_floating_point_identifier_to_preserve_exact_gbif_id(self):
        self.records[0]["gbifID"] = 101.0
        self._write()
        with self.assertRaisesRegex(ValueError, "exact integer"):
            self._freeze()

    def test_empty_response_is_allowed_but_not_citable_as_used_data(self):
        self.payload = {"offset": 0, "limit": 2, "count": 0,
                        "endOfRecords": True, "results": []}
        self._write()
        result = self._freeze()
        self.assertEqual(result["source_records_fetched"], 0)
        self.assertFalse(result["explicit_analysis_used_id_set_archived_privately"])

    def test_raw_source_bytes_are_held_verbatim_not_normalized(self):
        self._freeze()
        with zipfile.ZipFile(self.private) as z:
            exact = z.read("raw_pages/page_001.json")
            self.assertEqual(exact, (self.raw_dir / "page_001.json").read_bytes())
            self.assertEqual(json.loads(exact)["results"][0]["gbifID"], 101)


if __name__ == "__main__":
    unittest.main()
