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

from diagnose_public_japan_96pair_environment_nearest_overlap_v1 import (
    cluster_hit_mask,
    summarize,
    zero_row,
)


class EnvironmentNearestOverlapTests(unittest.TestCase):
    def test_cluster_hit_mask_detects_only_hit_clusters(self):
        selected = pd.DataFrame({"latitude": [35.0], "longitude": [140.0]})
        clusters = [
            [(35.01, 140.0, "a")],
            [(36.0, 141.0, "b")],
        ]
        mask = cluster_hit_mask(selected, clusters, 2.0)
        self.assertEqual(mask.tolist(), [True, False])

    def test_summary_partitions_overlap_exactly(self):
        rows = []
        for pair_id in range(1, 97):
            pair = pd.Series({
                "pair_id": pair_id,
                "taxon_group": "plant" if pair_id <= 48 else "animal",
                "region_name": "x",
                "speciesKey": pair_id,
                "scientific_name": f"Species {pair_id}",
            })
            row = zero_row(pair, "no_target", "synthetic")
            if pair_id == 1:
                row.update({
                    "status": "classified",
                    "novel_recent_clusters": 10,
                    "candidate_count_k": 2,
                    "both_environment_and_nearest": 3,
                    "environment_only": 2,
                    "nearest_only": 1,
                    "neither": 4,
                    "classified_overlap_clusters": 10,
                })
            rows.append(row)
        summary = summarize(pd.DataFrame(rows))
        self.assertEqual(summary["declared_pairs"], 96)
        self.assertEqual(summary["classified_novel_clusters"], 10)
        self.assertEqual(summary["environment_recovered_clusters"], 5)
        self.assertEqual(summary["nearest_recovered_clusters"], 4)
        self.assertEqual(summary["environment_or_nearest_union_clusters"], 6)
        self.assertAlmostEqual(summary["environment_increment_over_nearest_absolute"], 0.2)

    def test_failures_are_not_relabeled_as_neither(self):
        pair = pd.Series({
            "pair_id": 1,
            "taxon_group": "plant",
            "region_name": "x",
            "speciesKey": 1,
            "scientific_name": "Species 1",
        })
        row = zero_row(pair, "generation_failure", "synthetic", novel_clusters=7)
        self.assertEqual(row["neither"], 0)
        self.assertEqual(row["classified_overlap_clusters"], 0)
        self.assertEqual(row["novel_recent_clusters"], 7)


if __name__ == "__main__":
    unittest.main()
