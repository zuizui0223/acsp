"""Offline tests for the Campanula development loop.

These use a synthetic candidate pool so the harness stays testable in
environments with no GBIF or GSI access.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

import campanula_development_loop as loop


def synthetic_pool() -> pd.DataFrame:
    """Two islands, four candidates each, with a known best-scoring row."""
    rows = []
    for area, base_lat, base_lon in (("oshima", 34.75, 139.40), ("toshima", 34.52, 139.27)):
        for i in range(4):
            rows.append(
                {
                    "site_id": f"{area}-{i}",
                    "survey_area_id": area,
                    "latitude": base_lat + i * 0.01,
                    "longitude": base_lon + i * 0.01,
                    loop.SCORE_COL: 1.0 - i * 0.1,
                }
            )
    return pd.DataFrame(rows)


def synthetic_locations() -> pd.DataFrame:
    """Positive rows that sit on the top-scoring candidate of each island."""
    return pd.DataFrame(
        [
            {"detection_source_id": "a", "island": "oshima", "latitude": 34.7500, "longitude": 139.4000},
            {"detection_source_id": "b", "island": "oshima", "latitude": 34.7501, "longitude": 139.4001},
            {"detection_source_id": "c", "island": "toshima", "latitude": 34.5200, "longitude": 139.2700},
        ]
    )


class ClusteringTests(unittest.TestCase):
    def test_nearby_rows_collapse_into_one_cluster(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "locations.csv"
            synthetic_locations().to_csv(path, index=False)
            clusters = loop.load_detection_clusters(path)
        # The two Oshima rows are ~14 m apart and collapse; Toshima stays separate.
        self.assertEqual(len(clusters), 2)

    def test_real_field_file_yields_nineteen_clusters(self) -> None:
        if not loop.LOCATIONS.exists():
            self.skipTest("field locations file is absent")
        clusters = loop.load_detection_clusters(loop.LOCATIONS)
        self.assertEqual(len(clusters), 19)


class StrategyTests(unittest.TestCase):
    def test_every_registered_strategy_respects_the_budget(self) -> None:
        pool = synthetic_pool()
        for name, strategy in loop.STRATEGIES.items():
            with self.subTest(strategy=name):
                selected = strategy(pool, 3, 1.0)
                self.assertEqual(len(selected), 3)
                self.assertTrue(set(selected["site_id"]).issubset(set(pool["site_id"])))

    def test_local_topk_takes_the_highest_scores(self) -> None:
        selected = loop.strategy_local_topk(synthetic_pool(), 2, 1.0)
        self.assertEqual(list(selected["site_id"]), ["oshima-0", "toshima-0"])

    def test_area_balanced_covers_both_islands_before_repeating(self) -> None:
        selected = loop.strategy_area_balanced(synthetic_pool(), 2, 1.0)
        self.assertEqual(set(selected["survey_area_id"]), {"oshima", "toshima"})


class EvaluationTests(unittest.TestCase):
    def test_recall_and_random_baseline_are_reported_for_every_radius(self) -> None:
        pool = synthetic_pool()
        clusters = loop.load_detection_clusters_from_frame(synthetic_locations())
        selected = loop.strategy_local_topk(pool, 2, 1.0)
        result = loop.evaluate(pool, selected, clusters, iterations=200, seed=1)
        summary = result["summary"]
        self.assertEqual(len(summary), len(loop.REPORT_RADII_KM))
        # Both detections sit on selected candidates, so 1 km recall is complete.
        primary = summary[summary["radius_km"] == loop.PRIMARY_RADIUS_KM].iloc[0]
        self.assertEqual(float(primary["detection_recall"]), 1.0)
        self.assertEqual(len(result["benchmark"]), len(loop.REPORT_RADII_KM))

    def test_per_area_breakdown_lists_each_island(self) -> None:
        pool = synthetic_pool()
        clusters = loop.load_detection_clusters_from_frame(synthetic_locations())
        selected = loop.strategy_local_topk(pool, 2, 1.0)
        result = loop.evaluate(pool, selected, clusters, iterations=200, seed=1)
        misses = loop.per_area_misses(result["recovery"], loop.PRIMARY_RADIUS_KM)
        self.assertEqual(set(misses.iloc[:, 0]), {"oshima", "toshima"})


class GuardTests(unittest.TestCase):
    def test_missing_cache_explains_how_to_build_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as ctx:
                loop.load_pool(Path(tmp))
        self.assertIn("cache_campanula_development_data", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
