from __future__ import annotations

import inspect
import json
from pathlib import Path
import unittest

import run_global_availability_parity_heldout_v2 as h

ROOT = Path(__file__).resolve().parents[1]


class GlobalAvailabilityParityHeldoutV2Tests(unittest.TestCase):
    def test_stage3_identity_is_pinned(self):
        self.assertEqual(h.STAGE3_RUN_ID, 34134427957)
        self.assertEqual(h.STAGE3_AGGREGATE_ARTIFACT_ID, 10033756992)
        self.assertEqual(
            h.PREHELDOUT_STATES_SHA256,
            "23554f0f189712a98d74ac1901c9c62037df3df3fc2c9fddf0d8299af0c1544d",
        )
        self.assertEqual(
            h.EXPECTED_STAGE3_COUNTS,
            {"ROBUST_READY_PREHELDOUT": 43, "ROBUST_EMPTY": 1, "SENTINEL_OR_ABSTAIN": 4},
        )

    def test_stage5_source_does_not_regenerate_candidates(self):
        source = inspect.getsource(h)
        forbidden = (
            "validated_robust_candidate_patches(",
            "regional_terrain_inputs(",
            "fetch_country_occurrences(",
            "fetch_geoboundaries_country_geometry(",
        )
        for token in forbidden:
            self.assertNotIn(token, source)
        self.assertIn("fetch_recent_country_occurrences(", source)
        self.assertIn("same_size_random_recovery(", source)

    def test_frozen_primary_gates_remain_unchanged(self):
        p = json.loads((ROOT / "validation/acsp_global_availability_parity_confirmation_v2.json").read_text())
        dims = p["primary_dimensions"]
        self.assertEqual(dims["availability"]["robust_constructible_fraction_min"], 0.75)
        self.assertEqual(dims["retrospective_evaluability"]["conditional_fraction_min"], 0.75)
        self.assertEqual(dims["conditional_predictive_validity"]["mean_robust_minus_random_lift_gt"], 0.0)
        self.assertEqual(dims["conditional_predictive_validity"]["taxon_bootstrap_95_ci_lower_gt"], 0.0)
        self.assertEqual(dims["conditional_predictive_validity"]["plant_mean_lift_gte"], 0.0)
        self.assertEqual(dims["conditional_predictive_validity"]["animal_mean_lift_gte"], 0.0)
        self.assertTrue(dims["conditional_predictive_validity"]["include_evaluable_ROBUST_EMPTY_as_zero_lift"])

    def test_stage4_receipt_forbids_preopening(self):
        receipt = h._receipt()
        self.assertFalse(receipt["information_boundary"]["heldout_2021_2025_opened"])
        self.assertFalse(receipt["information_boundary"]["random_baseline_run"])
        self.assertFalse(receipt["information_boundary"]["recall_or_lift_read"])
        self.assertFalse(receipt["information_boundary"]["taxon_or_country_replacement"])
        self.assertFalse(receipt["information_boundary"]["validated_japan_core_changed"])


if __name__ == "__main__":
    unittest.main()
