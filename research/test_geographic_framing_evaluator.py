import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from evaluate_geographic_framing_development_v1 import (
    _snapshot_fingerprint,
    evaluate_fold,
)


class GeographicFramingEvaluatorTests(unittest.TestCase):
    def _fold(self, root: Path, *, ready: bool = True) -> Path:
        fold = root / "pair_001" / "fold_001"
        fold.mkdir(parents=True)
        manifest = {
            "pair_id": 1,
            "repeat": 1,
            "status": "ready" if ready else "failed_placeholder",
            "failure_reason": "" if ready else "synthetic upstream failure",
            "provenance": {
                "pair_id": 1,
                "scientific_name": "Synthetic taxon",
                "taxon_group": "plant",
                "region_name": "Synthetic region",
                "geographic_stratum": "east",
                "west": 138.5,
                "south": 34.5,
                "east": 140.5,
                "north": 36.5,
            },
        }
        (fold / "fold_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        training = pd.DataFrame(
            {
                "latitude": [35.01, 35.02, 35.11, 35.12],
                "longitude": [139.01, 139.02, 139.11, 139.12],
            }
        )
        heldout = pd.DataFrame(
            {
                "latitude": [35.05, 35.15, 36.20],
                "longitude": [139.05, 139.15, 141.20],
            }
        )
        training.to_csv(fold / "training_occurrences.csv", index=False)
        heldout.to_csv(fold / "held_out_occurrences.csv", index=False)
        return fold

    def test_ready_fold_reports_partial_containment_without_candidate_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            fold = self._fold(Path(tmp), ready=True)
            row = evaluate_fold(fold)
            self.assertEqual(row["framing_status"], "evaluated")
            self.assertEqual(row["heldout_records"], 3)
            self.assertEqual(row["heldout_inside_frames"], 2)
            self.assertAlmostEqual(row["heldout_frame_containment"], 2 / 3)
            self.assertGreater(row["frame_count"], 0)
            self.assertGreater(row["frame_area_ratio_to_fixed"], 0.0)
            self.assertLess(row["frame_area_ratio_to_fixed"], 1.0)

    def test_failed_placeholder_is_retained_as_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            fold = self._fold(Path(tmp), ready=False)
            row = evaluate_fold(fold)
            self.assertEqual(row["framing_status"], "failed_retained_as_zero")
            self.assertEqual(row["heldout_frame_containment"], 0.0)
            self.assertIn("synthetic upstream failure", row["failure_reason"])

    def test_snapshot_fingerprint_changes_when_fold_occurrences_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            fold = self._fold(Path(tmp), ready=True)
            first = _snapshot_fingerprint([fold])
            training = pd.read_csv(fold / "training_occurrences.csv")
            training.loc[0, "latitude"] += 0.001
            training.to_csv(fold / "training_occurrences.csv", index=False)
            second = _snapshot_fingerprint([fold])
            self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
