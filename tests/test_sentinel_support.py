from __future__ import annotations

import unittest

import pandas as pd

from acsp.sentinel_support import clip_to_uncertainty_footprint_union, uncertainty_footprint_support


class SentinelSupportTests(unittest.TestCase):
    def candidates(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "candidate_cell_id": ["a", "b", "c"],
                "latitude": [35.000, 35.010, 35.050],
                "longitude": [135.000, 135.010, 135.050],
            }
        )

    def evidence(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "source_occurrence_id": ["r1", "r2", "dup"],
                "latitude": [35.000, 35.010, 35.000],
                "longitude": [135.000, 135.010, 135.000],
                "coordinate_uncertainty_m": [2000.0, 3000.0, 2000.0],
            }
        )

    def test_support_uses_declared_footprint_overlap_without_center_distance_preference(self) -> None:
        support, union, audit = uncertainty_footprint_support(self.candidates(), self.evidence())
        self.assertEqual(audit.input_record_count, 3)
        self.assertEqual(audit.unique_footprint_count, 2)
        self.assertFalse(audit.distance_preference_inside_footprint)
        self.assertTrue(union.iloc[0])
        self.assertTrue(union.iloc[1])
        self.assertFalse(union.iloc[2])
        self.assertTrue(support.between(0, 1).all())

    def test_clip_adds_broad_support_and_removes_outside_cells(self) -> None:
        clipped, audit = clip_to_uncertainty_footprint_union(self.candidates(), self.evidence())
        self.assertEqual(len(clipped), audit.candidates_inside_union)
        self.assertIn("broad_sentinel_support", clipped)
        self.assertTrue(clipped["broad_sentinel_support"].between(0, 1).all())

    def test_unknown_uncertainty_cannot_form_kernel(self) -> None:
        evidence = self.evidence()
        evidence.loc[0, "coordinate_uncertainty_m"] = None
        with self.assertRaises(ValueError):
            uncertainty_footprint_support(self.candidates(), evidence)

    def test_local_precision_record_cannot_enter_broad_uncertainty_kernel(self) -> None:
        evidence = self.evidence()
        evidence.loc[0, "coordinate_uncertainty_m"] = 500.0
        with self.assertRaises(ValueError):
            uncertainty_footprint_support(self.candidates(), evidence)

    def test_field_outcome_contamination_fails_closed(self) -> None:
        candidates = self.candidates().assign(field_outcome_state="SEARCH_COMPLETED_NOT_DETECTED")
        with self.assertRaises(ValueError):
            uncertainty_footprint_support(candidates, self.evidence())


if __name__ == "__main__":
    unittest.main()
