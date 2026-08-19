import tempfile
import unittest
from pathlib import Path

import pandas as pd

from acsp.travel_matrix import normalize_travel_time_matrix, read_travel_time_matrix


class MovementEdgeNormalizationTests(unittest.TestCase):
    def test_undirected_edges_are_mirrored(self):
        edges = pd.DataFrame([
            {
                "from_id": "hub",
                "to_id": 1,
                "travel_minutes": 12,
                "distance_km": 3.5,
                "mode": "road",
            }
        ])
        normalized = normalize_travel_time_matrix(edges, undirected=True)
        self.assertEqual(
            set(map(tuple, normalized[["from_id", "to_id"]].to_numpy())),
            {("hub", "1"), ("1", "hub")},
        )
        self.assertTrue((normalized["travel_minutes"] == 12).all())

    def test_conflicting_reverse_costs_are_rejected_for_undirected_input(self):
        edges = pd.DataFrame([
            {"from_id": "hub", "to_id": "1", "travel_minutes": 12, "mode": "road"},
            {"from_id": "1", "to_id": "hub", "travel_minutes": 13, "mode": "road"},
        ])
        with self.assertRaisesRegex(ValueError, "conflicting reverse travel times"):
            normalize_travel_time_matrix(edges, undirected=True)

    def test_unavailable_edges_are_removed_and_missing_edges_stay_missing(self):
        edges = pd.DataFrame([
            {"from_id": "hub", "to_id": "a", "travel_minutes": 10, "mode": "walk", "available": True},
            {"from_id": "a", "to_id": "hub", "travel_minutes": 11, "mode": "walk", "available": False},
        ])
        normalized = normalize_travel_time_matrix(edges)
        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized.iloc[0]["from_id"], "hub")
        self.assertEqual(normalized.iloc[0]["to_id"], "a")

    def test_read_preserves_directed_sparse_graph(self):
        edges = pd.DataFrame([
            {"from_id": "hub", "to_id": "a", "travel_minutes": 10, "mode": "walk"},
            {"from_id": "a", "to_id": "b", "travel_minutes": 8, "mode": "trail"},
        ])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "edges.csv"
            edges.to_csv(path, index=False)
            loaded = read_travel_time_matrix(path)
        self.assertEqual(len(loaded), 2)
        self.assertNotIn(("a", "hub"), set(map(tuple, loaded[["from_id", "to_id"]].to_numpy())))


if __name__ == "__main__":
    unittest.main()
