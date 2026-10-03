from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))

from prepare_cirsium_private_candidate_frame_v1 import build_private_candidate_frame  # noqa: E402


class CirsiumPrivateFrameBuilderTests(unittest.TestCase):
    def grass_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "candidate_cell_id": ["a", "b", "c", "d"],
                "latitude": [35.0, 35.0, 35.001, 35.001],
                "longitude": [135.0, 135.001, 135.0, 135.001],
                "grid_row": [0, 0, 1, 1],
                "grid_col": [0, 1, 0, 1],
                "wc_grass_frac_250m": [0.8, 0.7, 0.2, 0.1],
                "slope100": [2.0, 3.0, 12.0, 14.0],
                "tpi300": [-2.0, -1.0, 5.0, 6.0],
                "rough300": [1.0, 1.1, 3.0, 3.2],
                "nearest_anchor_km": [0.8, 1.0, 1.5, 1.9],
            }
        )

    def test_structural_pipeline_builds_support_and_provenance(self) -> None:
        built, summary = build_private_candidate_frame(
            self.grass_frame(),
            feature_family="OPEN_GRASSLAND_STRUCTURE",
            source_manifest={"field_outcomes_opened": False, "dem": "sha256:demo", "worldcover": "sha256:wc"},
        )
        self.assertIn("fragment_continuity_score_raw", built)
        self.assertIn("terrain_context_score_raw", built)
        self.assertIn("structural_support", built)
        self.assertTrue(built["structural_support"].between(0, 1).all())
        self.assertTrue(summary["support_provenance_id"].startswith("sha256:"))
        self.assertFalse(summary["field_outcomes_opened"])
        self.assertFalse(summary["human_access_used"])

    def test_same_source_manifest_yields_same_provenance(self) -> None:
        manifest = {"field_outcomes_opened": False, "dem": "x", "worldcover": "y"}
        _, first = build_private_candidate_frame(
            self.grass_frame(), feature_family="OPEN_GRASSLAND_STRUCTURE", source_manifest=manifest
        )
        _, second = build_private_candidate_frame(
            self.grass_frame(), feature_family="OPEN_GRASSLAND_STRUCTURE", source_manifest=manifest
        )
        self.assertEqual(first["support_provenance_id"], second["support_provenance_id"])

    def test_field_outcome_contamination_fails(self) -> None:
        frame = self.grass_frame().assign(field_outcome_state="SEARCH_COMPLETED_DETECTED_VERIFIED")
        with self.assertRaises(ValueError):
            build_private_candidate_frame(
                frame,
                feature_family="OPEN_GRASSLAND_STRUCTURE",
                source_manifest={"field_outcomes_opened": False},
            )

    def test_source_manifest_cannot_open_field_outcomes(self) -> None:
        with self.assertRaises(ValueError):
            build_private_candidate_frame(
                self.grass_frame(),
                feature_family="OPEN_GRASSLAND_STRUCTURE",
                source_manifest={"field_outcomes_opened": True},
            )


if __name__ == "__main__":
    unittest.main()
