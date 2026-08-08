import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from summarize_sdm_decision_differences import describe_fold, run


class SdmDecisionDifferenceTests(unittest.TestCase):
    def _write_pair(self, root: Path) -> Path:
        pair = root / "pair_001"
        fold = pair / "fold_001"
        fold.mkdir(parents=True)
        (pair / "pair_manifest.json").write_text(
            json.dumps({
                "pair_id": 1,
                "taxon_group": "plant",
                "scientific_name": "Example plant",
                "region_name": "Example region",
            }),
            encoding="utf-8",
        )
        pd.DataFrame({
            "candidate_id": ["a", "b", "c", "d", "e", "f"],
            "latitude": [35.0, 35.1, 35.2, 35.3, 35.4, 35.5],
            "longitude": [139.0, 139.1, 139.2, 139.3, 139.4, 139.5],
            "component_local_habitat_score": [0.95, 0.9, 0.85, 0.4, 0.3, 0.2],
            "sdm_suitability": [0.2, 0.3, 0.4, 0.95, 0.9, 0.85],
        }).to_csv(fold / "candidate_pool_pre_outcome.csv", index=False)
        (fold / "decision_sets.json").write_text(
            json.dumps({
                "methods": {
                    "frozen_acsp": ["a", "b", "c", "d", "e"],
                    "fitted_sdm_top_k": ["b", "c", "d", "e", "f"],
                }
            }),
            encoding="utf-8",
        )
        pd.DataFrame({
            "decision_method": ["frozen_acsp", "fitted_sdm_top_k"],
            "method_status": ["ok", "ok"],
            # Deliberately include an outcome-like column to ensure the diagnostics
            # do not require or inspect it.
            "heldout_recall": [0.9, 0.1],
        }).to_csv(fold / "fold_result.csv", index=False)
        return pair

    def test_describe_fold_reports_set_overlap_and_score_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pair = self._write_pair(root)
            row = describe_fold(pair, pair / "fold_001")
            self.assertEqual(row["shared_count"], 4)
            self.assertAlmostEqual(row["jaccard_overlap"], 4 / 6)
            self.assertFalse(row["exact_set_match"])
            self.assertLess(row["local_sdm_rank_spearman"], 0)
            self.assertGreater(row["acsp_mean_local_evidence"], row["sdm_mean_local_evidence"])
            self.assertLess(row["acsp_mean_sdm_suitability"], row["sdm_mean_sdm_suitability"])

    def test_run_writes_descriptive_outputs_without_outcome_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pair_root = root / "pairs"
            pair_root.mkdir()
            self._write_pair(pair_root)
            output = root / "out"
            manifest = run(pair_root, output)
            self.assertEqual(manifest["pair_artifacts_seen"], 1)
            self.assertEqual(manifest["sdm_evaluable_folds"], 1)
            self.assertTrue((output / "fold_decision_differences.csv").exists())
            self.assertTrue((output / "pair_decision_differences.csv").exists())
            self.assertTrue((output / "decision_difference_summary.csv").exists())
            folds = pd.read_csv(output / "fold_decision_differences.csv")
            self.assertNotIn("heldout_recall", folds.columns)


if __name__ == "__main__":
    unittest.main()
