from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.benchmark_public_japan_96pair_temporal_anchor_v1 import (  # noqa: E402
    complete_link_clusters,
    evaluate_pair,
    normalize_record,
    summarize,
)


class PublicJapan96PairTemporalAnchorTests(unittest.TestCase):
    def pair(self, group="plant"):
        return pd.Series({
            "pair_id": 1,
            "taxon_group": group,
            "region_name": "Test region",
            "region_cell_index": 1,
            "speciesKey": 123,
            "scientific_name": "Test species",
            "west": 134.0,
            "south": 34.0,
            "east": 136.0,
            "north": 36.0,
        })

    def test_record_normalization_requires_frozen_species_key_and_precision(self):
        record = {
            "key": 1,
            "speciesKey": 123,
            "decimalLatitude": 35.0,
            "decimalLongitude": 135.0,
            "year": 2010,
            "coordinateUncertaintyInMeters": 100,
            "issues": [],
        }
        self.assertIsNotNone(normalize_record(record, 123))
        self.assertIsNone(normalize_record(dict(record, speciesKey=999), 123))
        missing = dict(record)
        missing.pop("coordinateUncertaintyInMeters")
        self.assertIsNone(normalize_record(missing, 123))

    def test_complete_link_does_not_chain(self):
        frame = pd.DataFrame({
            "gbif_key": ["a", "b", "c"],
            "latitude": [35.0, 35.003, 35.006],
            "longitude": [135.0, 135.0, 135.0],
        })
        clusters = complete_link_clusters(frame, 0.5)
        self.assertEqual(len(clusters), 2)

    def test_evaluate_pair_reports_2_5_10km_without_radius_tuning(self):
        records = pd.DataFrame([
            {"gbif_key": "h", "latitude": 35.0, "longitude": 135.0, "year": 2010},
            {"gbif_key": "r1", "latitude": 35.01, "longitude": 135.0, "year": 2022},
            {"gbif_key": "r2", "latitude": 35.06, "longitude": 135.0, "year": 2023},
            {"gbif_key": "r3", "latitude": 35.12, "longitude": 135.0, "year": 2024},
        ])
        row = evaluate_pair(self.pair(), records)
        self.assertEqual(row["novel_recent_clusters"], 3)
        self.assertEqual(row["novel_recent_within_2km"], 1)
        self.assertEqual(row["novel_recent_within_5km"], 1)
        self.assertEqual(row["novel_recent_within_10km"], 2)

    def test_summary_keeps_plant_animal_strata(self):
        rows = []
        for pair_id, group, count2 in [(1, "plant", 1), (2, "animal", 0)]:
            rows.append({
                "taxon_group": group,
                "strict_records": 5,
                "temporally_evaluable": True,
                "sentinel_no_historical_anchor": False,
                "novel_recent_clusters": 2,
                "novel_recent_within_2km": count2,
                "fraction_novel_recent_within_2km": count2 / 2,
                "novel_recent_within_5km": 1,
                "fraction_novel_recent_within_5km": 0.5,
                "novel_recent_within_10km": 2,
                "fraction_novel_recent_within_10km": 1.0,
            })
        audits = [
            {"raw_api_records_seen": 6, "strict_eligible_records": 5},
            {"raw_api_records_seen": 7, "strict_eligible_records": 5},
        ]
        result = summarize(rows, audits)
        self.assertEqual(result["declared_pairs"], 2)
        self.assertAlmostEqual(result["pooled_fraction_novel_recent_within_2km"], 0.25)
        self.assertAlmostEqual(result["plant_pooled_fraction_within_2km"], 0.5)
        self.assertAlmostEqual(result["animal_pooled_fraction_within_2km"], 0.0)
        self.assertFalse(result["new_independent_confirmation_claim"])


if __name__ == "__main__":
    unittest.main()
