from __future__ import annotations

from pathlib import Path
import unittest

import pandas as pd

from country_framed_integration_v2_pair_core import evaluate_one_v2_core
from country_framed_integration_v2_replication_execution_contract import (
    EXPECTED_EXECUTION_FINGERPRINT,
    execution_contract,
)
from predeclare_country_framed_integration_development_v1 import SOURCE_COHORT_PATH
from predeclare_country_framed_integration_development_v2 import select_v2_taxa
from predeclare_country_framed_integration_development_v2_replication import (
    EXPECTED_REPLICATION_PROTOCOL_FINGERPRINT,
    replication_protocol,
    select_replication_taxa,
)
import aggregate_country_framed_integration_development_v2_replication as replication_aggregate
import run_country_framed_integration_development_v2_replication_pair as replication_pair
import run_country_framed_integration_development_v2_timeout_retry_pair as retry_pair

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "country-framed-integration-development-v2-replication.yml"


class ReplicationExecutionContractTests(unittest.TestCase):
    def test_execution_contract_is_frozen_before_identities(self):
        contract = execution_contract()
        self.assertEqual(contract["execution_fingerprint"], EXPECTED_EXECUTION_FINGERPRINT)
        self.assertEqual(contract["status"], "frozen_before_replication_identities")
        self.assertTrue(contract["trigger_evidence"]["v2_development_gate_passed"])
        d = contract["execution_decomposition"]
        self.assertTrue(d["identity_freeze_first"])
        self.assertEqual(d["pair_shard_count"], 24)
        self.assertEqual(d["max_parallel"], 4)
        self.assertEqual(d["pair_ids"], list(range(1, 25)))
        self.assertEqual(d["pair_timeout_minutes"], 300)
        self.assertFalse(d["fail_fast"])
        self.assertTrue(d["aggregate_once_after_all_pairs"])
        self.assertTrue(d["same_frozen_declarations_artifact"])
        self.assertTrue(d["candidate_generation_before_recent_outcome"])
        for key in (
            "scientific_method_changed",
            "cohort_rule_changed",
            "country_declaration_rule_changed",
            "regional_lattice_changed",
            "robust_core_changed",
            "endpoint_changed",
            "random_baseline_changed",
            "gate_changed",
            "seed_changed",
        ):
            self.assertFalse(d[key], key)
        self.assertFalse(contract["failure_semantics"]["technical_failure_is_scientific_failure"])
        self.assertFalse(contract["failure_semantics"]["retuning_on_replication_taxa_allowed"])

    def test_replication_selection_is_exact_reserved_quarter(self):
        replication_protocol()
        frame = pd.read_csv(SOURCE_COHORT_PATH)
        replication = select_replication_taxa(frame)
        v2 = select_v2_taxa(frame)
        self.assertEqual(len(replication), 24)
        self.assertEqual(replication["speciesKey"].nunique(), 24)
        self.assertFalse(set(replication["speciesKey"].astype(int)) & set(v2["speciesKey"].astype(int)))
        self.assertEqual(replication["taxon_group"].value_counts().to_dict(), {"plant": 12, "animal": 12})
        self.assertEqual(
            replication["record_count_stratum"].astype(int).value_counts().sort_index().to_dict(),
            {0: 6, 1: 6, 2: 6, 3: 6},
        )

    def test_v2_retry_and_replication_use_same_pair_core(self):
        self.assertIs(retry_pair.evaluate_one.__globals__["evaluate_one_v2_core"], evaluate_one_v2_core)
        self.assertIs(replication_pair.evaluate_one_replication.__globals__["evaluate_one_v2_core"], evaluate_one_v2_core)
        self.assertEqual(
            replication_pair.EXPECTED_REPLICATION_PROTOCOL_FINGERPRINT,
            EXPECTED_REPLICATION_PROTOCOL_FINGERPRINT,
        )
        self.assertEqual(replication_pair.EXPECTED_EXECUTION_FINGERPRINT, EXPECTED_EXECUTION_FINGERPRINT)

    def test_workflow_cannot_open_identities_from_pr_event(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("pull_request:", text)
        self.assertIn("needs: freeze-identities", text)
        self.assertIn("fail-fast: false", text)
        self.assertIn("max-parallel: 4", text)
        self.assertIn("timeout-minutes: 300", text)
        self.assertIn("country-framed-integration-development-v2-replication-cohort", text)
        self.assertIn("Evaluate one frozen declaration with unchanged authoritative v2 method", text)
        self.assertIn("run_country_framed_integration_development_v2_replication_pair.py", text)
        self.assertIn("replication_execution_fingerprint", text)

    def test_workflow_and_aggregator_share_pair_artifact_prefix(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(replication_aggregate.PAIR_ARTIFACT_GLOB, "replication-pair-*")
        self.assertIn("name: replication-pair-${{ matrix.pair-id }}", text)
        self.assertIn("pattern: replication-pair-*", text)


if __name__ == "__main__":
    unittest.main()
