from __future__ import annotations

import unittest

import pandas as pd

from acsp.structural_selector import select_structural_support


class StructuralSelectorTests(unittest.TestCase):
    def test_selects_exact_count_by_support_then_stable_id(self) -> None:
        frame = pd.DataFrame(
            {
                "candidate_cell_id": [4, 2, 3, 1],
                "structural_support": [0.8, 0.9, 0.9, 0.1],
            }
        )
        selected, audit = select_structural_support(
            frame,
            count=2,
            feature_family="ALPINE_TOPOGRAPHIC_STRUCTURE",
            support_provenance_id="frozen-support-v1",
        )
        self.assertEqual(selected["candidate_cell_id"].tolist(), [2, 3])
        self.assertEqual(audit.selected_count, 2)
        self.assertFalse(audit.field_outcomes_used)
        self.assertFalse(audit.post_outcome_feature_switch_allowed)

    def test_count_larger_than_frame_returns_all_without_duplication(self) -> None:
        frame = pd.DataFrame(
            {"candidate_cell_id": [1, 2], "structural_support": [0.2, 0.8]}
        )
        selected, audit = select_structural_support(
            frame,
            count=5,
            feature_family="OPEN_GRASSLAND_STRUCTURE",
            support_provenance_id="frozen-support-v1",
        )
        self.assertEqual(selected["candidate_cell_id"].tolist(), [2, 1])
        self.assertEqual(audit.requested_count, 5)
        self.assertEqual(audit.selected_count, 2)

    def test_field_outcome_like_columns_fail_closed(self) -> None:
        frame = pd.DataFrame(
            {
                "candidate_cell_id": [1, 2],
                "structural_support": [0.2, 0.8],
                "detected": [False, True],
            }
        )
        with self.assertRaises(ValueError):
            select_structural_support(
                frame,
                count=1,
                feature_family="WETLAND_MOISTURE_STRUCTURE",
                support_provenance_id="frozen-support-v1",
            )

    def test_support_must_be_complete_and_bounded(self) -> None:
        bad_frames = [
            pd.DataFrame({"candidate_cell_id": [1], "structural_support": [None]}),
            pd.DataFrame({"candidate_cell_id": [1], "structural_support": [1.2]}),
        ]
        for frame in bad_frames:
            with self.subTest(frame=frame.to_dict()):
                with self.assertRaises(ValueError):
                    select_structural_support(
                        frame,
                        count=1,
                        feature_family="FOREST_EDGE_STRUCTURE",
                        support_provenance_id="frozen-support-v1",
                    )

    def test_support_provenance_is_required(self) -> None:
        frame = pd.DataFrame({"candidate_cell_id": [1], "structural_support": [0.5]})
        with self.assertRaises(ValueError):
            select_structural_support(
                frame,
                count=1,
                feature_family="COASTAL_ISLAND_STRUCTURE",
                support_provenance_id="",
            )


if __name__ == "__main__":
    unittest.main()
