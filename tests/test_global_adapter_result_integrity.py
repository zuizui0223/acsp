"""Offline checks of the evidence supporting the documented adapter boundary."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "validation"


class GlobalAdapterResultIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = json.loads((VALIDATION / "acsp_global_availability_parity_confirmation_result_v2.json").read_text(encoding="utf-8"))
        cls.path = VALIDATION / cls.result["authoritative_taxon_result_path"].split("/")[-1]
        cls.rows = pd.read_csv(cls.path).sort_values("availability_pair_id")
        cls.constructible = cls.rows.preheldout_availability_state.isin(["ROBUST_READY_PREHELDOUT", "ROBUST_EMPTY"])
        cls.evaluable = cls.constructible & cls.rows.temporal_status.eq("evaluated")

    def test_source_and_identity_integrity(self):
        # Git checks out text as CRLF on Windows; the artifact has LF bytes.
        artifact_bytes = self.path.read_bytes().replace(b"\r\n", b"\n")
        self.assertEqual(hashlib.sha256(artifact_bytes).hexdigest(), self.result["source_workflow"]["heldout_taxon_results_sha256"])
        self.assertEqual(self.result["source_workflow"]["run_id"], 34174350904)
        self.assertEqual(self.rows.availability_pair_id.tolist(), list(range(1, 49)))
        self.assertEqual(self.rows.speciesKey.nunique(), 48)
        self.assertEqual(self.rows.taxon_group.value_counts().to_dict(), {"animal": 24, "plant": 24})
        prior = pd.read_csv(VALIDATION / "acsp_country_framed_fresh_heterogeneity_confirmation_taxon_audit_v1.csv")
        self.assertFalse(set(prior.speciesKey) & set(self.rows.speciesKey))

    def test_conditional_denominators_and_empty_result(self):
        self.assertEqual(int(self.constructible.sum()), 44)
        self.assertEqual(int(self.evaluable.sum()), 35)
        self.assertEqual(self.result["robust_constructible_fraction"], 44 / 48)
        self.assertEqual(self.result["conditional_retrospective_evaluability_fraction"], 35 / 44)
        empty = self.rows[self.rows.preheldout_availability_state.eq("ROBUST_EMPTY")]
        self.assertEqual(len(empty), 1)
        self.assertEqual(empty.temporal_status.iloc[0], "evaluated")
        self.assertEqual(empty.candidate_patch_count.iloc[0], 0)
        self.assertEqual(empty.robust_minus_random_recall.iloc[0], 0)

    def test_recalculate_conditional_effect_and_bootstrap(self):
        rows = self.rows[self.evaluable]
        lifts = rows.robust_minus_random_recall.to_numpy(float)
        self.assertTrue(np.isfinite(lifts).all())
        self.assertAlmostEqual(float(lifts.mean()), self.result["conditional_mean_robust_minus_random_recall"], places=14)
        rng = np.random.default_rng(2026090703)
        means = np.array([rng.choice(lifts, size=len(lifts), replace=True).mean() for _ in range(10000)])
        np.testing.assert_allclose(np.quantile(means, [0.025, 0.975]), self.result["taxon_bootstrap_95pct_ci"], rtol=0, atol=1e-14)
        for group in ("plant", "animal"):
            mean = rows.loc[rows.taxon_group.eq(group), "robust_minus_random_recall"].mean()
            self.assertAlmostEqual(mean, self.result[f"{group}_mean_robust_minus_random_recall"], places=14)
            self.assertGreaterEqual(mean, 0)
        self.assertGreater(float(lifts.mean()), 0)
        self.assertGreater(float(np.quantile(means, 0.025)), 0)
        self.assertTrue(all(self.result["gate_checks"].values()))

    def test_promotion_preserves_information_boundary(self):
        for flag in ("same_cohort_retuning", "taxon_or_country_replacement", "validated_japan_core_changed"):
            self.assertTrue(self.rows[flag].eq(False).all())
        self.assertFalse(self.result["explicit_user_target_country_substitution_behavior_changed"])
        self.assertTrue(self.result["global_automatic_adapter_promoted"])
        self.assertTrue(self.rows.primary_radius_km.eq(10).all())


if __name__ == "__main__":
    unittest.main()
