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
                "site_id": ["a", "b", "c"],
                "survey_area_id": ["x", "x", "x"],
                "latitude": [35.000, 35.005, 35.010],
                "longitude": [139.000, 139.005, 139.010],
            })
            matrix = pd.DataFrame({
                "from_id": ["hub", "a", "a", "b", "b", "c", "c", "hub"],
                "to_id": ["a", "hub", "b", "a", "c", "b", "hub", "c"],
                "travel_minutes": [10, 10, 10, 10, 10, 10, 10, 10],
                "mode": ["walk"] * 8,
            })
            candidate_path = root / "candidates.csv"
            matrix_path = root / "matrix.csv"
            output_path = root / "selected.csv"
            summary_path = root / "summary.json"
            frontier_path = root / "frontier.csv"
            candidates.to_csv(candidate_path, index=False)
            matrix.to_csv(matrix_path, index=False)

            code = main([
                "auto-effort",
                "--input", str(candidate_path),
                "--output", str(output_path),
                "--summary-json", str(summary_path),
                "--frontier-audit", str(frontier_path),
                "--travel-matrix", str(matrix_path),
                "--hub-id", "hub",
                "--allowed-mode", "walk",
                "--taxon-profile", "plant",
            ])
            self.assertEqual(code, 0)
            summary = json.loads(summary_path.read_text())
            self.assertFalse(summary["target_days_user_supplied"])
            self.assertFalse(summary["target_site_count_user_supplied"])
            self.assertFalse(summary["survey_budget_user_supplied"])
            self.assertFalse(summary["straight_line_fallback"])
            self.assertEqual(summary["allowed_modes"], ["walk"])
            self.assertEqual(summary["geometry_order_count"], 3)
            self.assertGreaterEqual(summary["automatic_effort"]["recommended_days"], 1)
            self.assertTrue(output_path.is_file())
            self.assertTrue(frontier_path.is_file())


if __name__ == "__main__":
    unittest.main()
