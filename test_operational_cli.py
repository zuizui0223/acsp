import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

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
        self.assertIn("--osm-network-transition-km", option_strings)
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
        with self.assertRaises(SystemExit):
            parser.parse_args(
                [
                    "--patches", "p.csv",
                    "--max-transition-km", "2",
                    "--osm-network-transition-km", "2",
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

    def test_osm_cli_uses_network_pipeline_and_exposes_provider_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patches_path = root / "patches.csv"
            output = root / "visits.csv"
            summary = root / "summary.json"
            patches = pd.DataFrame(
                {
                    "candidate_patch_id": ["a", "b"],
                    "survey_area_id": ["A", "A"],
                    "latitude": [35.0, 35.0],
                    "longitude": [139.0, 139.02],
                    "candidate_patch_radius_m": [100.0, 100.0],
                }
            )
            patches.to_csv(patches_path, index=False)
            patch_edges = pd.DataFrame(
                {"from_patch_id": ["a"], "to_patch_id": ["b"]}
            )
            attachments = pd.DataFrame(
                {
                    "candidate_patch_id": ["a", "b"],
                    "network_node_id": ["n1", "n2"],
                    "off_network_access_distance_m": [0.0, 0.0],
                    "network_attached": [True, True],
                }
            )
            network_nodes = pd.DataFrame(
                {
                    "network_node_id": ["n1", "n2"],
                    "survey_area_id": ["A", "A"],
                    "latitude": [35.0, 35.0],
                    "longitude": [139.0, 139.02],
                }
            )
            network_edges = pd.DataFrame(
                {"from_node_id": ["n1"], "to_node_id": ["n2"], "distance_m": [900.0]}
            )
            area_audit = pd.DataFrame(
                {"survey_area_id": ["A"], "status": ["success"]}
            )
            osm_audit = {
                "movement_constraint_mode": "osm_weighted_transport_network",
                "max_network_transition_km": 5.0,
                "query_margin_derived_from_movement_limit": True,
                "candidate_pair_straight_line_used": False,
                "straight_line_candidate_fallback": False,
                "ferry_edges_included": False,
                "route_time_claim": False,
                "legal_access_claim": False,
                "safety_claim": False,
                "field_efficiency_claim": False,
                "provider": {
                    "successful_area_count": 1,
                    "failed_area_count": 0,
                },
                "reachability": {},
            }
            with patch(
                "acsp.operational_cli.build_osm_patch_reachability_edges",
                return_value=(
                    patch_edges,
                    attachments,
                    network_nodes,
                    network_edges,
                    area_audit,
                    osm_audit,
                ),
            ) as build:
                code = main(
                    [
                        "--patches", str(patches_path),
                        "--osm-network-transition-km", "5",
                        "--output", str(output),
                        "--summary-json", str(summary),
                    ]
                )

            self.assertEqual(code, 0)
            self.assertEqual(build.call_args.kwargs["max_network_transition_km"], 5.0)
            payload = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(payload["movement_constraint_mode"], "osm_weighted_transport_network")
            self.assertFalse(payload["straight_line_movement_assumption"])
            self.assertEqual(payload["provider_successful_area_count"], 1)
            self.assertEqual(payload["provider_failed_area_count"], 0)
            self.assertFalse(payload["ferry_edges_included"])
            self.assertFalse(payload["route_feasibility_claim"])
            self.assertFalse(payload["field_efficiency_claim"])
            self.assertFalse(payload["validated_candidate_generation_changed"])


if __name__ == "__main__":
    unittest.main()
