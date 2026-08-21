import unittest
from unittest.mock import patch

import pandas as pd

from acsp.osm_ferry import (
    ferry_ways_to_transport_edges,
    fetch_osm_ferry_edges_for_patches,
)


def _land_nodes() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "network_node_id": ["osm:A:node:10", "osm:B:node:30"],
            "survey_area_id": ["A", "B"],
            "latitude": [35.0, 35.1],
            "longitude": [139.0, 139.1],
        }
    )


def _ferry_payload() -> dict:
    return {
        "elements": [
            {
                "type": "way",
                "id": 500,
                "nodes": [10, 20, 30],
                "tags": {
                    "route": "ferry",
                    "name": "Test Ferry",
                    "foot": "yes",
                    "motorcar": "no",
                    "duration": "00:20",
                },
                "geometry": [
                    {"lat": 35.0, "lon": 139.0},
                    {"lat": 35.05, "lon": 139.05},
                    {"lat": 35.1, "lon": 139.1},
                ],
            }
        ]
    }


class OsmFerryTopologyTests(unittest.TestCase):
    def test_direct_ferry_way_connects_only_matching_land_endpoint_ids(self):
        edges, counts = ferry_ways_to_transport_edges(_ferry_payload(), _land_nodes())
        self.assertEqual(counts["ferry_way_count"], 1)
        self.assertEqual(counts["endpoint_matched_way_count"], 1)
        self.assertEqual(counts["ferry_edge_count"], 1)
        self.assertEqual(edges.loc[0, "from_node_id"], "osm:A:node:10")
        self.assertEqual(edges.loc[0, "to_node_id"], "osm:B:node:30")
        self.assertEqual(edges.loc[0, "network_mode"], "ferry")
        self.assertEqual(edges.loc[0, "ferry_name"], "Test Ferry")
        self.assertEqual(edges.loc[0, "ferry_foot"], "yes")
        self.assertEqual(edges.loc[0, "ferry_motorcar"], "no")
        self.assertGreater(edges.loc[0, "distance_m"], 0.0)

    def test_endpoint_proximity_without_raw_osm_id_match_does_not_connect(self):
        land_nodes = _land_nodes().copy()
        land_nodes.loc[1, "network_node_id"] = "osm:B:node:31"
        edges, counts = ferry_ways_to_transport_edges(_ferry_payload(), land_nodes)
        self.assertTrue(edges.empty)
        self.assertEqual(counts["ferry_way_count"], 1)
        self.assertEqual(counts["endpoint_matched_way_count"], 0)

    def test_relation_only_ferry_is_not_silently_treated_as_supported(self):
        payload = {
            "elements": [
                {
                    "type": "relation",
                    "id": 900,
                    "tags": {"type": "route", "route": "ferry"},
                    "members": [],
                }
            ]
        }
        edges, counts = ferry_ways_to_transport_edges(payload, _land_nodes())
        self.assertTrue(edges.empty)
        self.assertEqual(counts["ferry_way_count"], 0)

    def test_area_pair_query_pruning_uses_movement_limit_only_as_lower_bound(self):
        far_candidates = pd.DataFrame(
            {
                "candidate_patch_id": ["a", "b"],
                "survey_area_id": ["A", "B"],
                "latitude": [35.0, 40.0],
                "longitude": [139.0, 145.0],
            }
        )
        with patch("acsp.osm_ferry._post_overpass", return_value={"elements": []}) as fetch:
            edges, pair_audit, audit = fetch_osm_ferry_edges_for_patches(
                far_candidates,
                _land_nodes(),
                max_network_transition_km=20.0,
            )
        self.assertTrue(edges.empty)
        self.assertEqual(audit.query_count, 2)  # A-A and B-B only; no impossible A-B query.
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(len(pair_audit), 2)
        self.assertFalse(audit.proximity_terminal_fallback)

    def test_movement_relevant_area_pair_gets_explicit_ferry_query(self):
        near_candidates = pd.DataFrame(
            {
                "candidate_patch_id": ["a", "b"],
                "survey_area_id": ["A", "B"],
                "latitude": [35.0, 35.1],
                "longitude": [139.0, 139.1],
            }
        )
        with patch("acsp.osm_ferry._post_overpass", return_value=_ferry_payload()) as fetch:
            edges, pair_audit, audit = fetch_osm_ferry_edges_for_patches(
                near_candidates,
                _land_nodes(),
                max_network_transition_km=30.0,
            )
        self.assertEqual(fetch.call_count, 3)  # A-A, A-B, B-B.
        self.assertEqual(audit.query_count, 3)
        self.assertEqual(audit.failed_query_count, 0)
        self.assertEqual(len(edges), 1)
        self.assertGreaterEqual(audit.endpoint_matched_way_count, 1)
        self.assertTrue((pair_audit["status"] == "success").all())

    def test_provider_failure_never_creates_ferry_edge(self):
        candidates = pd.DataFrame(
            {
                "candidate_patch_id": ["a"],
                "survey_area_id": ["A"],
                "latitude": [35.0],
                "longitude": [139.0],
            }
        )
        with patch("acsp.osm_ferry._post_overpass", side_effect=RuntimeError("offline")):
            edges, pair_audit, audit = fetch_osm_ferry_edges_for_patches(
                candidates,
                _land_nodes().iloc[[0]],
                max_network_transition_km=10.0,
            )
        self.assertTrue(edges.empty)
        self.assertEqual(audit.failed_query_count, 1)
        self.assertEqual(pair_audit.loc[0, "status"], "failed")
        self.assertFalse(audit.proximity_terminal_fallback)
        self.assertFalse(audit.access_restrictions_enforced)
        self.assertFalse(audit.timetable_claim)


if __name__ == "__main__":
    unittest.main()
