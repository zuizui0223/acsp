import unittest
from unittest.mock import patch

import pandas as pd

from acsp.osm_ferry import (
    _ferry_query,
    ferry_relations_to_transport_edges,
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


def _relation_land_nodes() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "network_node_id": ["osm:A:node:10", "osm:B:node:40"],
            "survey_area_id": ["A", "B"],
            "latitude": [35.0, 35.12],
            "longitude": [139.0, 139.12],
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


def _relation_payload(*, include_second_way: bool = True) -> dict:
    elements = [
        {
            "type": "relation",
            "id": 900,
            "tags": {
                "type": "route",
                "route": "ferry",
                "name": "Relation Ferry",
                "ref": "RF1",
                "duration": "00:30",
                "foot": "yes",
            },
            "members": [
                {"type": "way", "ref": 501, "role": ""},
                {"type": "way", "ref": 502, "role": ""},
            ],
        },
        {
            "type": "way",
            "id": 501,
            "nodes": [10, 20, 30],
            "tags": {},
            "geometry": [
                {"lat": 35.0, "lon": 139.0},
                {"lat": 35.04, "lon": 139.04},
                {"lat": 35.08, "lon": 139.08},
            ],
        },
    ]
    if include_second_way:
        elements.append(
            {
                "type": "way",
                "id": 502,
                "nodes": [30, 35, 40],
                "tags": {},
                "geometry": [
                    {"lat": 35.08, "lon": 139.08},
                    {"lat": 35.10, "lon": 139.10},
                    {"lat": 35.12, "lon": 139.12},
                ],
            }
        )
    return {"elements": elements}


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
        self.assertEqual(edges.loc[0, "ferry_relation_id"], "")
        self.assertGreater(edges.loc[0, "distance_m"], 0.0)

    def test_endpoint_proximity_without_raw_osm_id_match_does_not_connect(self):
        land_nodes = _land_nodes().copy()
        land_nodes.loc[1, "network_node_id"] = "osm:B:node:31"
        edges, counts = ferry_ways_to_transport_edges(_ferry_payload(), land_nodes)
        self.assertTrue(edges.empty)
        self.assertEqual(counts["ferry_way_count"], 1)
        self.assertEqual(counts["endpoint_matched_way_count"], 0)

    def test_relation_only_ferry_reconstructs_multi_way_graph(self):
        payload = _relation_payload()
        direct_edges, direct_counts = ferry_ways_to_transport_edges(
            payload, _relation_land_nodes()
        )
        relation_edges, counts = ferry_relations_to_transport_edges(
            payload, _relation_land_nodes()
        )
        self.assertTrue(direct_edges.empty)  # Member ways are not individually route=ferry.
        self.assertEqual(direct_counts["ferry_way_count"], 0)
        self.assertEqual(counts["ferry_relation_count"], 1)
        self.assertEqual(counts["relation_member_way_count"], 2)
        self.assertEqual(counts["incomplete_relation_member_way_count"], 0)
        self.assertEqual(counts["relation_endpoint_matched_count"], 1)
        self.assertEqual(len(relation_edges), 1)
        row = relation_edges.iloc[0]
        self.assertEqual(row["from_node_id"], "osm:A:node:10")
        self.assertEqual(row["to_node_id"], "osm:B:node:40")
        self.assertEqual(row["network_source"], "osm_overpass_ferry_relation")
        self.assertEqual(row["ferry_relation_id"], "900")
        self.assertEqual(row["ferry_name"], "Relation Ferry")
        self.assertEqual(row["ferry_ref"], "RF1")
        self.assertEqual(row["ferry_duration"], "00:30")
        self.assertEqual(row["ferry_foot"], "yes")
        self.assertGreater(row["distance_m"], 0.0)

    def test_missing_relation_member_way_is_not_bridged(self):
        edges, counts = ferry_relations_to_transport_edges(
            _relation_payload(include_second_way=False), _relation_land_nodes()
        )
        self.assertTrue(edges.empty)
        self.assertEqual(counts["ferry_relation_count"], 1)
        self.assertEqual(counts["relation_member_way_count"], 1)
        self.assertEqual(counts["incomplete_relation_member_way_count"], 1)
        self.assertEqual(counts["relation_endpoint_matched_count"], 0)

    def test_relation_terminal_proximity_without_raw_id_match_does_not_connect(self):
        land_nodes = _relation_land_nodes().copy()
        land_nodes.loc[1, "network_node_id"] = "osm:B:node:41"
        edges, counts = ferry_relations_to_transport_edges(
            _relation_payload(), land_nodes
        )
        self.assertTrue(edges.empty)
        self.assertEqual(counts["relation_endpoint_matched_count"], 0)

    def test_ferry_query_requests_direct_ways_relations_and_member_ways(self):
        query = _ferry_query(138.9, 34.9, 139.2, 35.2)
        self.assertIn('relation["type"="route"]["route"="ferry"]', query)
        self.assertIn("way(r.fr)", query)
        self.assertIn('way["route"="ferry"]', query)
        self.assertIn("out body geom", query)

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
        self.assertTrue(audit.relation_only_support)
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

    def test_fetch_aggregates_relation_only_ferry_counts(self):
        candidates = pd.DataFrame(
            {
                "candidate_patch_id": ["a", "b"],
                "survey_area_id": ["A", "B"],
                "latitude": [35.0, 35.12],
                "longitude": [139.0, 139.12],
            }
        )
        with patch(
            "acsp.osm_ferry._post_overpass", return_value=_relation_payload()
        ):
            edges, pair_audit, audit = fetch_osm_ferry_edges_for_patches(
                candidates,
                _relation_land_nodes(),
                max_network_transition_km=30.0,
            )
        self.assertEqual(len(edges), 1)
        self.assertEqual(audit.ferry_relation_count, 3)  # Same fixture returned for A-A, A-B, B-B.
        self.assertEqual(audit.relation_member_way_count, 6)
        self.assertEqual(audit.relation_endpoint_matched_count, 3)
        self.assertEqual(audit.incomplete_relation_member_way_count, 0)
        self.assertTrue(audit.relation_only_support)
        self.assertIn("ferry_relation_count", pair_audit.columns)

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
