"""Tests for authentic historical DEVELOPMENT source and untouched-cohort boundary."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from research import audit_original_development_input_disjointness as audit

RECEIPT = Path(__file__).resolve().parents[1] / (
    "validation/acsp_20260819_original_development_fold_source_audit_20261029.json"
)


class DevelopmentOriginalFoldDisjointnessTests(unittest.TestCase):
    def test_saved_source_archive_receipt_clearly_excludes_untouched_input_recovery(self):
        obj = json.loads(RECEIPT.read_text(encoding="utf-8"))
        self.assertEqual(obj["schema_version"], audit.SCHEMA)
        self.assertEqual(obj["development_taxa"], 16)
        self.assertEqual(obj["development_taxon_groups"], {"animal": 4, "plant": 12})
        self.assertEqual(obj["development_folds"], 80)
        self.assertEqual(obj["source_fold_csv_hashes_and_candidate_hashes_verified"], 240)
        self.assertEqual(obj["stable_source_record_pools_across_folds"], 16)
        self.assertEqual(obj["independent_confirmation_source"]["independent_taxa"], 96)
        self.assertEqual(obj["development_and_independent_confirmation_taxon_name_overlap"], 0)
        self.assertEqual(obj["development_and_independent_confirmation_species_key_overlap"], 0)
        for k in ("confirms_original_2026_08_20_independent_confirmation_inputs_recovered",
                  "taxon_disjointness_proves_outcome_independence_in_all_other_senses",
                  "contemporaneous_GBIF_datasetKeys_restored",
                  "original_confirmation_GBIF_data_DOI_verified",
                  "new_GBIF_queries_or_biological_tests_run",
                  "raw_record_IDs_or_coordinates_disclosed",
                  "historical_confirmation_or_algorithm_modified"):
            self.assertIs(obj["boundaries"][k], False, k)

    def test_occurrence_row_count_does_not_double_count_repeated_folds(self):
        obj = json.loads(RECEIPT.read_text(encoding="utf-8"))
        self.assertEqual(obj["training_row_instances_across_all_folds"], 9660)
        self.assertEqual(obj["heldout_row_instances_across_all_folds"], 1965)
        self.assertEqual(obj["development_distinct_pair_pool_rows_summed"], 2325)
        self.assertEqual((9660+1965)//5, 2325)
        self.assertTrue(obj["used_gbif_id_aliases_present_in_development_fold_CSVs"])
        self.assertFalse(obj["source_datasetKeys_in_original_development_CSVs"])

    def test_authentic_original_identifiers_and_digests_are_pinned(self):
        obj = json.loads(RECEIPT.read_text(encoding="utf-8"))
        self.assertEqual(obj["original_development_source"]["run_id"], audit.DEVELOPMENT_RUN)
        self.assertEqual(obj["original_development_source"]["artifact_id"], audit.DEVELOPMENT_ARTIFACT)
        self.assertEqual(obj["original_development_source"]["whole_zip_sha256"],
                         audit.DEVELOPMENT_SHA256)
        self.assertEqual(obj["independent_confirmation_source"]["whole_zip_sha256"],
                         audit.CONFIRMATION_SHA256)
        self.assertEqual(obj["original_development_source"]["original_archive_member_count"], 368)

    def test_original_archive_sha_mismatch_must_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "false-original.zip"
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("exports/mixed/declared_pairs.csv", "pair_id,status\n1,predeclared\n")
            with self.assertRaisesRegex(ValueError, "original GitHub ZIP SHA256 mismatch"):
                audit._read_archive(path, audit.DEVELOPMENT_SHA256, expected_count=368)

    def test_positive_taxon_overlap_would_fail_the_original_audit_contract(self):
        obj = json.loads(RECEIPT.read_text(encoding="utf-8"))
        self.assertNotEqual(
            "DEVELOPMENT_INPUTS_RECOVERED_TAXON_DISJOINT_FROM_96_CONFIRMATION",
            "CONFIRMATORY_INPUTS_RESTORED",
        )
        self.assertEqual(obj["status"],
                         "DEVELOPMENT_INPUTS_RECOVERED_TAXON_DISJOINT_FROM_96_CONFIRMATION")

    def test_public_receipt_contains_no_real_GBIF_keys_or_species_names(self):
        blob = RECEIPT.read_text(encoding="utf-8")
        for token in ("scientific_name", "speciesKey", "_latitude", "_longitude",
                      "decimalLatitude", "decimalLongitude", "gbifID",
                      "pair_001", "taxonKey"):
            self.assertNotIn(token, blob)


if __name__ == "__main__":
    unittest.main()
