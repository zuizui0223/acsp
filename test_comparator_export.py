import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from acsp.comparator_benchmark import StandardBaselineProtocol
from acsp.comparator_export import write_comparator_pair_export


class ComparatorExportTests(unittest.TestCase):
    def test_export_is_explicit_checksummed_and_training_only(self):
        occurrences = pd.DataFrame({
            "latitude": [0.01, 0.02, 0.21, 0.22, 0.41, 0.42],
            "longitude": [0.01, 0.02, 0.21, 0.22, 0.41, 0.42],
            "source_record": [f"o{i}" for i in range(6)],
        })
        seen_training_tables = []

        def builder(training):
            self.assertNotIn("occurrence_id", training.columns)
            self.assertNotIn("spatial_block", training.columns)
            seen_training_tables.append(training.copy())
            return pd.DataFrame({
                "candidate_type": ["habitat", "habitat", "known-location"],
                "latitude": [0.05, 0.25, 0.45],
                "longitude": [0.05, 0.25, 0.45],
                "analogue_score": [0.9, 0.8, 1.0],
                "elevation": [10, 20, 30],
                "slope": [1, 2, 3],
                "aspect": [359, 180, 90],
                "roughness": [0.1, 0.2, 0.3],
                "tpi": [-1.0, 0.0, 1.0],
            })

        protocol = StandardBaselineProtocol(
            repeats=2,
            random_draws=5,
            bootstrap_draws=20,
            sign_flip_draws=20,
            random_state=11,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            status = write_comparator_pair_export(
                occurrences,
                builder,
                root,
                protocol,
                pair_id=7,
                provenance={"taxon_group": "plant"},
            )
            self.assertEqual(len(seen_training_tables), 2)
            self.assertEqual(len(status), 2)
            self.assertTrue(status["status"].eq("ready").all())
            for repeat in (1, 2):
                fold = root / f"fold_{repeat:03d}"
                manifest = json.loads((fold / "fold_manifest.json").read_text())
                self.assertIn("heldout_blocks", manifest)
                self.assertTrue(manifest["environmentally_eligible"])
                candidates = pd.read_csv(fold / "candidates.csv")
                self.assertEqual(len(candidates), 2)
                self.assertNotIn("known-location", set(candidates["candidate_type"]))
                self.assertIn("covered_heldout_ids", candidates.columns)
                for name, metadata in manifest["files"].items():
                    path = fold / metadata["path"]
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    self.assertEqual(digest, metadata["sha256"], name)
            pair_manifest = json.loads((root / "pair_manifest.json").read_text())
            self.assertEqual(pair_manifest["expected_folds"], 2)
            self.assertEqual(pair_manifest["written_folds"], 2)


if __name__ == "__main__":
    unittest.main()
