from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "research") not in sys.path:
    sys.path.insert(0, str(ROOT / "research"))

from compare_public_japan_96pair_environment_vs_distance_v1 import (
    recovery_fraction,
    select_nearest_known,
    select_spatial_balance,
    stable_candidate_key,
    summarize,
    zero_result,
)


class PublicJapan96PairEnvironmentVsDistanceTests(unittest.TestCase):
    def test_stable_candidate_key_is_coordinate_and_pair_specific(self):
        a = stable_candidate_key(1, 35.0, 140.0)
        b = stable_candidate_key(1, 35.0, 140.0)
        c = stable_candidate_key(2, 35.0, 140.0)
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_nearest_known_excludes_trivial_reobservation_and_returns_exact_k(self):
        historical = pd.DataFrame({"latitude": [35.0], "longitude": [140.0]})
        surface = pd.DataFrame(
            {
                "latitude": [35.0, 35.006, 35.012, 35.020],
                "longitude": [140.0, 140.0, 140.0, 140.0],
            }
        )
        selected = select_nearest_known(surface, historical, pair_id=7, count=2, exclusion_km=0.5)
        self.assertEqual(len(selected), 2)
        self.assertTrue((selected["_nearest_historical_km"] > 0.5).all())
        self.assertLessEqual(selected["_nearest_historical_km"].iloc[0], selected["_nearest_historical_km"].iloc[1])

    def test_spatial_balance_is_deterministic_unique_and_exact_count(self):
        surface = pd.DataFrame(
            {
                "latitude": [35.0, 35.0, 35.1, 35.1, 35.05],
                "longitude": [140.0, 140.1, 140.0, 140.1, 140.05],
            }
        )
        one = select_spatial_balance(surface, pair_id=4, count=3)
        two = select_spatial_balance(surface, pair_id=4, count=3)
        self.assertEqual(len(one), 3)
        self.assertEqual(len(one.drop_duplicates(["latitude", "longitude"])), 3)
        self.assertEqual(one[["latitude", "longitude"]].to_dict("records"), two[["latitude", "longitude"]].to_dict("records"))

    def test_recovery_fraction_uses_any_member_of_novel_cluster(self):
        selected = pd.DataFrame({"latitude": [35.0], "longitude": [140.0]})
        clusters = [
            [(35.005, 140.0, "a"), (35.006, 140.0, "b")],
            [(36.0, 141.0, "c")],
        ]
        self.assertEqual(recovery_fraction(selected, clusters, 1.0), 0.5)

    def test_summary_preserves_all_96_declared_pairs(self):
        rows = []
        for pair_id in range(1, 97):
            pair = pd.Series(
                {
                    "pair_id": pair_id,
                    "taxon_group": "plant" if pair_id <= 48 else "animal",
                    "region_name": "x",
                    "speciesKey": pair_id,
                    "scientific_name": f"Species {pair_id}",
                }
            )
            rows.append(zero_result(pair, "failure_zero", "synthetic"))
        summary = summarize(pd.DataFrame(rows))
        self.assertEqual(summary["declared_pairs"], 96)
        self.assertEqual(summary["compared_pairs"], 0)
        self.assertFalse(summary["development_nomination_gate"]["passed"])


if __name__ == "__main__":
    unittest.main()
