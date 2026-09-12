from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))

from diagnose_public_japan_cirsium_temporal_anchor_by_region_v1 import (  # noqa: E402
    evaluate_species_regions,
    inside_region,
    summarize_region_units,
)


class PublicJapanCirsiumTemporalAnchorRegionDiagnosticTests(unittest.TestCase):
    def test_inside_region_clips_without_changing_coordinates(self):
        records = pd.DataFrame(
            [
                {"gbif_key": "a", "latitude": 35.0, "longitude": 139.0, "year": 2010, "coordinate_uncertainty_m": 10},
                {"gbif_key": "b", "latitude": 40.0, "longitude": 140.0, "year": 2010, "coordinate_uncertainty_m": 10},
            ]
        )
        region = {"region_name": "test", "west": 138.5, "south": 34.5, "east": 139.5, "north": 35.5}
        clipped = inside_region(records, region)
        self.assertEqual(list(clipped["gbif_key"]), ["a"])
        self.assertEqual(float(clipped.iloc[0]["latitude"]), 35.0)

    def test_same_species_can_be_local_in_one_region_and_sentinel_in_another(self):
        records = pd.DataFrame(
            [
                {"gbif_key": "h", "latitude": 35.0, "longitude": 139.0, "year": 2010, "coordinate_uncertainty_m": 10},
                {"gbif_key": "r1", "latitude": 35.01, "longitude": 139.0, "year": 2022, "coordinate_uncertainty_m": 10},
                {"gbif_key": "r2", "latitude": 40.0, "longitude": 140.0, "year": 2023, "coordinate_uncertainty_m": 10},
            ]
        )
        regions = [
            {"region_name": "south", "west": 138.0, "south": 34.0, "east": 140.0, "north": 36.0},
            {"region_name": "north", "west": 139.0, "south": 39.0, "east": 141.0, "north": 41.0},
        ]
        rows = evaluate_species_regions("Cirsium testii", records, regions)
        by_region = {row["region_name"]: row for row in rows}
        self.assertTrue(by_region["south"]["temporally_evaluable"])
        self.assertTrue(by_region["north"]["sentinel_no_historical_anchor"])

    def test_summary_compares_regional_and_parent_without_overwriting_parent(self):
        rows = [
            {
                "eligible_records": 5,
                "temporally_evaluable": True,
                "sentinel_no_historical_anchor": False,
                "novel_recent_clusters": 2,
                "novel_recent_within_2km": 1,
                "novel_recent_within_5km": 2,
                "fraction_novel_recent_within_2km": 0.5,
                "fraction_novel_recent_within_5km": 1.0,
            },
            {
                "eligible_records": 2,
                "temporally_evaluable": False,
                "sentinel_no_historical_anchor": True,
                "novel_recent_clusters": 1,
                "novel_recent_within_2km": 0,
                "novel_recent_within_5km": 0,
                "fraction_novel_recent_within_2km": None,
                "fraction_novel_recent_within_5km": None,
            },
        ]
        parent = {
            "pooled_fraction_novel_recent_within_2km": 0.1,
            "pooled_fraction_novel_recent_within_5km": 0.2,
        }
        summary = summarize_region_units(rows, parent)
        self.assertEqual(summary["temporally_evaluable_units"], 1)
        self.assertAlmostEqual(summary["pooled_fraction_novel_recent_within_2km"], 0.5)
        self.assertAlmostEqual(summary["regional_minus_national_2km"], 0.4)
        self.assertEqual(summary["parent_national_fraction_within_2km"], 0.1)


if __name__ == "__main__":
    unittest.main()
