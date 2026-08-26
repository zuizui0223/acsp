from __future__ import annotations

import inspect
from pathlib import Path
import unittest

import numpy as np

import aggregate_country_framed_fresh_heterogeneity_confirmation as aggregate
import country_framed_fresh_heterogeneity_execution as execution
import run_country_framed_fresh_heterogeneity_ru as ru

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "country-framed-fresh-heterogeneity-confirmation-execution.yml"


class FreshHeterogeneityExecutionTests(unittest.TestCase):
    def test_execution_contract_is_frozen_after_identity_before_outcomes(self):
        contract = execution.execution_contract()
        self.assertEqual(contract["execution_fingerprint"], execution.EXPECTED_FRESH_EXECUTION_FINGERPRINT)
        self.assertEqual(contract["fresh_protocol_fingerprint"], execution.EXPECTED_FRESH_PROTOCOL_FINGERPRINT)
        self.assertFalse(contract["guards"]["scientific_method_changed"])
        self.assertFalse(contract["guards"]["outcome_driven_tuning"])
        self.assertFalse(contract["guards"]["taxa_replaced"])
        self.assertFalse(contract["guards"]["countries_replaced"])
        self.assertEqual(contract["cohort_source"]["declared_taxa"], 48)
        self.assertEqual(contract["cohort_source"]["artifact_id"], 9590098991)

    def test_pair_partition_is_complete_and_disjoint(self):
        self.assertEqual(execution.RU_PAIR_IDS, (2, 4, 6, 16))
        self.assertEqual(execution.FAILED_DECLARATION_PAIR_IDS, (19, 41))
        self.assertEqual(set(execution.NON_RU_PAIR_IDS) | set(execution.RU_PAIR_IDS), set(range(1, 49)))
        self.assertFalse(set(execution.NON_RU_PAIR_IDS) & set(execution.RU_PAIR_IDS))
        self.assertTrue(set(execution.FAILED_DECLARATION_PAIR_IDS).issubset(set(execution.NON_RU_PAIR_IDS)))

    def test_non_ru_runner_uses_unchanged_v2_pair_core(self):
        source = inspect.getsource(execution)
        self.assertIn("from country_framed_integration_v2_pair_core import evaluate_one_v2_core", source)
        self.assertIn("results, patches = evaluate_one_v2_core(hit.iloc[0])", source)
        for forbidden in ("VALIDATED_ROBUST_SUPPORT_FRACTION =", "patch_merge_distance_m =", "random_baseline_repetitions ="):
            self.assertNotIn(forbidden, source)

    def test_ru_wrapper_reuses_equivalence_tested_module(self):
        source = inspect.getsource(ru)
        self.assertIn("import run_replication_ru_robust_world_recovery as _ru", source)
        self.assertNotIn("def robust_environment_geometry", source)
        self.assertNotIn("def exact_fast_support_cells_to_patches", source)
        self.assertEqual(ru.WORLD_SHARD_COUNT, 8)

    def test_heterogeneity_is_secondary_and_bootstrap_is_deterministic(self):
        contract = execution.execution_contract()
        self.assertTrue(contract["aggregate"]["heterogeneity_secondary_only"])
        self.assertFalse(contract["aggregate"]["heterogeneity_changes_primary_decision"])
        plant = np.asarray([0.1, 0.2, 0.6, -0.1], dtype=float)
        animal = np.asarray([0.1, 0.12, 0.15, 0.08], dtype=float)
        first = aggregate._heterogeneity_bootstrap(plant, animal, repetitions=500, seed=2026082602)
        second = aggregate._heterogeneity_bootstrap(plant, animal, repetitions=500, seed=2026082602)
        self.assertEqual(first, second)
        self.assertGreater(first[0], 1.0)

    def test_workflow_is_marker_only_and_requires_all_48_pairs(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("validation/activate_country_framed_fresh_heterogeneity_confirmation_execution.marker", text)
        self.assertNotIn("pull_request:", text)
        self.assertIn("RUN_NUMBER", text)
        self.assertIn("pair_id: [2, 4, 6, 16]", text)
        self.assertIn("pattern: fresh-pair-*", text)
        self.assertIn("expected 48 fresh pair artifacts", inspect.getsource(aggregate))
        self.assertIn("needs: [non-ru-pair, ru-assemble]", text)


if __name__ == "__main__":
    unittest.main()
