"""Original-result descriptive report checks: not new biology or GBIF input recovery."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from research import describe_original_v2_patch_heterogeneity as m

RECEIPT = Path(__file__).resolve().parents[1] / (
    "validation/acsp_original_v2_descriptive_heterogeneity_20261028.json"
)


class DescriptiveHeterogeneityTests(unittest.TestCase):
    def test_saved_original_descriptive_receipt_is_bounded(self):
        data = json.loads(RECEIPT.read_text(encoding="utf-8"))
        self.assertEqual(data["status"],
                         "POSTHOC_DESCRIPTION_OF_FROZEN_VALIDATION_NOT_INDEPENDENT_CONFIRMATION")
        self.assertEqual(data["declared_pair_count"], 96)
        self.assertEqual(data["all_declared_fold_by_radius_rows"], 1920)
        self.assertEqual(data["primary_10km"]["sign_counts"],
                         {"positive": 54, "zero": 17, "negative": 25})
        self.assertEqual(data["pair_failure_strata_descriptive_only"]
                         ["five_failed_folds_count"], 17)
        self.assertEqual(data["primary_10km_failure_reasons"]["no_failure"], 375)
        self.assertEqual(data["primary_10km_failure_reasons"]
                         ["insufficient_environment_prototypes"], 55)
        self.assertEqual(data["primary_10km_failure_reasons"]
                         ["empty_robust_support"], 39)
        self.assertEqual(data["regional_means_positive"], 10)
        self.assertEqual(data["regional_means_negative"], 2)
        self.assertEqual(data["regions_descriptive_only"]["Izu"]["pairs_with_failed_folds"], 8)
        self.assertEqual(len(data["regions_descriptive_only"]), 12)
        self.assertEqual([p["radius_km"] for p in data["distance_scales_descriptive_only"]],
                         [1, 2, 5, 10])
        self.assertAlmostEqual(data["primary_10km"]["mean_lift"], 0.08558708102617191)
        self.assertFalse(data["science_boundary"]["new_gbif_queries_or_field_outcomes_used"])
        self.assertFalse(data["science_boundary"]["raw_original_gbif_occurrence_inputs_recovered"])
        self.assertFalse(data["science_boundary"]["regional_differences_causal_or_confirmatory"])
        self.assertFalse(data["science_boundary"]["primary_frozen_inference_or_denominator_changed"])

    def test_saved_report_does_not_publish_record_coordinates_or_taxon_names(self):
        serialized = RECEIPT.read_text(encoding="utf-8")
        for token in ("scientific_name", "gbifID", "_latitude", "_longitude",
                      "decimalLatitude", "decimalLongitude", "pair_id"):
            self.assertNotIn(token, serialized)
        self.assertEqual(json.loads(serialized)["original_artifact_id"], 9396133154)

    def test_zero_failure_reason_is_separate_from_biological_nondetection(self):
        data = json.loads(RECEIPT.read_text(encoding="utf-8"))
        self.assertTrue(data["primary_10km"]["zero_is_not_biological_nondetection"])
        self.assertEqual(data["pair_failure_strata_descriptive_only"]
                         ["one_or_more_failed_folds"]["n_pairs"], 23)
        self.assertEqual(data["pair_failure_strata_descriptive_only"]
                         ["no_failed_fold"]["n_pairs"], 73)
        self.assertTrue(data["pair_failure_strata_descriptive_only"]
                        ["not_for_complete_case_reestimation"])

    def test_same_size_random_and_unmodified_primary_inference(self):
        data = json.loads(RECEIPT.read_text(encoding="utf-8"))
        self.assertEqual(data["taxon_groups"]["plant"]["n_pairs"], 48)
        self.assertEqual(data["taxon_groups"]["animal"]["n_pairs"], 48)
        self.assertAlmostEqual(data["taxon_groups"]["plant"]["mean_lift"],
                               0.057023839246432256)
        self.assertAlmostEqual(data["taxon_groups"]["animal"]["mean_lift"],
                               0.11415032280591153)
        self.assertAlmostEqual(data["distance_scales_descriptive_only"][-1]["mean_lift"],
                               data["primary_10km"]["mean_lift"])


if __name__ == "__main__":
    unittest.main()
