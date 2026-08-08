import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import aggregate_sdm_topk_benchmark as aggregate
import run_sdm_topk_pair as runner


class DummyModel:
    def predict_proba(self, X):
        values = np.linspace(0.2, 0.8, len(X))
        return np.column_stack([1.0 - values, values])


class SdmTopKExecutionTests(unittest.TestCase):
    def test_frozen_execution_contract_fingerprint(self):
        self.assertEqual(
            runner._canonical_fingerprint(runner.CONTRACT_PATH, "contract_fingerprint"),
            runner.EXPECTED_CONTRACT,
        )
        self.assertEqual(
            runner._canonical_fingerprint(runner.PROTOCOL_PATH, "protocol_fingerprint"),
            runner.EXPECTED_PROTOCOL,
        )

    def test_production_sdm_scoring_preserves_shared_candidate_ids(self):
        training = pd.DataFrame({
            "_row_id": range(8),
            "_latitude": np.linspace(35.0, 35.7, 8),
            "_longitude": np.linspace(139.0, 139.7, 8),
        })
        candidates = pd.DataFrame({
            "candidate_id": [f"c{i}" for i in range(6)],
            "latitude": np.linspace(35.0, 35.5, 6),
            "longitude": np.linspace(139.0, 139.5, 6),
        })

        def fake_pb(*args, **kwargs):
            return pd.DataFrame({
                "latitude": np.linspace(35.0, 35.9, 10),
                "longitude": np.linspace(139.0, 139.9, 10),
                "presence": [1] * 5 + [0] * 5,
            })

        def fake_extract(points, variables, lat_col, lon_col, resolution, status=None):
            out = points.copy()
            for index, variable in enumerate(variables, start=1):
                out[variable] = np.arange(len(out), dtype=float) + index
            return out

        def fake_clean(table, variables, label, status=None):
            return table.copy(), 0

        fake_model = {
            "models": {name: DummyModel() for name in ("a", "b", "c", "d")},
            "metrics": pd.DataFrame(),
            "variables": list(runner.VARIABLES),
        }

        with (
            patch.object(runner, "spatially_balanced_cap", side_effect=lambda frame, n: frame.copy()),
            patch.object(runner, "auto_remote_spatial_outlier_qc", return_value=(training.copy(), pd.DataFrame(), {})),
            patch.object(runner, "prediction_area_geometry", return_value=None),
            patch.object(runner, "auto_sdm_partition", return_value=("random holdout", "test")),
            patch.object(runner, "build_presence_background", side_effect=fake_pb),
            patch.object(runner, "extract_environment", side_effect=fake_extract),
            patch.object(runner, "clean_environment_table", side_effect=fake_clean),
            patch.object(runner, "select_environment_variables", return_value=(list(runner.VARIABLES), pd.DataFrame())),
            patch.object(runner, "fit_sdm", return_value=fake_model),
        ):
            scored, audit = runner._fit_and_score_production_sdm(training, candidates)

        self.assertEqual(scored["candidate_id"].tolist(), candidates["candidate_id"].tolist())
        self.assertEqual(audit["status"], "sdm_ok")
        self.assertEqual(audit["finite_candidate_scores"], 6)
        self.assertTrue(pd.to_numeric(scored["sdm_suitability"], errors="coerce").notna().all())

    def test_attach_outcomes_scores_sdm_failure_zero_but_other_methods_normally(self):
        candidates = pd.DataFrame({
            "candidate_id": [f"c{i}" for i in range(6)],
            "latitude": [35.0, 35.01, 36.0, 36.01, 37.0, 37.01],
            "longitude": [139.0, 139.01, 140.0, 140.01, 141.0, 141.01],
        })
        heldout = pd.DataFrame({
            "_outer_occurrence_id": ["h1", "h2"],
            "_latitude": [35.0, 36.0],
            "_longitude": [139.0, 140.0],
        })
        decisions = {
            "methods": {
                "frozen_acsp": ["c0", "c2", "c4", "c1", "c3"],
                "local_evidence_top_k": ["c0", "c2", "c4", "c1", "c3"],
                "fitted_sdm_top_k": [],
                "geographic_maximin": ["c0", "c2", "c4", "c1", "c3"],
            },
            "random_same_pool_draws": [["c0", "c2", "c4", "c1", "c3"]],
        }
        state = {
            "method_status": {
                "frozen_acsp": "ok",
                "local_evidence_top_k": "ok",
                "fitted_sdm_top_k": "sdm_failure",
                "geographic_maximin": "ok",
                "random_same_pool_mean": "ok",
                "heldout_greedy_oracle": "shared_candidate_failure",
            },
            "sdm_audit": {"status": "sdm_failure"},
        }
        pair = pd.Series({
            "pair_id": 1,
            "taxon_group": "plant",
            "scientific_name": "Example plant",
            "region_name": "Example region",
        })
        result, oracle = runner.attach_outcomes(
            candidates, heldout, decisions, state, pair, 1, radius_km=10.0
        )
        sdm = result[result["decision_method"].eq("fitted_sdm_top_k")].iloc[0]
        acsp = result[result["decision_method"].eq("frozen_acsp")].iloc[0]
        self.assertEqual(sdm["heldout_recall"], 0.0)
        self.assertEqual(sdm["method_status"], "sdm_failure")
        self.assertEqual(acsp["heldout_recall"], 1.0)
        self.assertTrue(oracle)

    def test_primary_completion_inserts_zero_rows_for_missing_artifacts(self):
        cohort = pd.DataFrame({
            "pair_id": [1, 2],
            "taxon_group": ["plant", "animal"],
            "scientific_name": ["p", "a"],
            "region_name": ["r1", "r2"],
            "geographic_stratum": ["east", "west"],
        })
        raw = pd.DataFrame({
            "pair_id": [1],
            "repeat": [1],
            "decision_method": ["frozen_acsp"],
            "heldout_recall": [0.5],
            "method_status": ["ok"],
            "sdm_fold_ok": [False],
        })
        folds = aggregate._complete_fold_table(raw, cohort, repeats=2)
        self.assertEqual(len(folds), 2 * 2 * len(runner.METHODS))
        missing = folds[
            folds["pair_id"].eq(2)
            & folds["decision_method"].eq("fitted_sdm_top_k")
        ]
        self.assertTrue(missing["heldout_recall"].eq(0).all())
        self.assertTrue(missing["method_status"].eq("artifact_missing").all())

    def test_secondary_estimand_uses_identical_sdm_ok_folds_for_both_methods(self):
        cohort = pd.DataFrame({
            "pair_id": [1],
            "taxon_group": ["plant"],
            "scientific_name": ["p"],
            "region_name": ["r"],
            "geographic_stratum": ["east"],
        })
        rows = []
        for repeat, sdm_status, acsp_value, sdm_value in (
            (1, "ok", 0.8, 0.4),
            (2, "sdm_failure", 1.0, 0.0),
        ):
            for method, value in (
                ("frozen_acsp", acsp_value),
                ("fitted_sdm_top_k", sdm_value),
                ("local_evidence_top_k", acsp_value),
                ("geographic_maximin", 0.2),
                ("random_same_pool_mean", 0.1),
                ("heldout_greedy_oracle", 1.0),
            ):
                rows.append({
                    "pair_id": 1,
                    "repeat": repeat,
                    "decision_method": method,
                    "method_status": sdm_status if method == "fitted_sdm_top_k" else "ok",
                    "heldout_recall": value,
                    "sdm_fold_ok": sdm_status == "ok",
                })
        folds = aggregate._complete_fold_table(pd.DataFrame(rows), cohort, repeats=2)
        secondary = aggregate._sdm_evaluable_pair_table(folds, cohort)
        acsp = secondary[secondary["decision_method"].eq("frozen_acsp")].iloc[0]
        sdm = secondary[secondary["decision_method"].eq("fitted_sdm_top_k")].iloc[0]
        self.assertEqual(acsp["sdm_evaluable_folds"], 1)
        self.assertAlmostEqual(acsp["pair_mean_recall"], 0.8)
        self.assertAlmostEqual(sdm["pair_mean_recall"], 0.4)


if __name__ == "__main__":
    unittest.main()
