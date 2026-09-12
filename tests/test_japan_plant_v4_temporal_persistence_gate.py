from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

import develop_japan_plant_v4_temporal_persistence_gate as d


class JapanPlantV4TemporalPersistenceGateTests(unittest.TestCase):
    def test_frozen_development_cohort_is_exactly_24_with_six_evaluable(self):
        cohort = d.load_cohort()
        self.assertEqual(len(cohort), 24)
        self.assertEqual(cohort["speciesKey"].nunique(), 24)
        self.assertEqual(int(cohort["terminal_temporally_evaluable"].sum()), 6)

    def test_summary_uses_only_single_binary_gate(self):
        table = pd.DataFrame(
            {
                "recent_historical_persistence_gate_pass": [True, True, False, False],
                "terminal_temporally_evaluable": [True, False, True, False],
                "historical_reconstruction_matches_frozen": [True, True, True, True],
            }
        )
        summary = d.summarize(table)
        self.assertEqual(summary["two_by_two"], {
            "true_positive": 1,
            "false_positive": 1,
            "false_negative": 1,
            "true_negative": 1,
        })
        self.assertAlmostEqual(summary["evaluable_retention_sensitivity"], 0.5)
        self.assertAlmostEqual(summary["evaluable_fraction_among_gate_pass_ppv"], 0.5)
        self.assertFalse(summary["threshold_search_performed"])
        self.assertFalse(summary["candidate_frames_rescored"])


if __name__ == "__main__":
    unittest.main()
