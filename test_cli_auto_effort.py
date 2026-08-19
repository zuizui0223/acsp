import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from acsp.cli import main


class AutoEffortCliTests(unittest.TestCase):
    def test_auto_effort_requires_movement_not_day_or_site_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidates = pd.DataFrame({
                "site_id": ["a", "b", "blocked"],
                "survey_area_id": ["x", "x", "x"],
                "latitude": [35.000, 35.005, 35.010],
                "longitude": [139.000, 139.005, 139.010],
            })
            # a and b are reachable through an intermediate graph; blocked is absent.
            matrix = pd.DataFrame({
                "from_id": ["hub", "junction", "a", "junction", "junction", "b"],
                "to_id": ["junction", "a", "junction", "hub", "b", "junction"],
                "travel_minutes": [5, 5, 5, 5, 6, 6],
                "mode": ["road", "trail", "trail", "road", "walk", "walk"],
            })
            candidate_path = root / "candidates.csv"
            matrix_path = root / "matrix.csv"
            output_path = root / "selected.csv"
            summary_path = root / "summary.json"
            frontier_path = root / "frontier.csv"
            reachability_path = root / "reachability.csv"
            candidates.to_csv(candidate_path, index=False)
            matrix.to_csv(matrix_path, index=False)

            code = main([
                "auto-effort",
                "--input", str(candidate_path),
                "--output", str(output_path),
                "--summary-json", str(summary_path),
                "--frontier-audit", str(frontier_path),
                "--reachability-audit", str(reachability_path),
                "--travel-matrix", str(matrix_path),
                "--hub-id", "hub",
                "--allowed-mode", "walk",
                "--allowed-mode", "road",
                "--allowed-mode", "trail",
                "--taxon-profile", "plant",
            ])
            self.assertEqual(code, 0)
            summary = json.loads(summary_path.read_text())
            self.assertFalse(summary["target_days_user_supplied"])
            self.assertFalse(summary["target_site_count_user_supplied"])
            self.assertFalse(summary["survey_budget_user_supplied"])
            self.assertFalse(summary["straight_line_fallback"])
            self.assertTrue(summary["reachability_applied_before_coverage"])
            self.assertEqual(summary["reachable_candidate_count"], 2)
            self.assertEqual(summary["unreachable_candidate_count"], 1)
            self.assertGreaterEqual(summary["automatic_plan"]["effort"]["recommended_days"], 1)
            self.assertTrue(output_path.is_file())
            self.assertTrue(frontier_path.is_file())
            self.assertTrue(reachability_path.is_file())


if __name__ == "__main__":
    unittest.main()
