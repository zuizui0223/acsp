import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from acsp.operational_cli import _parser, main


class OperationalCliTests(unittest.TestCase):
    def test_parser_exposes_movement_constraint_without_design_budget_controls(self):
        parser = _parser()
        option_strings = {
            option
            for action in parser._actions
            for option in action.option_strings
        }
        self.assertIn("--max-transition-km", option_strings)
        self.assertNotIn("--max-sites", option_strings)
        self.assertNotIn("--target-coverage", option_strings)
        self.assertNotIn("--survey-days", option_strings)
        self.assertNotIn("--budget", option_strings)

    def test_cli_writes_automatic_subset_and_explicit_claim_ceiling(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patches = root / "patches.csv"
            output = root / "visits.csv"
            summary = root / "summary.json"
            pd.DataFrame(
                {
                    "candidate_patch_id": ["a", "b", "c"],
                    "survey_area_id": ["island"] * 3,
                    "latitude": [0.0, 0.0, 0.0],
                    "longitude": [0.000, 0.005, 0.010],
                    "candidate_patch_radius_m": [100.0] * 3,
                }
            ).to_csv(patches, index=False)

            code = main(
                [
                    "--patches", str(patches),
                    "--max-transition-km", "2",
                    "--output", str(output),
                    "--summary-json", str(summary),
                ]
            )
            self.assertEqual(code, 0)
            selected = pd.read_csv(output)
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(len(selected), 1)
            self.assertEqual(payload["automatic_selected_count"], 1)
            self.assertTrue(payload["movement_constraint_only"])
            self.assertFalse(payload["user_site_count_required"])
            self.assertFalse(payload["user_coverage_target_required"])
            self.assertFalse(payload["survey_days_input"])
            self.assertFalse(payload["monetary_budget_input"])
            self.assertFalse(payload["route_feasibility_claim"])
            self.assertFalse(payload["field_efficiency_claim"])
            self.assertFalse(payload["validated_candidate_generation_changed"])


if __name__ == "__main__":
    unittest.main()
