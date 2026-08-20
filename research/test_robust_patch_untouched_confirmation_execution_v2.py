from pathlib import Path
import unittest

import numpy as np

import export_robust_patch_confirmation_folds_v2 as exporter
import run_robust_patch_untouched_confirmation_v2 as confirmation


class RobustPatchUntouchedConfirmationExecutionV2Tests(unittest.TestCase):
    def test_execution_fingerprint_and_frozen_rules(self):
        payload = exporter._execution()
        self.assertEqual(payload["execution_fingerprint"], exporter.EXPECTED_EXECUTION)
        self.assertEqual(payload["protocol_fingerprint"], "68f94dbb5ad9cd6ec433653df83df323a7fc489b1ef8ded2422bd8520b0f71e6")
        self.assertEqual(payload["cohort_artifact"]["declared_pairs"], 96)
        self.assertEqual(payload["robust_support"]["support_fraction"], 0.025)
        self.assertEqual(payload["recovery"]["primary_radius_km"], 10.0)
        self.assertEqual(payload["recovery"]["random_draws_per_fold"], 200)
        self.assertEqual(payload["fold_generation"]["repeats"], 5)
        self.assertFalse(payload["retuning_after_opening_allowed"])

    def test_sign_flip_is_one_sided_and_deterministic(self):
        values = np.array([0.04, 0.03, 0.02, 0.01], dtype=float)
        p1 = confirmation._sign_flip_p(values, draws=2000, seed=123)
        p2 = confirmation._sign_flip_p(values, draws=2000, seed=123)
        self.assertEqual(p1, p2)
        self.assertGreaterEqual(p1, 0.0)
        self.assertLessEqual(p1, 1.0)

    def test_bootstrap_ci_is_deterministic(self):
        values = np.array([0.01, 0.02, 0.03, 0.04], dtype=float)
        first = confirmation._bootstrap_ci(values, draws=1000, seed=321)
        second = confirmation._bootstrap_ci(values, draws=1000, seed=321)
        self.assertEqual(first, second)
        self.assertLessEqual(first[0], float(values.mean()))
        self.assertGreaterEqual(first[1], float(values.mean()))


if __name__ == "__main__":
    unittest.main()
