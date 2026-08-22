import unittest
from unittest.mock import patch

import pandas as pd

from acsp.osm_ferry_stop_highways import (
    _bounded_highway_query,
    _highway_reverse_query,
    fetch_explicit_highway_extensions_for_ferry_stops,
    highway_reverse_payload_to_extensions,
)


def _stop_audit() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "stop_node_id": ["10"],
            "in_ferry_member_way_graph": [True],
            "in_land_highway_graph": [False],
        }
    )


def _land_nodes(anchor_raw_id: int = 30) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "network_node_id": [f"osm:A:node:{anchor_raw_id}"],
            "survey_area_id": ["A"],
            "latitude": [35.0],
            "longitude": [139.01],
        }
    )


def _anchored_highway_payload() -> dict:
    return {
        "elements": [
            {
                "type": "way",
                "id": 100,
                "nodes": [10, 20, 30],
                "tags": {"highway": "service"},
                "geometry": [
                    {"lat": 35.0, "lon": 139.0},
                    {"lat": 35.0, "lon": 139.005},
                    {"lat": 35.0, "lon": 139.01},
                ],
            }
        ]
    }


def _direct_unanchored_payload() -> dict:
    return {
        "elements": [
            {
                "type": "way",
                "id": 100,
                "nodes": [10, 20],
                "tags": {"highway": "service"},
                "geometry": [
                    {"lat": 35.0, "lon": 139.0},
                    {"lat": 35.0, "lon": 139.005},
                ],
            }
        ]
    }


def _bounded_anchored_payload() -> dict:
    return {
        "elements": [
            *_direct_unanchored_payload()["elements"],
            {
                "type": "way",
                "id": 101,
                "nodes": [20, 30],
                "tags": {"highway": "residential"},
                "geometry": [
                    {"lat": 35.0, "lon": 139.005},
                    {"lat": 35.0, "lon": 139.01},
                ],
            },
        ]
    }


class FerryStopHighwayReverseTests(unittest.TestCase):
    def test_query_uses_exact_node_ids_and_node_to_way_recurse(self):
        query = _highway_reverse_query(["40", "10", "10"])
        self.assertIn("node(id:10,40)->.st", query)
        self.assertIn('way(bn.st)["highway"]->.hw', query)
        self.assertIn("node(w.hw)->.hwn", query)
        self.assertIn("(.st;.hw;.hwn;);", query)
        self.assertIn("out body geom", query)

    def test_bounded_query_uses_named_stop_set_and_movement_radius_only_for_retrieval(self):
        query = _bounded_highway_query(["10"], 5000.0)
        self.assertIn("node(id:10)->.st", query)
        self.assertIn('way(around.st:5000.000)["highway"]->.hw', query)
        self.assertIn("node(w.hw)->.hwn", query)
        self.assertIn("(.st;.hw;.hwn;);", query)
        self.assertIn("out body geom", query)

    def test_highway_component_with_exact_land_anchor_is_imported(self):
        nodes, edges, counts = highway_reverse_payload_to_extensions(
            _anchored_highway_payload(),
            ["10"],
            _land_nodes(),
        )
        self.assertEqual(counts["queried_stop_count"], 1)
        self.assertEqual(counts["stops_with_highway_way_count"], 1)
        self.assertEqual(counts["returned_highway_way_count"], 1)
        self.assertEqual(counts["anchored_stop_count"], 1)
        self.assertEqual(counts["remaining_unconnected_stop_count"], 0)
        self.assertEqual(counts["stop_component_way_count"], 1)
        self.assertEqual(counts["stop_component_node_count"], 3)
        self.assertEqual(counts["stop_component_existing_land_anchor_count"], 1)
        self.assertIn("osm:A:node:10", set(nodes["network_node_id"]))
        self.assertIn("osm:A:node:30", set(nodes["network_node_id"]))
        self.assertEqual(len(edges), 2)
        self.assertEqual(set(edges["survey_area_id"]), {"A"})

    def test_highway_way_without_existing_land_anchor_is_not_imported(self):
        nodes, edges, counts = highway_reverse_payload_to_extensions(
            _anchored_highway_payload(),
            ["10"],
            _land_nodes(anchor_raw_id=99),
        )
        self.assertTrue(nodes.empty)
        self.assertTrue(edges.empty)
        self.assertEqual(counts["stops_with_highway_way_count"], 1)
        self.assertEqual(counts["anchored_stop_count"], 0)
        self.assertEqual(counts["remaining_unconnected_stop_count"], 1)
        self.assertEqual(counts["stop_component_existing_land_anchor_count"], 0)

    def test_nearby_or_equal_coordinate_way_without_stop_raw_id_does_not_connect(self):
        payload = {
            "elements": [
                {
                    "type": "way",
                    "id": 101,
                    "nodes": [11, 30],
                    "tags": {"highway": "service"},
                    "geometry": [
                        # Node 11 deliberately has the same coordinates a stop 10 could have.
                        {"lat": 35.0, "lon": 139.0},
                        {"lat": 35.0, "lon": 139.01},
                    ],
                }
            ]
        }
        nodes, edges, counts = highway_reverse_payload_to_extensions(
            payload,
            ["10"],
            _land_nodes(),
        )
        self.assertTrue(nodes.empty)
        self.assertTrue(edges.empty)
        self.assertEqual(counts["stops_with_highway_way_count"], 0)
        self.assertEqual(counts["anchored_stop_count"], 0)
        self.assertEqual(counts["stop_component_way_count"], 0)

    def test_connected_multiway_component_can_anchor_stop_through_shared_raw_nodes(self):
        nodes, edges, counts = highway_reverse_payload_to_extensions(
            _bounded_anchored_payload(),
            ["10"],
            _land_nodes(),
        )
        self.assertEqual(counts["anchored_stop_count"], 1)
        self.assertEqual(counts["stop_component_way_count"], 2)
        self.assertEqual(counts["stop_component_node_count"], 3)
        self.assertEqual(counts["stop_component_existing_land_anchor_count"], 1)
        self.assertIn("osm:A:node:10", set(nodes["network_node_id"]))
        self.assertEqual(len(edges), 2)

    def test_fetch_skips_bounded_query_when_direct_reverse_already_anchors_stop(self):
        with patch(
            "acsp.osm_ferry_stop_highways._post_overpass",
            return_value=_anchored_highway_payload(),
        ) as post:
            nodes, edges, audit = fetch_explicit_highway_extensions_for_ferry_stops(
                _stop_audit(),
                _land_nodes(),
                max_network_transition_km=5.0,
            )
        self.assertEqual(post.call_count, 1)
        self.assertEqual(audit.queried_stop_count, 1)
        self.assertEqual(audit.anchored_stop_count, 1)
        self.assertEqual(audit.bounded_query_count, 0)
        self.assertEqual(audit.bounded_query_radius_m, 5000.0)
        self.assertEqual(audit.remaining_unconnected_stop_count, 0)
        self.assertFalse(audit.proximity_terminal_fallback)
        self.assertFalse(audit.candidate_to_terminal_straight_line_used)
        self.assertFalse(audit.provider_query_failed)
        self.assertEqual(len(nodes), 3)
        self.assertEqual(len(edges), 2)

    def test_fetch_uses_bounded_exact_component_when_direct_way_has_no_anchor(self):
        with patch(
            "acsp.osm_ferry_stop_highways._post_overpass",
            side_effect=[_direct_unanchored_payload(), _bounded_anchored_payload()],
        ) as post:
            nodes, edges, audit = fetch_explicit_highway_extensions_for_ferry_stops(
                _stop_audit(),
                _land_nodes(),
                max_network_transition_km=5.0,
            )
        self.assertEqual(post.call_count, 2)
        self.assertEqual(audit.stops_with_highway_way_count, 1)
        self.assertEqual(audit.returned_highway_way_count, 1)
        self.assertEqual(audit.bounded_query_count, 1)
        self.assertEqual(audit.bounded_query_radius_m, 5000.0)
        self.assertEqual(audit.bounded_returned_highway_way_count, 2)
        self.assertEqual(audit.bounded_stop_component_way_count, 2)
        self.assertEqual(audit.bounded_stop_component_node_count, 3)
        self.assertEqual(audit.bounded_stop_component_existing_land_anchor_count, 1)
        self.assertEqual(audit.anchored_stop_count, 1)
        self.assertEqual(audit.remaining_unconnected_stop_count, 0)
        self.assertTrue(audit.bounded_radius_is_retrieval_only)
        self.assertFalse(audit.proximity_terminal_fallback)
        self.assertIn("osm:A:node:10", set(nodes["network_node_id"]))
        self.assertEqual(len(edges), 2)

    def test_provider_failure_is_explicit_and_leaves_stop_unconnected(self):
        with patch(
            "acsp.osm_ferry_stop_highways._post_overpass",
            side_effect=RuntimeError("Overpass offline"),
        ) as post:
            nodes, edges, audit = fetch_explicit_highway_extensions_for_ferry_stops(
                _stop_audit(),
                _land_nodes(),
                max_network_transition_km=5.0,
            )
        self.assertEqual(post.call_count, 2)  # direct and bounded both fail closed.
        self.assertTrue(nodes.empty)
        self.assertTrue(edges.empty)
        self.assertTrue(audit.provider_query_failed)
        self.assertTrue(audit.direct_query_failed)
        self.assertTrue(audit.bounded_query_failed)
        self.assertIn("Overpass offline", audit.provider_error)
        self.assertEqual(audit.queried_stop_count, 1)
        self.assertEqual(audit.anchored_stop_count, 0)
        self.assertEqual(audit.remaining_unconnected_stop_count, 1)
        self.assertFalse(audit.proximity_terminal_fallback)

    def test_no_unmatched_stop_skips_provider_request(self):
        stop_audit = pd.DataFrame(
            {
                "stop_node_id": ["10"],
                "in_ferry_member_way_graph": [True],
                "in_land_highway_graph": [True],
            }
        )
        with patch("acsp.osm_ferry_stop_highways._post_overpass") as post:
            nodes, edges, audit = fetch_explicit_highway_extensions_for_ferry_stops(
                stop_audit,
                _land_nodes(anchor_raw_id=10),
                max_network_transition_km=5.0,
            )
        post.assert_not_called()
        self.assertTrue(nodes.empty)
        self.assertTrue(edges.empty)
        self.assertEqual(audit.queried_stop_count, 0)
        self.assertEqual(audit.bounded_query_count, 0)
        self.assertEqual(audit.bounded_query_radius_m, 5000.0)


if __name__ == "__main__":
    unittest.main()
