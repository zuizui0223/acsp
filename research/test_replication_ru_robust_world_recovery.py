from __future__ import annotations

from pathlib import Path
import unittest

import run_replication_ru_robust_world_recovery as recovery
import run_ru_robust_world_shard_fallback as prior

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "country-framed-integration-v2-replication-ru-recovery.yml"


class ReplicationRuRecoveryTests(unittest.TestCase):
    def test_contract_is_exact_and_outcome_blind(self):
        contract = recovery.recovery_contract()
        self.assertEqual(contract["execution_fingerprint"], recovery.EXPECTED_RECOVERY_FINGERPRINT)
        self.assertEqual(contract["source_replication"]["workflow_run_id"], 32811169261)
        self.assertEqual(tuple(contract["source_replication"]["ru_pair_ids"]), recovery.RU_PAIR_IDS)
        self.assertTrue(contract["activation_rule"]["source_run_must_be_completed"])
        self.assertTrue(contract["activation_rule"]["recover_only_ru_pairs_with_job_conclusion_cancelled"])
        self.assertEqual(contract["activation_rule"]["minimum_cancelled_job_runtime_minutes"], 299)
        self.assertTrue(contract["activation_rule"]["reuse_successful_source_pair_artifacts"])
        self.assertTrue(contract["activation_rule"]["no_fresh_identity_freeze"])
        self.assertTrue(contract["activation_rule"]["no_outcome_driven_selection"])
        self.assertFalse(contract["execution_rule"]["scientific_method_changed"])
        self.assertFalse(contract["execution_rule"]["outcome_driven_tuning_allowed"])

    def test_recovery_reuses_exact_prior_ru_surface_and_world_semantics(self):
        self.assertEqual(recovery.EXPECTED_SURFACE_SHA256, prior.EXPECTED_SURFACE_SHA256)
        self.assertEqual(recovery.EXPECTED_SURFACE_MANIFEST_SHA256, prior.EXPECTED_SURFACE_MANIFEST_SHA256)
        self.assertEqual(recovery.SOURCE_RU_SURFACE_RUN_ID, prior.SOURCE_RU_SURFACE_RUN_ID)
        self.assertEqual(recovery.SOURCE_RU_SURFACE_ARTIFACT_ID, prior.SOURCE_RU_SURFACE_ARTIFACT_ID)
        self.assertEqual(recovery.WORLD_SHARD_COUNT, prior.WORLD_SHARD_COUNT)
        self.assertIs(recovery.exact_fast_support_cells_to_patches, prior.exact_fast_support_cells_to_patches)
        self.assertIs(recovery.robust_environment_geometry, prior.robust_environment_geometry)

    def test_workflow_is_marker_only_and_never_refreezes_replication(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("branches: [main]", text)
        self.assertIn("activate_country_framed_integration_development_v2_replication_ru_recovery.marker", text)
        self.assertNotIn("pull_request:", text)
        self.assertNotIn("workflow_dispatch:", text)
        self.assertIn("GITHUB_RUN_NUMBER'] == '1'", text)
        self.assertIn("source replication run is not complete", text)
        self.assertIn("runtime >= 299.0", text)
        self.assertIn("run-id: 32811169261", text)
        self.assertIn("name: country-framed-integration-development-v2-replication-cohort", text)
        self.assertIn("name: ru-complete-surface", text)
        self.assertNotIn("predeclare_country_framed_integration_development_v2_replication.py --output", text)

    def test_workflow_recovers_only_timeouts_and_reuses_successful_pairs(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("if conclusion=='success'", text)
        self.assertIn("if conclusion=='cancelled' and runtime >= 299.0", text)
        self.assertIn("pattern: replication-pair-*", text)
        self.assertIn("pattern: replication-ru-recovery-pair-*", text)
        self.assertIn("aggregate_country_framed_integration_development_v2_replication.py", text)
        self.assertIn("replication_ru_recovery_cohort_refrozen':False", text)
        self.assertIn("replication_ru_recovery_outcome_driven_tuning':False", text)


if __name__ == "__main__":
    unittest.main()
