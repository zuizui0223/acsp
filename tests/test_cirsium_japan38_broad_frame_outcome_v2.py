from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

import run_cirsium_japan38_broad_frame_confirmation_v2 as target


class Japan38ProviderIdentityHeldoutTests(unittest.TestCase):
    def test_amendment_freezes_one_duplicate_provider_identity_group(self):
        amendment = json.loads(target.AMENDMENT_PATH.read_text(encoding="utf-8"))
        self.assertFalse(amendment["recent_outcomes_opened_before_amendment"])
        self.assertEqual(amendment["provider_identity_audit"]["constructible_concept_rows"], 13)
        self.assertEqual(amendment["provider_identity_audit"]["unique_constructible_gbif_usage_keys"], 11)
        duplicate = amendment["provider_identity_audit"]["duplicate_usage_key_groups"]
        self.assertEqual(len(duplicate), 1)
        self.assertEqual(duplicate[0]["matched_usage_key"], 3113139)
        self.assertEqual(duplicate[0]["member_ids"], ["JPN_20", "JPN_21", "JPN_35"])
        self.assertEqual(duplicate[0]["canonical_representative_member_id"], "JPN_20")
        self.assertEqual(len(amendment["constructible_provider_identities"]), 11)

    def test_primary_aggregate_uses_frozen_thresholds(self):
        contract = {
            "outcome": {"primary_recovery_radius_km": 1.0},
            "primary_endpoint": {
                "minimum_temporally_evaluable_taxa": 8,
                "minimum_fraction_evaluable_taxa_with_strictly_positive_difference": 0.5,
                "minimum_cluster_weighted_added_recall": 0.1,
            },
        }
        results = [
            {"status": "TEMPORALLY_EVALUABLE", "primary_positive": i < 4}
            for i in range(8)
        ] + [{"status": "NOT_EVALUABLE_NO_STRICT_RECENT_POPULATION"} for _ in range(3)]
        rows = []
        # 10 novel clusters per evaluable identity; BROAD recovers 32 more than LOCAL5.
        for i in range(8):
            rows.append({"matched_usage_key": i, "lane_id": "BROAD_LAND", "recovery_radius_km": 1.0, "novel_population_count": 10, "recovered_novel_populations": 56 // 8})
            rows.append({"matched_usage_key": i, "lane_id": "LOCAL_5KM_LAND", "recovery_radius_km": 1.0, "novel_population_count": 10, "recovered_novel_populations": 24 // 8})
        out = target._primary_aggregate(results, pd.DataFrame(rows), contract)
        self.assertEqual(out["temporally_evaluable_provider_identities"], 8)
        self.assertEqual(out["positive_fraction"], 0.5)
        self.assertGreaterEqual(out["cluster_weighted_broad_minus_local5_added_recall"], 0.1)
        self.assertTrue(out["all_preregistered_gates_passed"])

    def test_run_fetches_recent_once_per_unique_provider_identity(self):
        amendment = {
            "constructible_provider_identities": [
                {"matched_usage_key": key, "canonical_member_id": f"JPN_{key:02d}"}
                for key in range(1, 12)
            ]
        }
        contract = {
            "outcome": {"primary_recovery_radius_km": 1.0},
            "primary_endpoint": {
                "minimum_temporally_evaluable_taxa": 8,
                "minimum_fraction_evaluable_taxa_with_strictly_positive_difference": 0.5,
                "minimum_cluster_weighted_added_recall": 0.1,
            },
        }
        roster = pd.DataFrame({"member_id": [f"JPN_{i:02d}" for i in range(1, 14)]})
        preflight_rows = []
        for i in range(1, 12):
            preflight_rows.append({
                "unit_id": f"JPN_{i:02d}",
                "species": f"Taxon {i}",
                "status": "PREOUTCOME_CANDIDATE_UNIVERSES_FROZEN",
                "gbif_historical_audit": {"matched_usage_key": i, "matched_scientific_name": f"Taxon {i}"},
            })
        preflight_rows.extend([
            {"unit_id": "JPN_12", "species": "Alias 12", "status": "PREOUTCOME_CANDIDATE_UNIVERSES_FROZEN", "gbif_historical_audit": {"matched_usage_key": 1, "matched_scientific_name": "Taxon 1"}},
            {"unit_id": "JPN_13", "species": "Alias 13", "status": "PREOUTCOME_CANDIDATE_UNIVERSES_FROZEN", "gbif_historical_audit": {"matched_usage_key": 1, "matched_scientific_name": "Taxon 1"}},
        ])
        preflight = {"units": preflight_rows}
        states = {i: SimpleNamespace(usage=i) for i in range(1, 12)}
        canonical = {i: f"JPN_{i:02d}" for i in range(1, 12)}
        calls: list[int] = []

        def fake_score(state, *, contract):
            calls.append(state.usage)
            result = {
                "status": "TEMPORALLY_EVALUABLE",
                "primary_positive": True,
                "recent_provider_audit": {"matched_usage_key": state.usage},
            }
            metric_rows = [
                {"lane_id": "BROAD_LAND", "recovery_radius_km": 1.0, "novel_population_count": 1, "recovered_novel_populations": 1},
                {"lane_id": "LOCAL_5KM_LAND", "recovery_radius_km": 1.0, "novel_population_count": 1, "recovered_novel_populations": 0},
            ]
            return result, metric_rows

        with patch.object(target, "verify_preoutcome_documents", return_value=(contract, amendment, preflight, roster)), \
             patch.object(target, "reconstruct_all_canonical_states", return_value=(states, canonical, {r["unit_id"]: r for r in preflight_rows})), \
             patch.object(target, "fetch_and_score_recent_unit", side_effect=fake_score), \
             patch.object(target, "_sha256", return_value="frozen"):
            summary, metrics, concepts = target.run(Path("unused.json"))

        self.assertEqual(calls, list(range(1, 12)))
        self.assertEqual(len(calls), 11)
        self.assertEqual(summary["primary"]["temporally_evaluable_provider_identities"], 11)
        self.assertTrue(summary["primary"]["all_preregistered_gates_passed"])
        self.assertEqual(len(metrics), 22)
        self.assertEqual(int(concepts["primary_provider_identity_unit"].sum()), 11)
        self.assertEqual(concepts.loc[concepts["member_id"].eq("JPN_12"), "outcome_status"].iloc[0], "ALIAS_OF_JPN_01")
        self.assertEqual(concepts.loc[concepts["member_id"].eq("JPN_13"), "outcome_status"].iloc[0], "ALIAS_OF_JPN_01")


if __name__ == "__main__":
    unittest.main()
