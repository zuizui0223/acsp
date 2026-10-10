from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.diagnose_public_japan_cirsium_gbif_precision_attrition_v1 import (  # noqa: E402
    classify_record,
    diagnose_species,
    summarize,
)


class PublicJapanCirsiumGbifPrecisionAttritionTests(unittest.TestCase):
    def base(self):
        return {
            "key": 1,
            "species": "Cirsium testii",
            "decimalLatitude": 35.0,
            "decimalLongitude": 135.0,
            "year": 2010,
            "coordinateUncertaintyInMeters": 100,
            "issues": [],
        }

    def test_ordered_attrition_classes_are_fail_closed(self):
        base = self.base()
        self.assertEqual(classify_record(base, "Cirsium testii"), "eligible_declared_uncertainty_le_1000m")
        wrong = dict(base, species="Cirsium other")
        self.assertEqual(classify_record(wrong, "Cirsium testii"), "exact_species_field_mismatch")
        missing = dict(base)
        missing.pop("coordinateUncertaintyInMeters")
        self.assertEqual(classify_record(missing, "Cirsium testii"), "missing_declared_coordinate_uncertainty")
        broad = dict(base, coordinateUncertaintyInMeters=5000)
        self.assertEqual(classify_record(broad, "Cirsium testii"), "declared_coordinate_uncertainty_gt_1000m")

    def test_diagnose_species_counts_temporal_strict_records(self):
        historical = self.base()
        recent = dict(self.base(), key=2, year=2023)
        missing = dict(self.base(), key=3, year=2022)
        missing.pop("coordinateUncertaintyInMeters")
        row = diagnose_species("Cirsium testii", [historical, recent, missing])
        self.assertEqual(row["raw_records"], 3)
        self.assertEqual(row["eligible_declared_uncertainty_le_1000m"], 2)
        self.assertEqual(row["missing_declared_coordinate_uncertainty"], 1)
        self.assertEqual(row["strict_historical_records"], 1)
        self.assertEqual(row["strict_recent_records"], 1)
        self.assertTrue(row["strict_both_periods"])

    def test_summary_preserves_parent_precision_rule(self):
        rows = [
            {
                "raw_records": 4,
                "exact_species_field_mismatch": 0,
                "invalid_or_missing_coordinate_or_year": 0,
                "forbidden_geospatial_issue": 0,
                "missing_declared_coordinate_uncertainty": 2,
                "invalid_declared_coordinate_uncertainty": 0,
                "declared_coordinate_uncertainty_gt_1000m": 1,
                "eligible_declared_uncertainty_le_1000m": 1,
                "strict_historical_records": 1,
                "strict_recent_records": 0,
                "strict_both_periods": False,
            },
            {
                "raw_records": 2,
                "exact_species_field_mismatch": 0,
                "invalid_or_missing_coordinate_or_year": 0,
                "forbidden_geospatial_issue": 0,
                "missing_declared_coordinate_uncertainty": 0,
                "invalid_declared_coordinate_uncertainty": 0,
                "declared_coordinate_uncertainty_gt_1000m": 0,
                "eligible_declared_uncertainty_le_1000m": 2,
                "strict_historical_records": 1,
                "strict_recent_records": 1,
                "strict_both_periods": True,
            },
        ]
        result = summarize(rows)
        self.assertEqual(result["raw_records"], 6)
        self.assertAlmostEqual(result["fraction_missing_declared_coordinate_uncertainty"], 2 / 6)
        self.assertAlmostEqual(result["fraction_strict_eligible"], 3 / 6)
        self.assertEqual(result["species_with_both_periods"], 1)
        self.assertFalse(result["parent_precision_rule_changed"])


if __name__ == "__main__":
    unittest.main()
