import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from acsp.operational_cli import _parser, main


class OperationalCliTests(unittest.TestCase):
    def test_parser_exposes_movement_constraints_without_design_budget_controls(self):
        parser = _parser()
        option_strings = {
            option
            for action in parser._actions
            for option in action.option_strings
        }
        self.assertIn("--max-transition-km", option_strings)
        self.assertIn("--reachability-edges", option_strings)
        self.assertNotIn("--max-sites", option_strings)
        self.assertNotIn("--target-coverage", option_strings)
        self.assertNotIn("--survey-days", option_strings)
        self.assertNotIn("--budget", option_strings)

    def test_exactly_one_movement_constraint_is_required(self):
        parser = _parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--patches", "p.csv", "--output", "o.csv"])
        with self.assertRaises(SystemExit):
            parser.parse_args(
                [
                    "--patches", "p.csv",
                    "--max-transition-km", "2",
                    "--reachability-edges", "e.csv",
                    "--output", "o.csv",
                ]
            )

    def test_geometric_cli_writes_automatic_subset_and_claim_ceiling(self):
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
            self.assertEqual(payload["movement_constraint_mode"], "geometric_transition_proxy")
            self.assertTrue(payload["straight_line_movement_assumption"])
            self.assertTrue(payload["movement_constraint_only"])
            self.assertFalse(payload["user_site_count_required"])
            self.assertFalse(payload["user_coverage_target_required"])
            self.assertFalse(payload["survey_days_input"])
            self.assertFalse(payload["monetary_budget_input"])
            self.assertFalse(payload["route_feasibility_claim"])
            self.assertFalse(payload["field_efficiency_claim"])
            self.assertFalse(payload["validated_candidate_generation_changed"])

    def test_reachability_graph_cli_does_not_use_straight_line_movement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patches = root / "patches.csv"
            edges = root / "edges.csv"
            output = root / "visits.csv"
            summary = root / "summary.json"
            pd.DataFrame(
                {
                    "candidate_patch_id": ["a", "b"],
                    "survey_area_id": ["island-a", "island-b"],
                    "latitude": [35.0, 43.0],
                    "longitude": [139.0, 145.0],
                    "candidate_patch_radius_m": [100.0, 100.0],
                }
            ).to_csv(patches, index=False)
            pd.DataFrame(
                {"from_patch_id": ["a"], "to_patch_id": ["b"]}
            ).to_csv(edges, index=False)

            code = main(
                [
                    "--patches", str(patches),
                    "--reachability-edges", str(edges),
                    "--output", str(output),
                    "--summary-json", str(summary),
                ]
            )
            self.assertEqual(code, 0)
            selected = pd.read_csv(output)
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(selected["candidate_patch_id"].tolist(), ["a", "b"])
            self.assertEqual(payload["automatic_selected_count"], 2)
            self.assertEqual(payload["movement_constraint_mode"], "explicit_reachability_graph")
            self.assertFalse(payload["straight_line_movement_assumption"])
            self.assertEqual(payload["reachability_edge_count"], 1)
            self.assertFalse(payload["route_feasibility_claim"])
            self.assertFalse(payload["field_efficiency_claim"])
            self.assertFalse(payload["validated_candidate_generation_changed"])


if __name__ == "__main__":
    unittest.main()
