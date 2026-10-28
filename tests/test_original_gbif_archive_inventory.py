"""Regression checks for the six-source 2026 historical GBIF input archive audit."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from research import audit_original_gbif_archive_inventory as audit

RECEIPT = (Path(__file__).resolve().parents[1] /
           "validation/acsp_original_gbif_archive_inventory_20261028.json")


class OriginalInputArchiveInventoryTests(unittest.TestCase):
    def test_six_exact_github_artifacts_have_explicit_closed_scope(self):
        source = json.loads(RECEIPT.read_text(encoding="utf-8"))
        self.assertEqual(source["schema_version"], audit.SCHEMA)
        self.assertEqual(source["checked_artifact_count"], 6)
        self.assertEqual(set(source["checked_artifacts"]), set(audit.ARTIFACTS))
        for name, (run, artifact, digest, members) in audit.ARTIFACTS.items():
            entry = source["checked_artifacts"][name]
            self.assertEqual(
                (entry["run_id"], entry["artifact_id"], entry["zip_sha256"],
                 entry["member_count"]),
                (run, artifact, digest, members),
            )
            self.assertIs(entry["actual_original_training_or_heldout_csv_present"], False)
        self.assertEqual(source["status"],
                         "EXACT_ORIGINAL_GBIF_INPUT_RECORDS_NOT_IN_SIX_CHECKED_ARCHIVES")

    def test_identical_status_is_not_misrepresented_as_identical_record_ids(self):
        source = json.loads(RECEIPT.read_text(encoding="utf-8"))
        self.assertTrue(source["four_execution_status_files_byte_identical"])
        self.assertTrue(source["four_execution_fold_manifests_byte_identical"])
        self.assertEqual(source["pair_status_summary"],
                         {"complete": 94, "failed_retained_as_zero": 2})
        self.assertEqual(source["original_confirmatory_pair_rows"], 96)
        self.assertEqual(source["original_confirmatory_fold_by_radius_rows"], 1920)
        self.assertFalse(source["scientific_boundaries"][
            "byte_identical_pair_status_proves_byte_identical_GBIF_inputs"])
        self.assertFalse(source["scientific_boundaries"][
            "all_other_backup_locations_exhaustively_searched"])

    def test_7895_coordinate_rows_are_not_focal_input_or_publicly_embedded(self):
        source = json.loads(RECEIPT.read_text(encoding="utf-8"))
        self.assertEqual(source["geographic_v2_nonfocal_reference_point_rows"], 7895)
        self.assertTrue(source["geographic_v2_prior_excludes_focal_coordinates"])
        for name in ("original_GBIF_input_rows_recovered", "original_GBIF_ID_inventory_recovered",
                     "original_datasetKey_mapping_recovered",
                     "original_GBIF_citation_DOI_verified",
                     "new_GBIF_queries_executed", "protected_coordinates_in_output"):
            self.assertIs(source["scientific_boundaries"][name], False)
        raw = RECEIPT.read_text(encoding="utf-8")
        self.assertNotIn("decimalLatitude", raw)
        self.assertNotIn("decimalLongitude", raw)
        self.assertNotIn("1039026628", raw)

    def test_wrong_original_zip_cannot_be_labeled_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            name = Path(tmp) / "fake.zip"
            with zipfile.ZipFile(name, "w") as z:
                z.writestr("pair_001/fold_001/training_occurrences.csv",
                           "gbifID,latitude,longitude\n123,35.0,139.0\n")
            with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                audit._read_original_archive(name, audit.ARTIFACTS[
                    "official_confirmation"][2], 6)

    def test_incomplete_archive_scope_fails_before_reading_content(self):
        with self.assertRaisesRegex(ValueError, "six original archives required"):
            audit.audit({})

    def test_exact_original_status_hash_locked(self):
        source = json.loads(RECEIPT.read_text(encoding="utf-8"))
        self.assertEqual(
            source["cross_execution_pair_export_status_sha256"],
            "55f66ba821cba0eafdcc149f04e082e0c66ecf4a51d9456c94319e158a81b7bf")
        self.assertEqual(
            source["cross_execution_fold_manifest_sha256"],
            "b9e89cb8de1969ea0531c8106d3f82750aa4791bfbf7658429855b1dd1f637fd")


if __name__ == "__main__":
    unittest.main()
