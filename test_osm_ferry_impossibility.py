import unittest
from unittest.mock import patch

import pandas as pd

from acsp.osm_ferry_impossibility import (
    _stop_coordinate_query,
    ferry_stop_candidate_lower_bounds,
    fetch_movement_pruned_highway_extensions_for_ferry_stops,
)
from acsp.osm_ferry_stop_highways import OsmFerryStopHighwayAudit


def _stop_audit(*ids: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "stop_node_id": list(ids),
            "in_ferry_member_way_graph": [True] * len(ids),
            "in_land_highway_graph": [False] * len(ids),
        }
    )


def _candidates(lat: float, radius_m: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "candidate_patch_id": ["p1"],
            "survey_area_id": ["A"],
            "latitude": [lat],
            "longitude": [139.0],
            "candidate_patch_radius_m": [radius_m],
        }
    )


def _coordinate_payload(node_id: int = 10, lat: float = 35.0, lon: float = 139.0) -> dict:
    return {
        "elements": [
            {"type": "node", "id": node_id, "lat": lat, "lon": lon, "tags": {}}
        ]
    }


def _empty_topology_result():
    nodes = pd.DataFrame(
        columns=["network_node_id", "survey_area_id", "latitude", "longitude", "network_source"]
    )
    edges = pd.DataFrame(columns=["from_node_id", "to_node_id", "distance_m"])
    audit = OsmFerryStopHighwayAudit(
        queried_stop_count=1,
        stops_with_highway_way_count=1,
        returned_highway_way_count=1,
        anchored_stop_count=0,
        imported_extension_node_count=0,
        imported_extension_edge_count=0,
        remaining_unconnected_stop_count=1,
        bounded_query_count=1,
        bounded_query_radius_m=5000.0,
    )
    return nodes, edges, audit


class FerryStopImpossibilityTests(unittest.TestCase):
    def test_coordinate_query_is_exact_node_lookup(self):
        query = _stop_coordinate_query(["40", "10", "10"])
        self.assertEqual(
            query,
            "[out:json][timeout:25];node(id:10,40);out body;",
        )

    def test_patch_radius_is_subtracted_from_geodesic_lower_bound(self):
        bounds = ferry_stop_candidate_lower_bounds(
            {"10": (35.0, 139.0)},
            _candidates(35.045, radius_m=500.0),
        )
        self.assertEqual(len(bounds), 1)
        centre = float(bounds.loc[0, "minimum_center_geodesic_km"])
        lower = float(bounds.loc[0, "minimum_patch_footprint_lower_bound_km"])
        self.assertGreater(centre, lower)
        self.assertAlmostEqual(centre - lower, 0.5, places=5)
        self.assertEqual(bounds.loc[0, "nearest_candidate_patch_id"], "p1")

    def test_impossible_stop_skips_expensive_topology_provider(self):
        # ~11 km centre distance minus 0.1 km radius remains > 5 km.
        with patch(
            "acsp.osm_ferry_impossibility._post_overpass",
            return_value=_coordinate_payload(),
        ) as coordinate_query, patch(
            "acsp.osm_ferry_impossibility.fetch_explicit_highway_extensions_for_ferry_stops"
        ) as topology:
            nodes, edges, audit = fetch_movement_pruned_highway_extensions_for_ferry_stops(
                _stop_audit("10"),
                pd.DataFrame(columns=["network_node_id", "survey_area_id"]),
                _candidates(35.1, radius_m=100.0),
                max_network_transition_km=5.0,
            )
        self.assertEqual(coordinate_query.call_count, 1)
        topology.assert_not_called()
        self.assertTrue(nodes.empty)
        self.assertTrue(edges.empty)
        self.assertEqual(audit.movement_impossible_stop_count, 1)
        self.assertEqual(audit.topology_eligible_stop_count, 0)
        self.assertEqual(audit.skipped_by_geodesic_lower_bound_count, 1)
        self.assertGreater(audit.minimum_patch_footprint_lower_bound_km, 5.0)
        self.assertTrue(audit.geodesic_is_lower_bound_only)
        self.assertFalse(audit.geodesic_used_to_create_reachability)
        self.assertFalse(audit.candidate_to_terminal_straight_line_edge)

    def test_stop_with_lower_bound_inside_limit_uses_exact_topology_provider(self):
        # ~3.3 km from the candidate, so impossibility cannot be proven.
        with patch(
            "acsp.osm_ferry_impossibility._post_overpass",
            return_value=_coordinate_payload(),
        ), patch(
            "acsp.osm_ferry_impossibility.fetch_explicit_highway_extensions_for_ferry_stops",
            return_value=_empty_topology_result(),
        ) as topology:
            _nodes, _edges, audit = fetch_movement_pruned_highway_extensions_for_ferry_stops(
                _stop_audit("10"),
                pd.DataFrame(columns=["network_node_id", "survey_area_id"]),
                _candidates(35.03, radius_m=100.0),
                max_network_transition_km=5.0,
            )
        self.assertEqual(topology.call_count, 1)
        self.assertEqual(audit.movement_impossible_stop_count, 0)
        self.assertEqual(audit.topology_eligible_stop_count, 1)
        self.assertEqual(audit.skipped_by_geodesic_lower_bound_count, 0)
        self.assertLess(audit.minimum_patch_footprint_lower_bound_km, 5.0)
        self.assertEqual(audit.topology_provider["bounded_query_count"], 1)

    def test_patch_radius_can_prevent_false_impossibility(self):
        # Centre is a little over 5 km away, but a 1 km patch radius makes the
        # conservative patch-footprint lower bound < 5 km.
        with patch(
            "acsp.osm_ferry_impossibility._post_overpass",
            return_value=_coordinate_payload(),
        ), patch(
            "acsp.osm_ferry_impossibility.fetch_explicit_highway_extensions_for_ferry_stops",
            return_value=_empty_topology_result(),
        ) as topology:
            _nodes, _edges, audit = fetch_movement_pruned_highway_extensions_for_ferry_stops(
                _stop_audit("10"),
                pd.DataFrame(columns=["network_node_id", "survey_area_id"]),
                _candidates(35.05, radius_m=1000.0),
                max_network_transition_km=5.0,
            )
        self.assertGreater(audit.minimum_center_geodesic_km, 5.0)
        self.assertLess(audit.minimum_patch_footprint_lower_bound_km, 5.0)
        self.assertEqual(topology.call_count, 1)
        self.assertEqual(audit.movement_impossible_stop_count, 0)

    def test_missing_coordinate_evidence_never_becomes_impossibility(self):
        with patch(
            "acsp.osm_ferry_impossibility._post_overpass",
            return_value={"elements": []},
        ), patch(
            "acsp.osm_ferry_impossibility.fetch_explicit_highway_extensions_for_ferry_stops",
            return_value=_empty_topology_result(),
        ) as topology:
            _nodes, _edges, audit = fetch_movement_pruned_highway_extensions_for_ferry_stops(
                _stop_audit("10"),
                pd.DataFrame(columns=["network_node_id", "survey_area_id"]),
                _candidates(40.0),
                max_network_transition_km=5.0,
            )
        self.assertEqual(audit.coordinate_available_stop_count, 0)
        self.assertEqual(audit.movement_impossible_stop_count, 0)
        self.assertEqual(audit.topology_eligible_stop_count, 1)
        self.assertEqual(topology.call_count, 1)

    def test_coordinate_provider_failure_falls_back_to_exact_topology_provider(self):
        with patch(
            "acsp.osm_ferry_impossibility._post_overpass",
            side_effect=RuntimeError("coordinate lookup offline"),
        ), patch(
            "acsp.osm_ferry_impossibility.fetch_explicit_highway_extensions_for_ferry_stops",
            return_value=_empty_topology_result(),
        ) as topology:
            _nodes, _edges, audit = fetch_movement_pruned_highway_extensions_for_ferry_stops(
                _stop_audit("10"),
                pd.DataFrame(columns=["network_node_id", "survey_area_id"]),
                _candidates(40.0),
                max_network_transition_km=5.0,
            )
        self.assertTrue(audit.stop_coordinate_query_failed)
        self.assertEqual(audit.movement_impossible_stop_count, 0)
        self.assertEqual(topology.call_count, 1)

    def test_mixed_stops_only_prune_proven_impossible_ids(self):
        payload = {
            "elements": [
                {"type": "node", "id": 10, "lat": 35.0, "lon": 139.0},
                {"type": "node", "id": 20, "lat": 35.1, "lon": 139.0},
            ]
        }
        candidates = _candidates(35.03, radius_m=100.0)
        with patch(
            "acsp.osm_ferry_impossibility._post_overpass",
            return_value=payload,
        ), patch(
            "acsp.osm_ferry_impossibility.fetch_explicit_highway_extensions_for_ferry_stops",
            return_value=_empty_topology_result(),
        ) as topology:
            _nodes, _edges, audit = fetch_movement_pruned_highway_extensions_for_ferry_stops(
                _stop_audit("10", "20"),
                pd.DataFrame(columns=["network_node_id", "survey_area_id"]),
                candidates,
                max_network_transition_km=5.0,
            )
        eligible_stop_audit = topology.call_args.args[0]
        self.assertEqual(eligible_stop_audit["stop_node_id"].astype(str).tolist(), ["10"])
        self.assertEqual(audit.movement_impossible_stop_count, 1)
        self.assertEqual(audit.topology_eligible_stop_count, 1)


if __name__ == "__main__":
    unittest.main()
