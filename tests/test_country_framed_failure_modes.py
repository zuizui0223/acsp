from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

from summarize_country_framed_failure_modes import summarize


class CountryFramedFailureModeTests(unittest.TestCase):
    def test_availability_failures_are_separate_from_integrated_prediction_signal(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "declaration_status": "declared",
                    "candidate_generation_status": "generated",
                    "candidate_generation_failure_reason": "",
                    "temporal_status": "evaluated",
                    "robust_minus_random_recall": 0.2,
                },
                {
                    "declaration_status": "declared",
                    "candidate_generation_status": "candidate_generation_failed",
                    "candidate_generation_failure_reason": "fewer than five usable historical occurrence rows",
                    "temporal_status": "zero_recent_country_records",
                    "robust_minus_random_recall": None,
                },
                {
                    "declaration_status": "declared",
                    "candidate_generation_status": "candidate_generation_failed",
                    "candidate_generation_failure_reason": "robust candidate generation returned zero candidate patches",
                    "temporal_status": "evaluated",
                    "robust_minus_random_recall": None,
                },
                {
                    "declaration_status": "failed",
                    "candidate_generation_status": "not_attempted_declaration_failed",
                    "candidate_generation_failure_reason": "country declaration failed",
                    "temporal_status": "not_attempted_no_declared_country",
                    "robust_minus_random_recall": None,
                },
            ]
        )
        result = summarize(frame)
        self.assertEqual(result["declared_units"], 4)
        self.assertEqual(result["country_declaration_success"], 3)
        self.assertEqual(result["country_declaration_failure"], 1)
        self.assertEqual(result["candidate_generation_success"], 1)
        self.assertEqual(result["candidate_generation_failure"], 3)
        self.assertEqual(result["candidate_failure_modes"]["country_declaration_failed"], 1)
        self.assertEqual(result["candidate_failure_modes"]["insufficient_historical_evidence_or_complete_prototypes"], 1)
        self.assertEqual(result["candidate_failure_modes"]["robust_core_returned_zero_candidate_patches"], 1)
        self.assertEqual(result["candidate_failure_modes"]["other"], 0)
        self.assertEqual(result["temporally_evaluable"], 2)
        self.assertEqual(result["temporal_failure_modes"]["zero_recent_country_records"], 1)
        self.assertEqual(result["temporal_failure_modes"]["no_declared_country"], 1)
        self.assertEqual(result["integrated_evaluable"], 1)
        self.assertAlmostEqual(result["rates"]["candidate_generation_success"], 0.25)
        self.assertAlmostEqual(result["rates"]["candidate_generation_success_given_declaration"], 1 / 3)
        self.assertAlmostEqual(result["rates"]["temporal_evaluability"], 0.5)
        self.assertAlmostEqual(result["rates"]["integrated_evaluability"], 0.25)
        self.assertFalse(result["scientific_method_changed"])
        self.assertFalse(result["subset_rescue_used"])

    def test_unknown_failure_stays_visible_in_other_bin(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "declaration_status": "declared",
                    "candidate_generation_status": "candidate_generation_failed",
                    "candidate_generation_failure_reason": "unexpected provider decoding failure",
                    "temporal_status": "provider_failed",
                    "robust_minus_random_recall": None,
                }
            ]
        )
        result = summarize(frame)
        self.assertEqual(result["candidate_failure_modes"]["other"], 1)
        self.assertEqual(result["temporal_failure_modes"]["other"], 1)


if __name__ == "__main__":
    unittest.main()
