import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from acsp.odsp_export import ODSPFoldExportConfig, iter_odsp_folds, write_odsp_fold_exports


class ODSPExportTests(unittest.TestCase):
    def setUp(self):
        self.occurrences = pd.DataFrame({
            "latitude": [34.00, 34.01, 34.20, 34.21, 34.40, 34.41],
            "longitude": [139.00, 139.01, 139.00, 139.01, 139.00, 139.01],
            "source": list("abcdef"),
        })
        self.seen_training_sources = []

    def builder(self, training):
        self.seen_training_sources.append(set(training["source"]))
        return pd.DataFrame({
            "latitude": [34.05, 34.25, 34.45],
            "longitude": [139.0, 139.0, 139.0],
            "integrated_support_score": [0.9, 0.8, 0.7],
        })

    def test_training_only_split_and_explicit_coordinates(self):
        cfg = ODSPFoldExportConfig(block_degrees=0.1, repeats=2, holdout_fraction=0.34, random_state=7)
        folds = list(iter_odsp_folds(self.occurrences, self.builder, config=cfg))
        self.assertEqual(len(folds), 2)
        for _, training, heldout, candidates, manifest in folds:
            self.assertFalse(training.empty)
            self.assertFalse(heldout.empty)
            self.assertEqual(set(candidates.columns), {"latitude", "longitude", "candidate_support", "repeat"})
            held_sources = set(self.occurrences.loc[self.occurrences.index.isin(heldout.occurrence_id), "source"])
            self.assertTrue(held_sources.isdisjoint(self.seen_training_sources[manifest["repeat"] - 1]))
            self.assertEqual(manifest["status"], "ready")

    def test_writer_creates_checksum_manifest(self):
        cfg = ODSPFoldExportConfig(block_degrees=0.1, repeats=1, holdout_fraction=0.34, random_state=7)
        with tempfile.TemporaryDirectory() as tmp:
            summary = write_odsp_fold_exports(self.occurrences, self.builder, tmp, config=cfg, provenance={"pair_id": 1})
            self.assertEqual(summary.status.tolist(), ["ready"])
            fold = Path(tmp) / "fold_001"
            for name in ("training_occurrences.csv", "held_out_occurrences.csv", "candidate_support.csv", "fold_manifest.json"):
                self.assertTrue((fold / name).exists())
            manifest = json.loads((fold / "fold_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["provenance"]["pair_id"], 1)
            self.assertEqual(len(manifest["files"]["candidate_support"]["sha256"]), 64)

    def test_missing_support_is_audited(self):
        def bad_builder(training):
            return pd.DataFrame({"latitude": [34.1], "longitude": [139.0]})
        cfg = ODSPFoldExportConfig(block_degrees=0.1, repeats=1, holdout_fraction=0.34, random_state=7)
        fold = next(iter_odsp_folds(self.occurrences, bad_builder, config=cfg))
        self.assertEqual(fold[4]["status"], "no_candidate_support")
        self.assertIn("integrated_support_score", fold[4]["candidate_missing_columns"])


if __name__ == "__main__":
    unittest.main()
