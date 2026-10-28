"""Strict no-input-record audit of two *related*, nonindependent original runs."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from research import audit_original_v2_seed_offset_parity as audit

RECEIPT = Path(__file__).resolve().parents[1] / (
    "validation/acsp_original_v2_rng_seed_parity_20261028.json"
)


class OriginalSeedParityTests(unittest.TestCase):
    def test_archival_comparison_is_not_an_independent_confirmation(self):
        doc = json.loads(RECEIPT.read_text(encoding="utf-8"))
        self.assertEqual(doc["schema_version"], audit.SCHEMA)
        self.assertEqual(doc["status"],
                         "HISTORICAL_NONINDEPENDENT_SEED_IMPLEMENTATION_COMPARISON")
        self.assertEqual(doc["provenance"]["prior_successful_run"], 32336724090)
        self.assertEqual(doc["provenance"]["final_official_run"], 32337884576)
        self.assertEqual(doc["provenance"]["prior_artifact_id"], 9395679418)
        self.assertEqual(doc["provenance"]["final_artifact_id"], 9396133154)
        for key in ("independent_new_taxa_or_cohort",
                    "historical_input_GBIF_rows_byte_verified_equal",
                    "comparison_is_controlled_fixed_input_RNG_experiment",
                    "causal_attribution_only_to_seed_proven",
                    "original_source_occurence_rows_recovered",
                    "new_biological_or_field_effect",
                    "original_frozen_method_parameters_retuned",
                    "new_confirmatory_statistical_test"):
            self.assertIs(doc["scientific_limits"][key], False, key)
        audit.verify_saved_receipt(doc, RECEIPT)

    def test_changes_are_random_comparison_only(self):
        doc = json.loads(RECEIPT.read_text(encoding="utf-8"))
        self.assertEqual(doc["frozen_geometry_and_recovery_outputs"]
                         ["original_fold_by_radius_rows"], 1920)
        self.assertEqual(doc["frozen_geometry_and_recovery_outputs"]
                         ["changed_random_baseline_fold_by_radius_rows"], 1287)
        self.assertEqual(doc["frozen_geometry_and_recovery_outputs"]
                         ["changed_pair_mean_lift_rows"], 78)
        self.assertEqual([doc["by_radius_descriptive_only"][x]
                          ["changed_random_baseline_folds"] for x in ("1", "2", "5", "10")],
                         [225, 324, 369, 369])
        self.assertTrue(doc["frozen_geometry_and_recovery_outputs"]
                        ["unaltered_nonlinear_support_fields_and_recall_in_all_rows"])
        self.assertTrue(doc["primary_10km"]["both_passed_frozen_gates"])
        self.assertAlmostEqual(doc["primary_10km"]
                               ["mean_lift_difference_final_minus_prior"],
                               0.000833813015095833, places=12)

    def test_precise_prior_archive_digest_locked(self):
        self.assertEqual(audit.PRIOR_ARCHIVE["archive_sha256"],
                         "7b7bc3dd069c948bb7c63254b3e50e2822d3a8bbe51bd3a4f245dd04aad297f3")
        self.assertEqual(len(audit.PRIOR_ARCHIVE["member_sha256"]), 6)
        self.assertEqual(audit.PRIOR_HEAD_SHA,
                         "df6277f4d9e8b3e36a5dad1730affb8db69da48a")
        self.assertEqual(audit.FINAL_HEAD_SHA,
                         "39c9e6853f8d8aeffe42acd1258fe4f8f936f009")

    def test_nonlinear_ecological_recall_drift_must_fail_closed(self):
        b = [{"pair_id": "1", "repeat": "1", "radius_km": "10.0",
              "recall": "0.25", "random_mean_recall": "0.05",
              "lift_over_random": "0.20"}]
        a = [dict(b[0], recall="0.50", random_mean_recall="0.07",
                  lift_over_random="0.43")]
        with self.assertRaisesRegex(ValueError, "frozen non-random result changed"):
            audit._aligned(b, a, ("pair_id", "repeat", "radius_km"),
                           audit.BASELINE_DIFF_FIELDS)

    def test_only_baseline_comparator_change_is_permitted_in_alignment(self):
        b = [{"pair_id": "1", "repeat": "1", "radius_km": "10.0",
              "recall": "0.25", "random_mean_recall": "0.05",
              "lift_over_random": "0.20"}]
        a = [dict(b[0], random_mean_recall="0.07", lift_over_random="0.18")]
        paired = audit._aligned(b, a, ("pair_id", "repeat", "radius_km"),
                                audit.BASELINE_DIFF_FIELDS)
        self.assertEqual(len(paired), 1)
        self.assertTrue(audit._changed("0.05", "0.07"))

    def test_public_receipt_rejects_changed_official_mean(self):
        doc = json.loads(RECEIPT.read_text(encoding="utf-8"))
        doc["primary_10km"]["final_mean_lift"] = 0.9999
        with self.assertRaisesRegex(ValueError, "numerical change"):
            audit.verify_saved_receipt(doc, RECEIPT)

    def test_no_coordinates_names_or_record_lists_in_report(self):
        serial = RECEIPT.read_text(encoding="utf-8")
        for term in ("scientific_name", "longitude", "latitude", "gbifID",
                     "datasetKey", "original_record_ids"):
            self.assertNotIn(term, serial)


if __name__ == "__main__":
    unittest.main()
