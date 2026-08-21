import inspect
import unittest

import pandas as pd

from acsp.transport_reachability import build_patch_reachability_edges_from_transport_network


class TransportNetworkReachabilityTests(unittest.TestCase):
    def test_disconnected_network_blocks_nearby_candidate_transition(self):
        candidates = pd.DataFrame(
            {
                "candidate_patch_id": ["a", "b"],
                "survey_area_id": ["island", "island"],
                "latitude": [35.0, 35.0],
                "longitude": [139.0000, 139.0010],
            }
        )
        nodes = pd.DataFrame(
            {
                "network_node_id": ["n1", "n2"],
                "survey_area_id": ["island", "island"],
                "latitude": [35.0, 35.0],
                "longitude": [139.0000, 139.0010],
            }
        )
        network_edges = pd.DataFrame(columns=["from_node_id", "to_node_id", "distance_m"])
        patch_edges, attachments, audit = build_patch_reachability_edges_from_transport_network(
            candidates, nodes, network_edges, max_network_transition_km=10.0
        )
        self.assertTrue(patch_edges.empty)
        self.assertEqual(audit.attached_candidate_count, 2)
        self.assertEqual(audit.emitted_patch_edge_count, 0)
        self.assertFalse(audit.candidate_pair_straight_line_used)
        self.assertTrue(attachments["network_attached"].all())

    def test_explicit_ferry_edge_is_required_for_cross_area_transition(self):
        candidates = pd.DataFrame(
            {
                "candidate_patch_id": ["a", "b"],
                "survey_area_id": ["island-a", "island-b"],
                "latitude": [35.0, 35.5],
                "longitude": [139.0, 139.5],
            }
        )
        nodes = pd.DataFrame(
            {
                "network_node_id": ["port-a", "port-b"],
                "survey_area_id": ["island-a", "island-b"],
                "latitude": [35.0, 35.5],
                "longitude": [139.0, 139.5],
            }
        )
        no_ferry = pd.DataFrame(columns=["from_node_id", "to_node_id", "distance_m"])
        without, _, _ = build_patch_reachability_edges_from_transport_network(
            candidates, nodes, no_ferry, max_network_transition_km=20.0
        )
        self.assertTrue(without.empty)

        ferry = pd.DataFrame(
            {
                "from_node_id": ["port-a"],
                "to_node_id": ["port-b"],
                "distance_m": [12_000.0],
            }
        )
        with_ferry, _, audit = build_patch_reachability_edges_from_transport_network(
            candidates, nodes, ferry, max_network_transition_km=20.0
        )
        self.assertEqual(len(with_ferry), 1)
        self.assertEqual(with_ferry.loc[0, "from_patch_id"], "a")
        self.assertEqual(with_ferry.loc[0, "to_patch_id"], "b")
        self.assertAlmostEqual(with_ferry.loc[0, "network_path_distance_m"], 12_000.0)
        self.assertAlmostEqual(with_ferry.loc[0, "total_transition_distance_m"], 12_000.0)
        self.assertEqual(audit.network_edge_count, 1)

    def test_candidates_snap_only_to_transport_nodes_in_same_area(self):
        candidates = pd.DataFrame(
            {
                "candidate_patch_id": ["a", "b"],
                "survey_area_id": ["island-a", "island-b"],
                "latitude": [35.0, 35.0],
                "longitude": [139.0, 139.0001],
            }
        )
        nodes = pd.DataFrame(
            {
                "network_node_id": ["node-a"],
                "survey_area_id": ["island-a"],
                "latitude": [35.0],
                "longitude": [139.0],
            }
        )
        edges = pd.DataFrame(columns=["from_node_id", "to_node_id", "distance_m"])
        patch_edges, attachments, audit = build_patch_reachability_edges_from_transport_network(
            candidates, nodes, edges, max_network_transition_km=10.0
        )
        self.assertTrue(patch_edges.empty)
        self.assertTrue(attachments.loc[0, "network_attached"])
        self.assertFalse(attachments.loc[1, "network_attached"])
        self.assertEqual(audit.attached_candidate_count, 1)
        self.assertEqual(audit.unattached_candidate_count, 1)

    def test_off_network_access_distance_is_included_in_threshold(self):
        candidates = pd.DataFrame(
            {
                "candidate_patch_id": ["a", "b"],
                "survey_area_id": ["area", "area"],
                "latitude": [0.0, 0.0],
                "longitude": [0.0000, 0.0200],
            }
        )
        nodes = pd.DataFrame(
            {
                "network_node_id": ["n1", "n2"],
                "survey_area_id": ["area", "area"],
                "latitude": [0.0, 0.0],
                "longitude": [0.0050, 0.0150],
            }
        )
        edges = pd.DataFrame(
            {"from_node_id": ["n1"], "to_node_id": ["n2"], "distance_m": [1000.0]}
        )
        too_small, attachments, _ = build_patch_reachability_edges_from_transport_network(
            candidates, nodes, edges, max_network_transition_km=2.0
        )
        self.assertTrue(too_small.empty)
        self.assertGreater(attachments["off_network_access_distance_m"].sum(), 1000.0)

        enough, _, _ = build_patch_reachability_edges_from_transport_network(
            candidates, nodes, edges, max_network_transition_km=3.0
        )
        self.assertEqual(len(enough), 1)
        row = enough.iloc[0]
        self.assertAlmostEqual(
            row["total_transition_distance_m"],
            row["from_access_distance_m"]
            + row["network_path_distance_m"]
            + row["to_access_distance_m"],
        )

    def test_shortest_weighted_network_path_is_used(self):
        candidates = pd.DataFrame(
            {
                "candidate_patch_id": ["a", "b"],
                "survey_area_id": ["area", "area"],
                "latitude": [0.0, 0.0],
                "longitude": [0.0, 0.02],
            }
        )
        nodes = pd.DataFrame(
            {
                "network_node_id": ["n1", "n2", "n3"],
                "survey_area_id": ["area", "area", "area"],
                "latitude": [0.0, 0.0, 0.0],
                "longitude": [0.0, 0.01, 0.02],
            }
        )
        edges = pd.DataFrame(
            {
                "from_node_id": ["n1", "n1", "n2"],
                "to_node_id": ["n3", "n2", "n3"],
                "distance_m": [5000.0, 800.0, 800.0],
            }
        )
        patch_edges, _, _ = build_patch_reachability_edges_from_transport_network(
            candidates, nodes, edges, max_network_transition_km=2.0
        )
        self.assertEqual(len(patch_edges), 1)
        self.assertAlmostEqual(patch_edges.loc[0, "network_path_distance_m"], 1600.0)

    def test_duplicate_reverse_network_edges_use_minimum_distance(self):
        candidates = pd.DataFrame(
            {
                "candidate_patch_id": ["a", "b"],
                "survey_area_id": ["area", "area"],
                "latitude": [0.0, 0.0],
                "longitude": [0.0, 0.01],
            }
        )
        nodes = pd.DataFrame(
            {
                "network_node_id": ["n1", "n2"],
                "survey_area_id": ["area", "area"],
                "latitude": [0.0, 0.0],
                "longitude": [0.0, 0.01],
            }
        )
        edges = pd.DataFrame(
            {
                "from_node_id": ["n1", "n2", "n1"],
                "to_node_id": ["n2", "n1", "n2"],
                "distance_m": [1500.0, 900.0, 1200.0],
            }
        )
        patch_edges, _, audit = build_patch_reachability_edges_from_transport_network(
            candidates, nodes, edges, max_network_transition_km=1.0
        )
        self.assertEqual(audit.network_edge_count, 1)
        self.assertEqual(len(patch_edges), 1)
        self.assertAlmostEqual(patch_edges.loc[0, "network_path_distance_m"], 900.0)

    def test_unknown_transport_node_is_hard_error(self):
        candidates = pd.DataFrame(
            {
                "candidate_patch_id": ["a"],
                "survey_area_id": ["area"],
                "latitude": [0.0],
                "longitude": [0.0],
            }
        )
        nodes = pd.DataFrame(
            {
                "network_node_id": ["n1"],
                "survey_area_id": ["area"],
                "latitude": [0.0],
                "longitude": [0.0],
            }
        )
        edges = pd.DataFrame(
            {"from_node_id": ["n1"], "to_node_id": ["missing"], "distance_m": [1.0]}
        )
        with self.assertRaisesRegex(ValueError, "unknown node IDs"):
            build_patch_reachability_edges_from_transport_network(
                candidates, nodes, edges, max_network_transition_km=1.0
            )

    def test_api_has_only_network_movement_limit_not_design_budget(self):
        parameters = inspect.signature(build_patch_reachability_edges_from_transport_network).parameters
        self.assertIn("max_network_transition_km", parameters)
        self.assertNotIn("max_sites", parameters)
        self.assertNotIn("target_coverage", parameters)
        self.assertNotIn("survey_days", parameters)
        self.assertNotIn("budget", parameters)


if __name__ == "__main__":
    unittest.main()
