from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

from benchmark_public_japan_cirsium_temporal_anchor_v1 import Cluster
from run_public_cirsium_alpine_structural_smoke_v1 import (
    cluster_medoid,
    select_myoko_slot_anchors,
    slot_novel_recent_clusters,
)


class PublicCirsiumAlpineStructuralSmokeTests(unittest.TestCase):
    def test_cluster_medoid_collapses_population_to_one_observed_member(self) -> None:
        cluster = Cluster(
            (
                (35.0, 139.00, "z"),
                (35.0, 139.01, "b"),
                (35.0, 139.02, "a"),
            )
        )
        medoid = cluster_medoid(cluster)
        self.assertAlmostEqual(float(medoid["longitude"]), 139.01)
        self.assertEqual(int(medoid["cluster_size"]), 3)

    def test_myoko_slot_selects_exact_frozen_count_by_reference_distance(self) -> None:
        medoids = pd.DataFrame(
            {
                "historical_cluster_id": ["H0000", "H0001", "H0002"],
                "historical_cluster_index": [0, 1, 2],
                "latitude": [36.89, 37.20, 36.95],
                "longitude": [138.11, 138.50, 138.15],
                "gbif_key": ["a", "b", "c"],
                "cluster_size": [1, 1, 1],
            }
        )
        selected = select_myoko_slot_anchors(
            medoids,
            reference_latitude=36.8913888889,
            reference_longitude=138.1136111111,
            count=2,
        )
        self.assertEqual(selected["historical_cluster_index"].astype(int).tolist(), [0, 2])

    def test_later_clusters_are_attributed_to_nearest_historical_population(self) -> None:
        historical_clusters = [
            Cluster(((35.0, 139.0, "h0"),)),
            Cluster(((35.0, 140.0, "h1"),)),
        ]
        medoids = pd.DataFrame(
            {
                "historical_cluster_id": ["H0000", "H0001"],
                "historical_cluster_index": [0, 1],
                "latitude": [35.0, 35.0],
                "longitude": [139.0, 140.0],
                "gbif_key": ["h0", "h1"],
            }
        )
        selected = medoids.iloc[[0]].copy()
        records = pd.DataFrame(
            {
                "gbif_key": ["slot", "offslot", "reobs"],
                "latitude": [35.0, 35.0, 35.0],
                "longitude": [139.01, 140.01, 139.001],
                "year": [2022, 2023, 2024],
            }
        )
        novel, audit = slot_novel_recent_clusters(
            records,
            historical_clusters=historical_clusters,
            medoids=medoids,
            selected_anchors=selected,
        )
        self.assertEqual(len(novel), 1)
        self.assertEqual(audit["recent_novel_clusters_in_slot"], 1)
        self.assertEqual(audit["recent_novel_clusters_outside_slot"], 1)
        self.assertEqual(audit["recent_reobserved_clusters"], 1)

    def test_preexecution_amendment_pins_parent_and_jma_reference(self) -> None:
        amendment = json.loads(
            (ROOT / "validation" / "public_cirsium_structural_three_family_smoke_anchor_slot_amendment_v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(amendment["structural_layer_execution_before_amendment"])
        self.assertEqual(
            amendment["parent_contract_blob_sha"],
            "34d6d7000de30a4c9bfbf8d501eae03c2ac9af31",
        )
        slot = amendment["cir04_myoko_slot"]
        self.assertEqual(slot["frozen_primary_anchor_count"], 4)
        self.assertAlmostEqual(slot["public_reference"]["latitude"], 36.8913888889)
        self.assertAlmostEqual(slot["public_reference"]["longitude"], 138.1136111111)


if __name__ == "__main__":
    unittest.main()
