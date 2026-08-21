import unittest
from unittest.mock import Mock, patch

import pandas as pd

from acsp.osm_transport import (
    _candidate_around_query,
    fetch_osm_transport_network_for_patches,
    overpass_ways_to_transport_tables,
)


class OsmTransportProviderTests(unittest.TestCase):
    def test_parser_preserves_shared_way_topology(self):
        payload = {
            "elements": [
                {
                    "type": "way",
                    "id": 10,
                    "nodes": [1, 2, 3],
                    "tags": {"highway": "residential"},
                    "geometry": [
                        {"lat": 35.0, "lon": 139.0},
                        {"lat": 35.0, "lon": 139.001},
                        {"lat": 35.0, "lon": 139.002},
                    ],
                },
                {
                    "type": "way",
                    "id": 11,
                    "nodes": [3, 4],
                    "tags": {"highway": "path"},
                    "geometry": [
                        {"lat": 35.0, "lon": 139.002},
                        {"lat": 35.001, "lon": 139.002},
                    ],
                },
            ]
        }
        nodes, edges, counts = overpass_ways_to_transport_tables(
            payload, survey_area_id="island-a"
        )
        self.assertEqual(counts, {"way_count": 2, "node_count": 4, "edge_count": 3})
        self.assertEqual(len(nodes), 4)
        self.assertEqual(len(edges), 3)
        shared_id = "osm:island-a:node:3"
        self.assertIn(shared_id, set(nodes["network_node_id"]))
        incident = edges[
            (edges["from_node_id"] == shared_id) | (edges["to_node_id"] == shared_id)
        ]
        self.assertEqual(len(incident), 2)
        self.assertEqual(set(edges["network_mode"]), {"road", "trail"})
        self.assertTrue((edges["distance_m"] > 0).all())

    def test_coordinate_fallback_connects_equal_geometry_points_within_area(self):
        payload = {
            "elements": [
                {
                    "type": "way",
                    "id": 1,
                    "tags": {"highway": "track"},
                    "geometry": [
                        {"lat": 34.0, "lon": 139.0},
                        {"lat": 34.0, "lon": 139.001},
                    ],
                },
                {
                    "type": "way",
                    "id": 2,
                    "tags": {"highway": "service"},
                    "geometry": [
                        {"lat": 34.0, "lon": 139.001},
                        {"lat": 34.001, "lon": 139.001},
                    ],
                },
            ]
        }
        nodes, edges, counts = overpass_ways_to_transport_tables(
            payload, survey_area_id="island"
        )
        self.assertEqual(counts["node_count"], 3)
        self.assertEqual(counts["edge_count"], 2)
        shared = nodes[
            (nodes["latitude"].round(7) == 34.0)
            & (nodes["longitude"].round(7) == 139.001)
        ]
        self.assertEqual(len(shared), 1)

    def test_same_osm_node_is_namespaced_by_survey_area(self):
        payload = {
            "elements": [
                {
                    "type": "way",
                    "id": 1,
                    "nodes": [100, 101],
                    "tags": {"highway": "residential"},
                    "geometry": [
                        {"lat": 35.0, "lon": 139.0},
                        {"lat": 35.0, "lon": 139.001},
                    ],
                }
            ]
        }
        nodes_a, _, _ = overpass_ways_to_transport_tables(payload, survey_area_id="A")
        nodes_b, _, _ = overpass_ways_to_transport_tables(payload, survey_area_id="B")
        self.assertTrue(set(nodes_a["network_node_id"]).isdisjoint(set(nodes_b["network_node_id"])))

    def test_candidate_query_uses_local_around_union_not_region_bbox(self):
        candidates = pd.DataFrame(
            {
                "latitude": [35.0, 26.2],
                "longitude": [139.0, 127.7],
            }
        )
        query, unique_centers = _candidate_around_query(
            candidates,
            latitude_col="latitude",
            longitude_col="longitude",
            radius_km=5.0,
        )
        self.assertEqual(unique_centers, 2)
        self.assertEqual(query.count('way["highway"](around:'), 2)
        self.assertIn('(around:5000.000,35.0000000,139.0000000)', query)
        self.assertIn('(around:5000.000,26.2000000,127.7000000)', query)
        # No one giant bounding-box selector spans the empty space between them.
        self.assertNotIn('way["highway"](26.2,127.7,35.0,139.0)', query)
        self.assertTrue(query.endswith(');out body geom;'))

    def test_candidate_query_collapses_duplicate_retrieval_centers(self):
        candidates = pd.DataFrame(
            {
                "latitude": [35.0, 35.0, 35.1],
                "longitude": [139.0, 139.0, 139.1],
            }
        )
        query, unique_centers = _candidate_around_query(
            candidates,
            latitude_col="latitude",
            longitude_col="longitude",
            radius_km=2.0,
        )
        self.assertEqual(unique_centers, 2)
        self.assertEqual(query.count('way["highway"](around:'), 2)

    def test_fetch_is_per_area_and_retains_failure_without_geometric_fallback(self):
        candidates = pd.DataFrame(
            {
                "candidate_patch_id": ["a", "b"],
                "survey_area_id": ["A", "B"],
                "latitude": [35.0, 34.0],
                "longitude": [139.0, 138.0],
            }
        )
        good_payload = {
            "elements": [
                {
                    "type": "way",
                    "id": 1,
                    "nodes": [1, 2],
                    "tags": {"highway": "residential"},
                    "geometry": [
                        {"lat": 35.0, "lon": 139.0},
                        {"lat": 35.0, "lon": 139.001},
                    ],
                }
            ]
        }

        good_response = Mock()
        good_response.raise_for_status.return_value = None
        good_response.json.return_value = good_payload
        bad_response = Mock()
        bad_response.raise_for_status.side_effect = RuntimeError("provider unavailable")

        with patch("acsp.osm_transport.requests.post", side_effect=[good_response, bad_response]) as post:
            nodes, edges, area_audit, audit = fetch_osm_transport_network_for_patches(
                candidates,
                query_margin_km=1.0,
                attempts=1,
            )

        self.assertEqual(audit.survey_area_count, 2)
        self.assertEqual(audit.successful_area_count, 1)
        self.assertEqual(audit.failed_area_count, 1)
        self.assertEqual(audit.query_scope, "candidate_around_union")
        self.assertTrue(audit.query_radius_derived_from_movement_limit)
        self.assertFalse(audit.region_spanning_bbox_query)
        self.assertFalse(audit.straight_line_candidate_fallback)
        self.assertEqual(set(nodes["survey_area_id"]), {"A"})
        self.assertEqual(set(edges["survey_area_id"]), {"A"})
        status = dict(zip(area_audit["survey_area_id"], area_audit["status"]))
        self.assertEqual(status, {"A": "success", "B": "failed"})
        self.assertTrue((area_audit["query_scope"] == "candidate_around_union").all())
        self.assertTrue((area_audit["query_radius_km"] == 1.0).all())
        self.assertTrue((area_audit["candidate_center_count"] == 1).all())
        self.assertTrue((area_audit["unique_query_center_count"] == 1).all())
        first_query = post.call_args_list[0].kwargs["data"]["data"]
        second_query = post.call_args_list[1].kwargs["data"]["data"]
        self.assertIn('(around:1000.000,35.0000000,139.0000000)', first_query)
        self.assertIn('(around:1000.000,34.0000000,138.0000000)', second_query)

    def test_non_highway_and_incomplete_geometry_are_ignored(self):
        payload = {
            "elements": [
                {
                    "type": "way",
                    "id": 1,
                    "tags": {"route": "ferry"},
                    "geometry": [
                        {"lat": 35.0, "lon": 139.0},
                        {"lat": 35.1, "lon": 139.1},
                    ],
                },
                {
                    "type": "way",
                    "id": 2,
                    "tags": {"highway": "path"},
                    "geometry": [{"lat": 35.0, "lon": 139.0}],
                },
            ]
        }
        nodes, edges, counts = overpass_ways_to_transport_tables(payload, survey_area_id="A")
        self.assertTrue(nodes.empty)
        self.assertTrue(edges.empty)
        self.assertEqual(counts["way_count"], 0)


if __name__ == "__main__":
    unittest.main()
