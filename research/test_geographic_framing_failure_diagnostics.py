import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from diagnose_geographic_framing_v1_failures import diagnose_fold


class GeographicFramingFailureDiagnosticTests(unittest.TestCase):
    def test_misses_distinguish_supported_gap_from_heldout_only_component(self):
        with tempfile.TemporaryDirectory() as tmp:
            fold = Path(tmp) / "pair_001" / "fold_001"
            fold.mkdir(parents=True)
            manifest = {
                "pair_id": 1,
                "repeat": 1,
                "status": "ready",
                "failure_reason": "",
                "provenance": {
                    "pair_id": 1,
                    "scientific_name": "Synthetic taxon",
                    "taxon_group": "animal",
                    "region_name": "Synthetic region",
                    "west": 138.0,
                    "south": 34.0,
                    "east": 143.0,
                    "north": 39.0,
                },
            }
            (fold / "fold_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            pd.DataFrame(
                {
                    "latitude": [35.01, 35.11],
                    "longitude": [139.01, 139.11],
                }
            ).to_csv(fold / "training_occurrences.csv", index=False)
            # 35.21 bridges the training component to 35.31 in the full block
            # graph; 38/142 is a genuinely heldout-only component.
            pd.DataFrame(
                {
                    "latitude": [35.21, 35.31, 38.01],
                    "longitude": [139.21, 139.31, 142.01],
                }
            ).to_csv(fold / "held_out_occurrences.csv", index=False)

            row = diagnose_fold(fold)
            self.assertEqual(row["status"], "evaluated")
            self.assertEqual(row["heldout_records"], 3)
            self.assertGreaterEqual(row["v1_missed_records"], 2)
            self.assertGreaterEqual(row["missed_training_supported_component"], 1)
            self.assertGreaterEqual(row["missed_heldout_only_component"], 1)
            self.assertGreaterEqual(row["bbox_10km_containment"], 0.0)
            self.assertLessEqual(row["bbox_10km_containment"], 1.0)

    def test_upstream_failure_is_retained_without_reclassification(self):
        with tempfile.TemporaryDirectory() as tmp:
            fold = Path(tmp) / "pair_001" / "fold_001"
            fold.mkdir(parents=True)
            manifest = {
                "pair_id": 1,
                "repeat": 1,
                "status": "failed_placeholder",
                "failure_reason": "synthetic upstream failure",
                "provenance": {
                    "pair_id": 1,
                    "scientific_name": "Synthetic taxon",
                    "taxon_group": "plant",
                    "region_name": "Synthetic region",
                    "west": 138.0,
                    "south": 34.0,
                    "east": 143.0,
                    "north": 39.0,
                },
            }
            (fold / "fold_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            row = diagnose_fold(fold)
            self.assertEqual(row["status"], "upstream_failed_retained_as_zero")
            self.assertEqual(row["bbox_10km_containment"], 0.0)
            self.assertIn("synthetic upstream failure", row["failure_reason"])


if __name__ == "__main__":
    unittest.main()
