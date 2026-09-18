from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

import diagnose_country_frame_selection as diagnosis


class CountryFrameSelectionDiagnosisTests(unittest.TestCase):
    def test_failed_sparse_selection_exposes_richer_historical_alternative_without_rerun(self) -> None:
        frame = pd.DataFrame([
            {
                "fresh_pair_id": 13,
                "scientific_name": "Example species",
                "selected_country_code": "LV",
                "historical_selected_country_count": 6,
                "historical_country_counts_json": json.dumps({"LV": 6, "CN": 7207, "JP": 3445}),
                "candidate_generation_status": "candidate_generation_failed",
                "candidate_generation_failure_reason": "fewer than five complete prototypes",
            }
        ])
        with patch.object(diagnosis, "_supported_alpha2_codes", return_value={"LV", "CN", "JP"}):
            detail, summary = diagnosis.diagnose(frame)
        row = detail.iloc[0]
        self.assertEqual(row["evidence_first_country_code"], "CN")
        self.assertEqual(int(row["historical_count_gain"]), 7201)
        self.assertEqual(summary["candidate_failures_with_higher_supported_historical_alternative"], 1)
        self.assertFalse(summary["heldout_used_to_choose_country"])
        self.assertFalse(summary["robust_support_rerun"])
        self.assertFalse(summary["counterfactual_candidate_generation_success_claimed"])

    def test_provider_unsupported_frozen_country_can_be_diagnosed_but_not_claimed_rescued(self) -> None:
        frame = pd.DataFrame([
            {
                "fresh_pair_id": 19,
                "scientific_name": "Example bird",
                "selected_country_code": "HK",
                "historical_selected_country_count": 8,
                "historical_country_counts_json": json.dumps({"HK": 8, "TW": 17881}),
                "candidate_generation_status": "not_attempted_declaration_failed",
                "candidate_generation_failure_reason": "",
            }
        ])
        with patch.object(diagnosis, "_supported_alpha2_codes", return_value={"TW"}):
            detail, summary = diagnosis.diagnose(frame)
        row = detail.iloc[0]
        self.assertFalse(bool(row["frozen_selected_provider_supported"]))
        self.assertEqual(row["evidence_first_country_code"], "TW")
        self.assertFalse(summary["counterfactual_predictive_lift_claimed"])


if __name__ == "__main__":
    unittest.main()
