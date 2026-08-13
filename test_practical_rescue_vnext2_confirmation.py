import unittest

import numpy as np
import pandas as pd

from aggregate_practical_rescue_vnext2_confirmation import _inference, _passes
from run_practical_rescue_vnext2_confirmation_pair import _scientific_zero_fold


class PracticalRescueVNext2ConfirmationTests(unittest.TestCase):
    def test_primary_gate_requires_practical_margin_ci_and_p(self):
        result = {
            "mean_difference": 0.016,
            "bootstrap_95ci_low": 0.001,
            "sign_flip_p": 0.049,
        }
        self.assertTrue(_passes(result, 0.015))
        for key, value in (
            ("mean_difference", 0.0149),
            ("bootstrap_95ci_low", 0.0),
            ("sign_flip_p", 0.05),
        ):
            failed = dict(result)
            failed[key] = value
            self.assertFalse(_passes(failed, 0.015))

    def test_inference_handles_clear_signal(self):
        values = np.array([0.02, 0.03, 0.04, 0.01] * 24, dtype=float)
        result = _inference(values, 5000, 20260815)
        self.assertGreater(result["mean_difference"], 0.015)
        self.assertGreater(result["bootstrap_95ci_low"], 0.0)
        self.assertLess(result["sign_flip_p"], 0.05)

    def test_scientific_zero_is_shared_across_all_primary_methods(self):
        pair = pd.Series({
            "pair_id": 1,
            "taxon_group": "plant",
            "scientific_name": "Example species",
            "region_name": "example",
        })
        row = _scientific_zero_fold(pair, 1, "test_reason", 0)
        for key in (
            "router_recovery_10km",
            "frozen_v1_recovery_10km",
            "rescue_v2_recovery_10km",
            "grts_mean_recovery_10km",
            "local_only_recovery_10km",
            "geographic_recovery_10km",
            "random_mean_recovery_10km",
        ):
            self.assertEqual(row[key], 0.0)
        self.assertEqual(row["fold_status"], "explicit_scientific_zero")
        self.assertEqual(row["grts_error_draws"], 0)
        self.assertFalse(row["outcomes_available_to_router"])
        self.assertFalse(row["outcomes_available_to_grts_selector"])


if __name__ == "__main__":
    unittest.main()
