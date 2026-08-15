import unittest

import numpy as np
import pandas as pd

from recover_sdm_topk_pair import (
    is_empty_shared_candidate_fold,
    prepare_sdm_scoring_input,
    update_sdm_fold_result,
)


class SdmTopKRecoveryTests(unittest.TestCase):
    def test_empty_placeholder_is_removed_without_changing_candidate_rows(self):
        candidates = pd.DataFrame({
            "candidate_id": ["a", "b", "c"],
            "latitude": [35.0, 35.1, 35.2],
            "longitude": [139.0, 139.1, 139.2],
            "sdm_suitability": [np.nan, np.nan, np.nan],
            "component_local_habitat_score": [0.9, 0.8, 0.7],
        })
        prepared = prepare_sdm_scoring_input(candidates)
        self.assertNotIn("sdm_suitability", prepared.columns)
        self.assertEqual(prepared["candidate_id"].tolist(), ["a", "b", "c"])
        self.assertEqual(
            prepared["component_local_habitat_score"].tolist(),
            candidates["component_local_habitat_score"].tolist(),
        )

    def test_nonmissing_source_sdm_score_is_rejected(self):
        candidates = pd.DataFrame({"candidate_id": ["a"], "sdm_suitability": [0.5]})
        with self.assertRaisesRegex(ValueError, "already contains non-missing"):
            prepare_sdm_scoring_input(candidates)

    def test_empty_shared_candidate_fold_is_preserved(self):
        candidates = pd.DataFrame({"candidate_id": pd.Series(dtype=str)})
        fold_result = pd.DataFrame({"candidate_pool": [0, 0, 0, 0, 0, 0]})
        self.assertTrue(is_empty_shared_candidate_fold(candidates, fold_result))

    def test_empty_candidate_artifact_with_nonzero_pool_is_rejected(self):
        candidates = pd.DataFrame({"candidate_id": pd.Series(dtype=str)})
        fold_result = pd.DataFrame({"candidate_pool": [5, 5, 5, 5, 5, 5]})
        with self.assertRaisesRegex(ValueError, "conflicts with non-zero"):
            is_empty_shared_candidate_fold(candidates, fold_result)

    def test_only_fitted_sdm_recall_is_changed(self):
        original = pd.DataFrame({
            "decision_method": [
                "frozen_acsp",
                "local_evidence_top_k",
                "fitted_sdm_top_k",
                "geographic_maximin",
                "random_same_pool_mean",
                "heldout_greedy_oracle",
            ],
            "method_status": ["ok", "ok", "sdm_failure", "ok", "ok", "ok"],
            "heldout_recall": [0.4, 0.5, 0.0, 0.2, 0.1, 0.8],
            "sdm_fold_ok": [False] * 6,
            "selected_ids": ["a", "b", "", "c", "", "d"],
        })
        recovered = update_sdm_fold_result(
            original,
            status="ok",
            recall=0.3,
            selected_ids=["x", "y"],
        )
        other = recovered[~recovered["decision_method"].eq("fitted_sdm_top_k")]
        expected = original[~original["decision_method"].eq("fitted_sdm_top_k")]
        self.assertEqual(other["heldout_recall"].tolist(), expected["heldout_recall"].tolist())
        sdm = recovered[recovered["decision_method"].eq("fitted_sdm_top_k")].iloc[0]
        self.assertEqual(sdm["method_status"], "ok")
        self.assertAlmostEqual(sdm["heldout_recall"], 0.3)
        self.assertEqual(sdm["selected_ids"], "x;y")
        self.assertTrue(recovered["sdm_fold_ok"].all())

    def test_genuine_sdm_failure_serializes_empty_selection_from_float_csv_dtype(self):
        original = pd.DataFrame({
            "decision_method": [
                "frozen_acsp",
                "local_evidence_top_k",
                "fitted_sdm_top_k",
                "geographic_maximin",
                "random_same_pool_mean",
                "heldout_greedy_oracle",
            ],
            "method_status": ["ok", "ok", "sdm_failure", "ok", "ok", "ok"],
            "heldout_recall": [0.4, 0.5, 0.0, 0.2, 0.1, 0.8],
            "sdm_fold_ok": [False] * 6,
            # Mimics pandas reading an all-empty CSV column as float64 NaN.
            "selected_ids": [np.nan] * 6,
        })
        recovered = update_sdm_fold_result(
            original,
            status="sdm_failure_after_recovery",
            recall=0.0,
            selected_ids=[],
        )
        sdm = recovered[recovered["decision_method"].eq("fitted_sdm_top_k")].iloc[0]
        self.assertEqual(sdm["method_status"], "sdm_failure_after_recovery")
        self.assertEqual(sdm["selected_ids"], "")
        self.assertFalse(recovered["sdm_fold_ok"].any())


if __name__ == "__main__":
    unittest.main()
