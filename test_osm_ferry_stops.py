import unittest
from unittest.mock import patch

import pandas as pd

from acsp.osm_ferry_stops import (
    _ferry_stop_query,
    ferry_relation_stops_to_transport_edges,
    fetch_osm_ferry_stop_edges_for_patches,
)


def _land_nodes(second_raw_id: int = 40) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "network_node_id": ["osm:A:node:10", f"osm:B:node:{second_raw_id}"],
            "survey_area_id": ["A", "B"],
            "latitude": [35.0, 35.1],
            "longitude": [139.0, 139.1],
        }
    )


def _relation_stop_payload(second_stop_id: int = 40) -> dict:
    return {
        "elements": [
            {
                "type": "relation",
                "id": 900,
                "tags": {
                    "type": "route",
                    "route": "ferry",
                    "name": "Explicit Stop Ferry",
                    "ref": "F1",
                },
                "members": [
                    {"type": "node", "ref": 10, "role": "stop"},
                    {"type": "node", "ref": second_stop_id, "role": "stop"},
                    {"type": "way", "ref": 100, "role": ""},
                    {"type": "way", "ref": 101, "role": ""},
                ],
            },
            {
                "type": "way",
                "id": 100,
                "nodes": [10, 20],
                "geometry": [
                    {"lat": 35.0, "lon": 139.0},
                    {"lat": 35.05, "lon": 139.05},
                ],
                "tags": {},
            },
            {
                "type": "way",
                "id": 101,
                "nodes": [20, second_stop_id],
                "geometry": [
                    {"lat": 35.05, "lon": 139.05},
                    {"lat": 35.1, "lon": 139.1},
                ],
                "tags": {},
            },
            {
                "type": "node",
                "id": 10,
                "lat": 35.0,
                "lon": 139.0,
                "tags": {
                    "amenity": "ferry_terminal",
                    "public_transport": "stop_position",
                    "ferry": "yes",
                    "name": "Terminal A",
                },
            },
            {
                "type": "node",
                "id": second_stop_id,
                "lat": 35.1,
                "lon": 139.1,
                "tags": {
                    "amenity": "ferry_terminal",
                    "public_transport": "stop_position",
                    "ferry": "yes",
                    "name": "Terminal B",
                },
            },
        ]
    }


class OsmFerryStopTerminalTests(unittest.TestCase):
    def test_exact_relation_stops_in_both_graphs_create_ferry_edge(self):
        edges, stops, counts = ferry_relation_stops_to_transport_edges(
            _relation_stop_payload(), _land_nodes()
        )
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges.loc[0, "from_node_id"], "osm:A:node:10")
        self.assertEqual(edges.loc[0, "to_node_id"], "osm:B:node:40")
        self.assertEqual(edges.loc[0, "network_mode"], "ferry")
        self.assertEqual(edges.loc[0, "network_source"], "osm_overpass_ferry_relation_stop")
        self.assertEqual(counts["relation_stop_member_count"], 2)
        self.assertEqual(counts["unique_stop_node_count"], 2)
        self.assertEqual(counts["ferry_terminal_tagged_stop_count"], 2)
        self.assertEqual(counts["public_transport_ferry_stop_count"], 2)
        self.assertEqual(counts["stop_in_ferry_graph_count"], 2)
        self.assertEqual(counts["stop_in_land_graph_count"], 2)
        self.assertEqual(counts["stop_in_both_graphs_count"], 2)
        self.assertTrue(stops["exact_terminal_usable"].all())

    def test_stop_on_ferry_graph_but_not_land_graph_stays_disconnected(self):
        edges, stops, counts = ferry_relation_stops_to_transport_edges(
            _relation_stop_payload(), _land_nodes(second_raw_id=41)
        )
        self.assertTrue(edges.empty)
        self.assertEqual(counts["stop_in_ferry_graph_count"], 2)
        self.assertEqual(counts["stop_in_land_graph_count"], 1)
        self.assertEqual(counts["stop_in_both_graphs_count"], 1)
        self.assertEqual(counts["unmatched_land_stop_count"], 1)
        terminal_b = stops[stops["stop_node_id"] == "40"].iloc[0]
        self.assertTrue(terminal_b["in_ferry_member_way_graph"])
        self.assertFalse(terminal_b["in_land_highway_graph"])
        self.assertFalse(terminal_b["exact_terminal_usable"])

    def test_equal_coordinates_with_different_raw_node_id_do_not_snap(self):
        land = _land_nodes(second_raw_id=41).copy()
        # Node 41 deliberately has exactly the coordinates of stop node 40.
        land.loc[1, ["latitude", "longitude"]] = [35.1, 139.1]
        edges, stops, _ = ferry_relation_stops_to_transport_edges(
            _relation_stop_payload(), land
        )
        self.assertTrue(edges.empty)
        terminal_b = stops[stops["stop_node_id"] == "40"].iloc[0]
        self.assertFalse(terminal_b["in_land_highway_graph"])

    def test_non_stop_relation_node_member_is_not_a_terminal(self):
        payload = _relation_stop_payload()
        payload["elements"][0]["members"][1]["role"] = "platform"
        edges, stops, counts = ferry_relation_stops_to_transport_edges(
            payload, _land_nodes()
        )
        self.assertTrue(edges.empty)
        self.assertEqual(counts["relation_stop_member_count"], 1)
        self.assertEqual(stops["stop_node_id"].tolist(), ["10"])

    def test_query_requests_relation_member_ways_and_nodes(self):
        query = _ferry_stop_query(138.9, 34.9, 139.2, 35.2)
        self.assertIn('relation["type"="route"]["route"="ferry"]', query)
        self.assertIn("way(r.fr)", query)
        self.assertIn("node(r.fr)", query)
        self.assertIn("out body geom", query)

    def test_fetch_aggregates_exact_stop_diagnostics_without_proximity_fallback(self):
        candidates = pd.DataFrame(
            {
                "candidate_patch_id": ["a", "b"],
                "survey_area_id": ["A", "B"],
                "latitude": [35.0, 35.1],
                "longitude": [139.0, 139.1],
            }
        )
        with patch(
            "acsp.osm_ferry_stops._post_overpass",
            return_value=_relation_stop_payload(),
        ) as post:
            edges, stops, audit = fetch_osm_ferry_stop_edges_for_patches(
                candidates,
                _land_nodes(),
                max_network_transition_km=30.0,
            )
        self.assertEqual(post.call_count, 3)  # A-A, A-B, B-B.
        self.assertEqual(audit.query_count, 3)
        self.assertEqual(audit.failed_query_count, 0)
        self.assertEqual(audit.unique_stop_node_count, 2)
        self.assertEqual(audit.stop_in_both_graphs_count, 2)
        self.assertEqual(audit.emitted_ferry_edge_count, 1)
        self.assertFalse(audit.proximity_terminal_fallback)
        self.assertEqual(len(edges), 1)
        self.assertEqual(len(stops.drop_duplicates("stop_node_id")), 2)


if __name__ == "__main__":
    unittest.main()
