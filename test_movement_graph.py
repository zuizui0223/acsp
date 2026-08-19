import unittest

import pandas as pd

from acsp.movement_graph import dijkstra_minutes, hub_roundtrip_table


class MovementGraphTests(unittest.TestCase):
    def test_dijkstra_uses_only_explicit_edges_and_intermediate_nodes(self):
        edges = pd.DataFrame({
            "from_id": ["hub", "junction", "site"],
            "to_id": ["junction", "site", "hub"],
            "travel_minutes": [5, 7, 20],
            "mode": ["road", "trail", "road"],
        })
        distances = dijkstra_minutes(edges, "hub")
        self.assertEqual(distances["site"], 12.0)
        self.assertNotIn("missing", distances)

    def test_roundtrip_requires_both_directed_paths(self):
        edges = pd.DataFrame({
            "from_id": ["hub", "junction", "oneway"],
            "to_id": ["junction", "reachable", "hub"],
            "travel_minutes": [5, 5, 9],
            "mode": ["walk", "walk", "walk"],
        })
        table = hub_roundtrip_table(
            edges,
            hub_id="hub",
            site_ids=["reachable", "oneway"],
            allowed_modes=["walk"],
        ).set_index("site_id")
        self.assertFalse(bool(table.loc["reachable", "roundtrip_reachable"]))
        self.assertFalse(bool(table.loc["oneway", "roundtrip_reachable"]))

    def test_disallowed_mode_is_not_a_fallback_route(self):
        edges = pd.DataFrame({
            "from_id": ["hub", "island", "hub", "walkable"],
            "to_id": ["island", "hub", "walkable", "hub"],
            "travel_minutes": [1, 1, 10, 10],
            "mode": ["flight", "flight", "walk", "walk"],
        })
        table = hub_roundtrip_table(
            edges,
            hub_id="hub",
            site_ids=["island", "walkable"],
            allowed_modes=["walk"],
        ).set_index("site_id")
        self.assertFalse(bool(table.loc["island", "roundtrip_reachable"]))
        self.assertTrue(bool(table.loc["walkable", "roundtrip_reachable"]))
        self.assertEqual(float(table.loc["walkable", "roundtrip_minutes"]), 20.0)


if __name__ == "__main__":
    unittest.main()
