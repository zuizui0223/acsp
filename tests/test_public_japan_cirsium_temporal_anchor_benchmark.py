from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.benchmark_public_japan_cirsium_temporal_anchor_v1 import (  # noqa: E402
    deterministic_complete_link_greedy,
    evaluate_species,
    normalize_record,
    summarize,
)


class PublicJapanCirsiumTemporalAnchorBenchmarkTests(unittest.TestCase):
    def test_normalize_record_is_strict_about_species_uncertainty_and_geospatial_issue(self):
        base = {
            "key": 1,
            "species": "Cirsium testii",
            "occurrenceStatus": "PRESENT",
            "decimalLatitude": 35.0,
            "decimalLongitude": 135.0,
            "year": 2010,
            "coordinateUncertaintyInMeters": 50,
            "issues": [],
        }
        self.assertIsNotNone(normalize_record(base, "Cirsium testii"))
        wrong_species = dict(base, species="Cirsium other")
        self.assertIsNone(normalize_record(wrong_species, "Cirsium testii"))
        missing_uncertainty = dict(base)
        missing_uncertainty.pop("coordinateUncertaintyInMeters")
        self.assertIsNone(normalize_record(missing_uncertainty, "Cirsium testii"))
        geospatial_issue = dict(base, issues=["COUNTRY_COORDINATE_MISMATCH"])
        self.assertIsNone(normalize_record(geospatial_issue, "Cirsium testii"))

    def test_complete_link_clustering_prevents_chain_bridge(self):
        # Adjacent gaps are <0.5 km but endpoints are >0.5 km, so a single-link
        # chain would merge all three while complete-link greedy does not.
        frame = pd.DataFrame(
            {
                "gbif_key": ["a", "b", "c"],
                "latitude": [35.0, 35.003, 35.006],
                "longitude": [135.0, 135.0, 135.0],
            }
        )
        clusters = deterministic_complete_link_greedy(frame, 0.5)
        self.assertEqual(len(clusters), 2)
        self.assertEqual(sorted(cluster.size for cluster in clusters), [1, 2])

    def test_temporal_evaluation_separates_reobservation_local_and_detached(self):
        frame = pd.DataFrame(
            [
                {"gbif_key": "h1", "latitude": 35.0000, "longitude": 135.0000, "year": 2010, "coordinate_uncertainty_m": 20},
                {"gbif_key": "h2", "latitude": 35.1000, "longitude": 135.1000, "year": 2015, "coordinate_uncertainty_m": 20},
                # re-observation of h1
                {"gbif_key": "r1", "latitude": 35.0010, "longitude": 135.0000, "year": 2022, "coordinate_uncertainty_m": 20},
                # novel but within ~1.1 km of h1
                {"gbif_key": "r2", "latitude": 35.0100, "longitude": 135.0000, "year": 2023, "coordinate_uncertainty_m": 20},
                # detached >5 km from either historical anchor
                {"gbif_key": "r3", "latitude": 35.2500, "longitude": 135.2500, "year": 2024, "coordinate_uncertainty_m": 20},
            ]
        )
        result = evaluate_species("Cirsium testii", frame)
        self.assertEqual(result["historical_clusters"], 2)
        self.assertEqual(result["recent_clusters"], 3)
        self.assertEqual(result["recent_reobserved_clusters_le_0_5km"], 1)
        self.assertEqual(result["novel_recent_clusters"], 2)
        self.assertEqual(result["novel_recent_within_2km"], 1)
        self.assertEqual(result["novel_recent_within_5km"], 1)
        self.assertEqual(result["novel_recent_detached_gt_5km"], 1)

    def test_summary_is_species_cluster_weighted_not_record_weighted(self):
        rows = [
            {
                "eligible_records": 100,
                "temporally_evaluable": True,
                "sentinel_no_historical_anchor": False,
                "novel_recent_clusters": 2,
                "novel_recent_within_2km": 1,
                "novel_recent_within_5km": 2,
                "fraction_novel_recent_within_2km": 0.5,
                "fraction_novel_recent_within_5km": 1.0,
            },
            {
                "eligible_records": 5,
                "temporally_evaluable": True,
                "sentinel_no_historical_anchor": False,
                "novel_recent_clusters": 1,
                "novel_recent_within_2km": 1,
                "novel_recent_within_5km": 1,
                "fraction_novel_recent_within_2km": 1.0,
                "fraction_novel_recent_within_5km": 1.0,
            },
        ]
        audits = [
            {"raw_api_records_seen": 110, "eligible_records": 100},
            {"raw_api_records_seen": 7, "eligible_records": 5},
        ]
        summary = summarize(rows, audits)
        self.assertAlmostEqual(summary["pooled_fraction_novel_recent_within_2km"], 2 / 3)
        self.assertAlmostEqual(summary["species_level_fraction_within_2km_median"], 0.75)
        self.assertEqual(summary["gbif_eligible_records"], 105)


if __name__ == "__main__":
    unittest.main()
