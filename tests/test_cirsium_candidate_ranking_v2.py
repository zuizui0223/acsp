from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))

from freeze_cirsium_candidate_patch_ranking_v2 import rank_unit  # noqa: E402


class CirsiumCandidateRankingV2Tests(unittest.TestCase):
    def structural_local_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "candidate_cell_id": ["a", "b", "c"],
                "latitude": [35.0, 35.01, 35.02],
                "longitude": [135.0, 135.01, 135.02],
                "nearest_anchor_km": [1.5, 0.7, 1.0],
                "open_land_score": [0.9, 0.5, 0.7],
                "fragment_continuity_score": [0.8, 0.8, 0.6],
                "terrain_context_score": [0.7, 0.9, 0.6],
            }
        )

    def cohort(
        self,
        regime: str = "LOCAL_CONTINUATION",
        arm: str = "STRUCTURAL_LOCAL",
        sentinel_subregime: str = "NOT_APPLICABLE",
    ) -> dict[str, str]:
        return {
            "cohort_unit_id": "TEST01",
            "aza3_slot_id": "P0_TEST",
            "species_binomial": "Cirsium testii",
            "occurrence_problem_class": regime,
            "sentinel_subregime": sentinel_subregime,
            "structural_feature_family": "OPEN_GRASSLAND_STRUCTURE" if arm != "SPATIAL_BASELINE_ONLY" else "GENERAL_SPATIAL_BASELINE_ONLY",
            "anchor_replication_class": "MULTIPLE_PRIMARY_ANCHORS" if regime == "LOCAL_CONTINUATION" else "ZERO_PRIMARY_ANCHOR",
            "method_arm": arm,
        }

    def test_local_unit_freezes_full_three_method_rankings(self) -> None:
        frame = self.structural_local_frame()
        rows = rank_unit(
            frame,
            cohort_row=self.cohort(),
            support_provenance_id="sha256:demo",
            salt=b"0123456789abcdef",
        )
        result = pd.DataFrame(rows)
        self.assertEqual(set(result["frozen_method"]), {"STRUCTURAL_SUPPORT", "ANNULAR_NEAREST_KNOWN", "DETERMINISTIC_SPATIAL_BALANCE"})
        for _, group in result.groupby("frozen_method"):
            self.assertEqual(sorted(group["decision_rank"].tolist()), [1, 2, 3])
        self.assertTrue(result["sentinel_subregime"].eq("NOT_APPLICABLE").all())
        self.assertFalse(any("latitude" in c.lower() or "longitude" in c.lower() for c in result.columns))
        self.assertEqual(result["candidate_token"].nunique(), len(result))

    def test_uncertainty_sentinel_uses_frozen_footprint_support(self) -> None:
        frame = self.structural_local_frame().drop(columns=["nearest_anchor_km"])
        frame["broad_sentinel_support"] = [0.2, 0.9, 0.5]
        rows = rank_unit(
            frame,
            cohort_row=self.cohort(
                regime="SENTINEL",
                arm="STRUCTURAL_SENTINEL",
                sentinel_subregime="UNCERTAINTY_FOOTPRINT",
            ),
            support_provenance_id="sha256:demo",
            salt=b"0123456789abcdef",
        )
        result = pd.DataFrame(rows)
        self.assertEqual(
            set(result["frozen_method"]),
            {"STRUCTURAL_SUPPORT", "UNCERTAINTY_FOOTPRINT_SUPPORT", "DETERMINISTIC_SPATIAL_BALANCE"},
        )
        self.assertTrue(result["sentinel_subregime"].eq("UNCERTAINTY_FOOTPRINT").all())
        self.assertNotIn("BROAD_SENTINEL_SUPPORT", set(result["frozen_method"]))

    def test_context_only_sentinel_does_not_invent_broad_support(self) -> None:
        frame = self.structural_local_frame().drop(columns=["nearest_anchor_km"])
        rows = rank_unit(
            frame,
            cohort_row=self.cohort(
                regime="SENTINEL",
                arm="STRUCTURAL_SENTINEL",
                sentinel_subregime="LEGACY_RANGE_CONTEXT",
            ),
            support_provenance_id="sha256:demo",
            salt=b"0123456789abcdef",
        )
        result = pd.DataFrame(rows)
        self.assertEqual(
            set(result["frozen_method"]),
            {"STRUCTURAL_SUPPORT", "DETERMINISTIC_SPATIAL_BALANCE"},
        )
        self.assertNotIn("UNCERTAINTY_FOOTPRINT_SUPPORT", set(result["frozen_method"]))

    def test_baseline_lane_has_two_rankings(self) -> None:
        frame = self.structural_local_frame().drop(
            columns=["open_land_score", "fragment_continuity_score", "terrain_context_score"]
        )
        rows = rank_unit(
            frame,
            cohort_row=self.cohort(arm="SPATIAL_BASELINE_ONLY"),
            support_provenance_id="",
            salt=b"0123456789abcdef",
        )
        result = pd.DataFrame(rows)
        self.assertEqual(set(result["frozen_method"]), {"ANNULAR_NEAREST_KNOWN", "DETERMINISTIC_SPATIAL_BALANCE"})

    def test_unknown_sentinel_subregime_fails_closed(self) -> None:
        frame = self.structural_local_frame().drop(columns=["nearest_anchor_km"])
        with self.assertRaisesRegex(ValueError, "unsupported frozen sentinel subregime"):
            rank_unit(
                frame,
                cohort_row=self.cohort(regime="SENTINEL", arm="STRUCTURAL_SENTINEL", sentinel_subregime="UNKNOWN"),
                support_provenance_id="sha256:demo",
                salt=b"0123456789abcdef",
            )

    def test_field_outcome_column_fails_closed(self) -> None:
        frame = self.structural_local_frame().assign(field_outcome_state="SEARCH_COMPLETED_DETECTED_VERIFIED")
        with self.assertRaises(ValueError):
            rank_unit(
                frame,
                cohort_row=self.cohort(),
                support_provenance_id="sha256:demo",
                salt=b"0123456789abcdef",
            )


if __name__ == "__main__":
    unittest.main()
