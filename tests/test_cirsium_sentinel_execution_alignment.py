import json
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


class CirsiumSentinelExecutionAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.cohort = pd.read_csv(ROOT / "validation" / "cirsium_aza3_prospective_validation_cohort_v1.csv")
        self.requirements = pd.read_csv(ROOT / "validation" / "cirsium_private_frame_source_requirements_v1.csv")
        self.execution = json.loads(
            (ROOT / "validation" / "cirsium_structural_selector_execution_freeze_v1.json").read_text(encoding="utf-8")
        )

    def test_sentinel_subregime_counts_and_source_requirements_are_aligned(self):
        sentinel = self.cohort[self.cohort["occurrence_problem_class"].eq("SENTINEL")].set_index("cohort_unit_id")
        req = self.requirements.set_index("cohort_unit_id")
        self.assertEqual(
            sentinel["sentinel_subregime"].to_dict(),
            {
                "CIR02": "UNCERTAINTY_FOOTPRINT",
                "CIR06": "LEGACY_RANGE_CONTEXT",
                "CIR12": "UNCERTAINTY_FOOTPRINT",
                "CIR13": "COARSE_RANGE_CONTEXT",
            },
        )
        for unit, row in sentinel.iterrows():
            requires = str(req.loc[unit, "requires_broad_sentinel_support"]).strip().lower() == "true"
            self.assertEqual(requires, row["sentinel_subregime"] == "UNCERTAINTY_FOOTPRINT", unit)

    def test_execution_method_sets_match_frozen_subregimes(self):
        methods = self.execution["ranking_method_sets"]["STRUCTURAL_SENTINEL"]
        self.assertEqual(
            methods["UNCERTAINTY_FOOTPRINT"],
            ["STRUCTURAL_SUPPORT", "UNCERTAINTY_FOOTPRINT_SUPPORT", "DETERMINISTIC_SPATIAL_BALANCE"],
        )
        self.assertEqual(
            methods["LEGACY_RANGE_CONTEXT"],
            ["STRUCTURAL_SUPPORT", "DETERMINISTIC_SPATIAL_BALANCE"],
        )
        self.assertEqual(
            methods["COARSE_RANGE_CONTEXT"],
            ["STRUCTURAL_SUPPORT", "DETERMINISTIC_SPATIAL_BALANCE"],
        )

    def test_cohort_comparator_text_matches_subregime(self):
        sentinel = self.cohort[self.cohort["occurrence_problem_class"].eq("SENTINEL")]
        for row in sentinel.itertuples(index=False):
            if row.sentinel_subregime == "UNCERTAINTY_FOOTPRINT":
                self.assertIn("UNCERTAINTY_FOOTPRINT_SUPPORT", row.comparators)
            else:
                self.assertEqual(row.comparators, "DETERMINISTIC_SPATIAL_BALANCE")


if __name__ == "__main__":
    unittest.main()
