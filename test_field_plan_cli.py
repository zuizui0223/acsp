import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from acsp.field_plan_cli import _parser, main


def _validated_patches() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "candidate_patch_id": ["a", "b", "c"],
            "survey_area_id": ["izu", "izu", "izu"],
            "latitude": [35.0, 35.0, 35.0],
            "longitude": [139.000, 139.005, 139.010],
            "candidate_patch_radius_m": [100.0, 100.0, 100.0],
            "validation_region_id": ["izu", "izu", "izu"],
        }
    )


def _successful_osm_result():
    patch_edges = pd.DataFrame(
        {
            "from_patch_id": ["a", "b"],
            "to_patch_id": ["b", "c"],
        }
    )
    attachments = pd.DataFrame(
        {
            "candidate_patch_id": ["a", "b", "c"],
            "network_node_id": ["n1", "n2", "n3"],
            "off_network_access_distance_m": [0.0, 0.0, 0.0],
            "network_attached": [True, True, True],
        }
    )
    network_nodes = pd.DataFrame(
        {
            "network_node_id": ["n1", "n2", "n3"],
            "survey_area_id": ["izu", "izu", "izu"],
            "latitude": [35.0, 35.0, 35.0],
            "longitude": [139.000, 139.005, 139.010],
        }
    )
    network_edges = pd.DataFrame(
        {
            "from_node_id": ["n1", "n2"],
            "to_node_id": ["n2", "n3"],
            "distance_m": [500.0, 500.0],
        }
    )
    area_audit = pd.DataFrame(
        {"survey_area_id": ["izu"], "status": ["success"]}
    )
    osm_audit = {
        "movement_constraint_mode": "osm_weighted_transport_network",
        "max_network_transition_km": 5.0,
        "query_margin_derived_from_movement_limit": True,
        "candidate_pair_straight_line_used": False,
        "straight_line_candidate_fallback": False,
        "ferry_edges_included": False,
        "ferry_relation_only_support": True,
        "route_time_claim": False,
        "timetable_claim": False,
        "legal_access_claim": False,
        "safety_claim": False,
        "field_efficiency_claim": False,
        "provider": {"successful_area_count": 1, "failed_area_count": 0},
        "ferry_provider": {"failed_query_count": 0},
        "reachability": {},
    }
    return patch_edges, attachments, network_nodes, network_edges, area_audit, osm_audit


def _argv(root: Path) -> list[str]:
    return [
        "--taxon", "Example species",
        "--osm-network-transition-km", "5",
        "--patches-output", str(root / "patches.csv"),
        "--visits-output", str(root / "visits.csv"),
        "--summary-json", str(root / "summary.json"),
    ]


class FieldPlanCliTests(unittest.TestCase):
    def test_parser_has_species_and_one_movement_limit_without_design_budget_controls(self):
        parser = _parser()
        option_strings = {
            option
            for action in parser._actions
            for option in action.option_strings
        }
        self.assertIn("--taxon", option_strings)
        self.assertIn("--osm-network-transition-km", option_strings)
        self.assertNotIn("--max-sites", option_strings)
        self.assertNotIn("--top-k", option_strings)
        self.assertNotIn("--target-coverage", option_strings)
        self.assertNotIn("--survey-days", option_strings)
        self.assertNotIn("--budget", option_strings)

    def test_validated_patch_artifact_is_preserved_before_operational_subset(self):
        patches = _validated_patches()
        discovery_audit = {
            "input_mode": "taxon_japan_validated_regions",
            "candidate_patch_count": 3,
            "candidate_generation_only": True,
            "routing_or_budget_optimization": False,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patches_output = root / "patches.csv"
            visits_output = root / "visits.csv"
            summary_output = root / "summary.json"
            with patch(
                "acsp.field_plan_cli.discover_validated_candidate_patches_japan",
                return_value=(patches.copy(), discovery_audit),
            ) as discover, patch(
                "acsp.field_plan_cli.build_osm_patch_reachability_edges",
                return_value=_successful_osm_result(),
            ) as osm:
                code = main(_argv(root))

            self.assertEqual(code, 0)
            discover.assert_called_once_with("Example species")
            self.assertEqual(osm.call_args.kwargs["max_network_transition_km"], 5.0)
            persisted_patches = pd.read_csv(patches_output)
            pd.testing.assert_frame_equal(
                persisted_patches,
                patches,
                check_dtype=False,
            )
            visits = pd.read_csv(visits_output)
            # This wrapper test checks artifact separation, not the selector's
            # separately tested exact tie-break identity.
            self.assertEqual(len(visits), 1)
            self.assertTrue(
                set(visits["candidate_patch_id"]).issubset(set(persisted_patches["candidate_patch_id"]))
            )

            payload = json.loads(summary_output.read_text(encoding="utf-8"))
            validated = payload["validated_candidate_product"]
            operational = payload["downstream_operational_selection"]
            boundary = payload["artifact_boundary"]
            self.assertIsNone(payload["failed_stage"])
            self.assertEqual(validated["candidate_patch_count"], 3)
            self.assertTrue(validated["non_ranked"])
            self.assertFalse(validated["routing_or_budget_optimization"])
            self.assertEqual(operational["automatic_selected_count"], 1)
            self.assertEqual(operational["movement_constraint_mode"], "osm_weighted_transport_network")
            self.assertFalse(operational["straight_line_movement_assumption"])
            self.assertFalse(operational["user_site_count_required"])
            self.assertFalse(operational["user_coverage_target_required"])
            self.assertFalse(operational["survey_days_input"])
            self.assertFalse(operational["monetary_budget_input"])
            self.assertFalse(operational["field_efficiency_claim"])
            self.assertFalse(operational["validated_candidate_membership_changed"])
            self.assertTrue(boundary["candidate_patches_written_before_operations"])
            self.assertFalse(boundary["candidate_patch_artifact_filtered_by_operations"])
            self.assertTrue(boundary["operational_output_is_separate_artifact"])
            self.assertTrue(boundary["operational_visits_written"])

    def test_provider_failure_conservatively_keeps_isolated_patches(self):
        patches = _validated_patches().iloc[:2].copy().reset_index(drop=True)
        empty_edges = pd.DataFrame(columns=["from_patch_id", "to_patch_id"])
        attachments = pd.DataFrame(
            {
                "candidate_patch_id": patches["candidate_patch_id"],
                "network_node_id": pd.array([pd.NA, pd.NA], dtype="string"),
                "off_network_access_distance_m": [float("nan"), float("nan")],
                "network_attached": [False, False],
            }
        )
        nodes = pd.DataFrame(columns=["network_node_id", "survey_area_id", "latitude", "longitude"])
        network_edges = pd.DataFrame(columns=["from_node_id", "to_node_id", "distance_m"])
        area_audit = pd.DataFrame(
            {"survey_area_id": ["izu"], "status": ["failed"], "error": ["offline"]}
        )
        osm_audit = {
            "movement_constraint_mode": "osm_weighted_transport_network",
            "straight_line_candidate_fallback": False,
            "provider": {"successful_area_count": 0, "failed_area_count": 1},
            "ferry_provider": {"failed_query_count": 1},
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch(
                "acsp.field_plan_cli.discover_validated_candidate_patches_japan",
                return_value=(patches.copy(), {"candidate_patch_count": 2}),
            ), patch(
                "acsp.field_plan_cli.build_osm_patch_reachability_edges",
                return_value=(empty_edges, attachments, nodes, network_edges, area_audit, osm_audit),
            ):
                main(_argv(root))
            visits = pd.read_csv(root / "visits.csv")
            self.assertEqual(visits["candidate_patch_id"].tolist(), ["a", "b"])
            payload = json.loads((root / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["validated_candidate_product"]["candidate_patch_count"], 2)
            self.assertEqual(
                payload["downstream_operational_selection"]["automatic_selected_count"], 2
            )
            self.assertEqual(
                payload["downstream_operational_selection"]["osm_audit"]["provider"]["failed_area_count"],
                1,
            )

    def test_candidate_generation_failure_writes_stage_summary_without_patch_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch(
                "acsp.field_plan_cli.discover_validated_candidate_patches_japan",
                side_effect=RuntimeError("GBIF unavailable"),
            ):
                with self.assertRaisesRegex(RuntimeError, "GBIF unavailable"):
                    main(_argv(root))

            self.assertFalse((root / "patches.csv").exists())
            self.assertFalse((root / "visits.csv").exists())
            payload = json.loads((root / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "field_plan_failed")
            self.assertEqual(payload["failed_stage"], "candidate_generation")
            self.assertEqual(payload["error"]["type"], "RuntimeError")
            self.assertFalse(
                payload["artifact_boundary"]["candidate_patches_written_before_operations"]
            )

    def test_osm_failure_retains_complete_validated_patch_artifact_and_reports_stage(self):
        patches = _validated_patches()
        discovery_audit = {"candidate_patch_count": 3, "candidate_generation_only": True}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch(
                "acsp.field_plan_cli.discover_validated_candidate_patches_japan",
                return_value=(patches.copy(), discovery_audit),
            ), patch(
                "acsp.field_plan_cli.build_osm_patch_reachability_edges",
                side_effect=RuntimeError("Overpass unavailable"),
            ):
                with self.assertRaisesRegex(RuntimeError, "Overpass unavailable"):
                    main(_argv(root))

            persisted = pd.read_csv(root / "patches.csv")
            pd.testing.assert_frame_equal(persisted, patches, check_dtype=False)
            self.assertFalse((root / "visits.csv").exists())
            payload = json.loads((root / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["failed_stage"], "osm_network_provider")
            self.assertEqual(payload["validated_candidate_product"]["candidate_patch_count"], 3)
            self.assertTrue(
                payload["artifact_boundary"]["candidate_patches_written_before_operations"]
            )
            self.assertFalse(payload["artifact_boundary"]["operational_visits_written"])
            self.assertFalse(
                payload["downstream_operational_selection"]["straight_line_movement_assumption"]
            )

    def test_selection_failure_retains_validated_artifact_and_reports_operational_stage(self):
        patches = _validated_patches()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch(
                "acsp.field_plan_cli.discover_validated_candidate_patches_japan",
                return_value=(patches.copy(), {"candidate_patch_count": 3}),
            ), patch(
                "acsp.field_plan_cli.build_osm_patch_reachability_edges",
                return_value=_successful_osm_result(),
            ), patch(
                "acsp.field_plan_cli.select_reachability_constrained_patches",
                side_effect=RuntimeError("selector failed"),
            ):
                with self.assertRaisesRegex(RuntimeError, "selector failed"):
                    main(_argv(root))

            persisted = pd.read_csv(root / "patches.csv")
            pd.testing.assert_frame_equal(persisted, patches, check_dtype=False)
            self.assertFalse((root / "visits.csv").exists())
            payload = json.loads((root / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["failed_stage"], "operational_selection")
            self.assertEqual(
                payload["downstream_operational_selection"]["status"],
                "operational_selection_failed",
            )
            self.assertTrue(
                payload["artifact_boundary"]["candidate_patches_written_before_operations"]
            )
            self.assertFalse(payload["artifact_boundary"]["operational_visits_written"])


if __name__ == "__main__":
    unittest.main()
