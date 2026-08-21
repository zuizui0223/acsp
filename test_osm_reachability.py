import inspect
import unittest
from unittest.mock import patch

import pandas as pd

from acsp.osm_ferry import OsmFerryProviderAudit
from acsp.osm_reachability import build_osm_patch_reachability_edges
from acsp.osm_transport import OsmTransportProviderAudit


def _empty_ferry_result():
    edges = pd.DataFrame(
        columns=[
            "from_node_id", "to_node_id", "distance_m", "survey_area_id",
            "network_mode", "highway", "osm_way_id", "network_source",
            "ferry_name", "ferry_access", "ferry_foot", "ferry_motorcar",
            "ferry_bicycle", "ferry_duration",
        ]
    )
    pair_audit = pd.DataFrame()
    audit = OsmFerryProviderAudit(
        query_count=0,
        successful_query_count=0,
        failed_query_count=0,
        ferry_way_count=0,
        endpoint_matched_way_count=0,
        emitted_ferry_edge_count=0,
    )
    return edges, pair_audit, audit


class OsmReachabilityPipelineTests(unittest.TestCase):
    def test_movement_limit_is_reused_as_query_margin(self):
        candidates = pd.DataFrame(
            {
                "candidate_patch_id": ["a", "b"],
                "survey_area_id": ["A", "A"],
                "latitude": [35.0, 35.0],
                "longitude": [139.0, 139.01],
            }
        )
        nodes = pd.DataFrame(
            {
                "network_node_id": ["n1", "n2"],
                "survey_area_id": ["A", "A"],
                "latitude": [35.0, 35.0],
                "longitude": [139.0, 139.01],
                "network_source": ["osm_overpass", "osm_overpass"],
            }
        )
        network_edges = pd.DataFrame(
            {
                "from_node_id": ["n1"],
                "to_node_id": ["n2"],
                "distance_m": [800.0],
                "survey_area_id": ["A"],
                "network_mode": ["road"],
                "highway": ["residential"],
                "osm_way_id": ["1"],
                "network_source": ["osm_overpass"],
            }
        )
        area_audit = pd.DataFrame(
            {"survey_area_id": ["A"], "status": ["success"]}
        )
        provider_audit = OsmTransportProviderAudit(
            survey_area_count=1,
            successful_area_count=1,
            failed_area_count=0,
            network_node_count=2,
            network_edge_count=1,
            way_count=1,
        )

        with patch(
            "acsp.osm_reachability.fetch_osm_transport_network_for_patches",
            return_value=(nodes, network_edges, area_audit, provider_audit),
        ) as fetch, patch(
            "acsp.osm_reachability.fetch_osm_ferry_edges_for_patches",
            return_value=_empty_ferry_result(),
        ) as ferry_fetch:
            patch_edges, attachments, _, _, _, audit = build_osm_patch_reachability_edges(
                candidates, max_network_transition_km=1.0
            )

        self.assertEqual(fetch.call_args.kwargs["query_margin_km"], 1.0)
        self.assertEqual(ferry_fetch.call_args.kwargs["max_network_transition_km"], 1.0)
        self.assertEqual(len(patch_edges), 1)
        self.assertTrue(attachments["network_attached"].all())
        self.assertTrue(audit["query_margin_derived_from_movement_limit"])
        self.assertFalse(audit["candidate_pair_straight_line_used"])
        self.assertFalse(audit["straight_line_candidate_fallback"])
        self.assertFalse(audit["ferry_edges_included"])
        self.assertTrue(audit["ferry_relation_only_support"])

    def test_provider_failure_does_not_fallback_to_geometric_patch_edges(self):
        candidates = pd.DataFrame(
            {
                "candidate_patch_id": ["a", "b"],
                "survey_area_id": ["A", "A"],
                "latitude": [35.0, 35.0],
                "longitude": [139.0, 139.00001],
            }
        )
        nodes = pd.DataFrame(
            columns=["network_node_id", "survey_area_id", "latitude", "longitude", "network_source"]
        )
        network_edges = pd.DataFrame(
            columns=[
                "from_node_id", "to_node_id", "distance_m", "survey_area_id",
                "network_mode", "highway", "osm_way_id", "network_source",
            ]
        )
        area_audit = pd.DataFrame(
            {"survey_area_id": ["A"], "status": ["failed"], "error": ["offline"]}
        )
        provider_audit = OsmTransportProviderAudit(
            survey_area_count=1,
            successful_area_count=0,
            failed_area_count=1,
            network_node_count=0,
            network_edge_count=0,
            way_count=0,
        )
        with patch(
            "acsp.osm_reachability.fetch_osm_transport_network_for_patches",
            return_value=(nodes, network_edges, area_audit, provider_audit),
        ), patch(
            "acsp.osm_reachability.fetch_osm_ferry_edges_for_patches",
            return_value=_empty_ferry_result(),
        ):
            patch_edges, attachments, _, _, returned_area_audit, audit = build_osm_patch_reachability_edges(
                candidates, max_network_transition_km=5.0
            )

        self.assertTrue(patch_edges.empty)
        self.assertFalse(attachments["network_attached"].any())
        self.assertEqual(returned_area_audit.loc[0, "status"], "failed")
        self.assertFalse(audit["straight_line_candidate_fallback"])
        self.assertEqual(audit["provider"]["failed_area_count"], 1)
        self.assertFalse(audit["ferry_edges_included"])
        self.assertTrue(audit["ferry_relation_only_support"])

    def test_explicit_ferry_edge_is_the_only_cross_area_bridge(self):
        candidates = pd.DataFrame(
            {
                "candidate_patch_id": ["a", "b"],
                "survey_area_id": ["A", "B"],
                "latitude": [35.0, 35.1],
                "longitude": [139.0, 139.1],
            }
        )
        nodes = pd.DataFrame(
            {
                "network_node_id": ["osm:A:node:10", "osm:B:node:30"],
                "survey_area_id": ["A", "B"],
                "latitude": [35.0, 35.1],
                "longitude": [139.0, 139.1],
                "network_source": ["osm_overpass", "osm_overpass"],
            }
        )
        road_edges = pd.DataFrame(
            columns=[
                "from_node_id", "to_node_id", "distance_m", "survey_area_id",
                "network_mode", "highway", "osm_way_id", "network_source",
            ]
        )
        area_audit = pd.DataFrame(
            {"survey_area_id": ["A", "B"], "status": ["success", "success"]}
        )
        road_audit = OsmTransportProviderAudit(
            survey_area_count=2,
            successful_area_count=2,
            failed_area_count=0,
            network_node_count=2,
            network_edge_count=0,
            way_count=0,
        )
        ferry_edges = pd.DataFrame(
            {
                "from_node_id": ["osm:A:node:10"],
                "to_node_id": ["osm:B:node:30"],
                "distance_m": [12_000.0],
                "survey_area_id": ["A|B"],
                "network_mode": ["ferry"],
                "highway": [""],
                "osm_way_id": ["500"],
                "network_source": ["osm_overpass_route_ferry"],
            }
        )
        ferry_pair_audit = pd.DataFrame(
            {"left_survey_area_id": ["A"], "right_survey_area_id": ["B"], "status": ["success"]}
        )
        ferry_audit = OsmFerryProviderAudit(
            query_count=1,
            successful_query_count=1,
            failed_query_count=0,
            ferry_way_count=1,
            endpoint_matched_way_count=1,
            emitted_ferry_edge_count=1,
        )
        with patch(
            "acsp.osm_reachability.fetch_osm_transport_network_for_patches",
            return_value=(nodes, road_edges, area_audit, road_audit),
        ), patch(
            "acsp.osm_reachability.fetch_osm_ferry_edges_for_patches",
            return_value=(ferry_edges, ferry_pair_audit, ferry_audit),
        ):
            patch_edges, attachments, _, combined_network, _, audit = build_osm_patch_reachability_edges(
                candidates, max_network_transition_km=20.0
            )

        self.assertTrue(attachments["network_attached"].all())
        self.assertEqual(len(combined_network), 1)
        self.assertEqual(combined_network.loc[0, "network_mode"], "ferry")
        self.assertEqual(len(patch_edges), 1)
        self.assertEqual(patch_edges.loc[0, "from_patch_id"], "a")
        self.assertEqual(patch_edges.loc[0, "to_patch_id"], "b")
        self.assertTrue(audit["ferry_edges_included"])
        self.assertTrue(audit["ferry_relation_only_support"])
        self.assertFalse(audit["ferry_proximity_terminal_fallback"])
        self.assertFalse(audit["ferry_access_restrictions_enforced"])

    def test_public_pipeline_has_one_movement_tuning_input(self):
        parameters = inspect.signature(build_osm_patch_reachability_edges).parameters
        self.assertIn("max_network_transition_km", parameters)
        self.assertNotIn("query_margin_km", parameters)
        self.assertNotIn("max_sites", parameters)
        self.assertNotIn("target_coverage", parameters)
        self.assertNotIn("survey_days", parameters)
        self.assertNotIn("budget", parameters)


if __name__ == "__main__":
    unittest.main()
