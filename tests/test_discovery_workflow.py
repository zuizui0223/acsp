from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acsp.discovery import (
    DiscoveryContext,
    assess_occurrence_evidence,
    rank_discovery_frame,
)


class DiscoveryWorkflowTests(unittest.TestCase):
    def occurrence_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "occurrence_id": "a",
                    "latitude": 35.0,
                    "longitude": 139.0000,
                    "event_year": 2024,
                    "coordinate_uncertainty_m": 100.0,
                    "provider_id": "test",
                },
                {
                    "occurrence_id": "b",
                    "latitude": 35.0,
                    "longitude": 139.0020,
                    "event_year": 2024,
                    "coordinate_uncertainty_m": 200.0,
                    "provider_id": "test",
                },
                {
                    "occurrence_id": "c",
                    "latitude": 35.1,
                    "longitude": 139.1,
                    "event_year": 2024,
                    "coordinate_uncertainty_m": None,
                    "provider_id": "test",
                },
            ]
        )

    def candidate_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"candidate_cell_id": "c1", "latitude": 35.01, "longitude": 139.01, "grid_row": 0, "grid_col": 0, "nearest_anchor_km": 0.8},
                {"candidate_cell_id": "c2", "latitude": 35.02, "longitude": 139.02, "grid_row": 0, "grid_col": 1, "nearest_anchor_km": 1.2},
                {"candidate_cell_id": "c3", "latitude": 35.03, "longitude": 139.03, "grid_row": 1, "grid_col": 0, "nearest_anchor_km": 1.5},
                {"candidate_cell_id": "c4", "latitude": 35.04, "longitude": 139.04, "grid_row": 1, "grid_col": 1, "nearest_anchor_km": 1.8},
            ]
        )

    def manifest(self) -> dict:
        return {
            "schema_version": "test-v1",
            "sources": [
                {
                    "provider_id": "TEST",
                    "layer_role": "candidate_frame",
                    "release_id": "v1",
                    "retrieved_at": "2026-09-05T00:00:00+00:00",
                    "source_uri": "synthetic://candidate-frame",
                    "sha256": "0" * 64,
                }
            ],
        }

    def test_auto_context_does_not_promote_anchors_to_local(self) -> None:
        assessment, medoids = assess_occurrence_evidence(self.occurrence_frame())
        self.assertEqual(assessment.status, "CONTEXT_REQUIRED")
        self.assertEqual(assessment.regime, "ABSTAIN_LOCAL_PATCH")
        self.assertEqual(assessment.exact_anchor_rows, 2)
        self.assertEqual(assessment.population_anchor_count, 1)
        self.assertEqual(len(medoids), 1)
        self.assertEqual(assessment.rows_missing_declared_uncertainty, 1)

    def test_explicit_source_backed_local_context_makes_frame_ranking_eligible(self) -> None:
        assessment, _ = assess_occurrence_evidence(
            self.occurrence_frame(),
            context=DiscoveryContext(local_component_justified=True),
        )
        self.assertEqual(assessment.status, "READY_FOR_DECLARED_LOCAL_FRAME")
        rankings, audit = rank_discovery_frame(
            self.candidate_frame(),
            assessment=assessment,
            source_manifest=self.manifest(),
        )
        self.assertEqual(
            set(rankings),
            {"DETERMINISTIC_SPATIAL_BALANCE", "ANNULAR_NEAREST_KNOWN"},
        )
        self.assertTrue(audit.no_fitted_blend)
        self.assertTrue(audit.same_candidate_frame_for_all_methods)
        self.assertFalse(audit.human_access_used)
        self.assertEqual(
            rankings["ANNULAR_NEAREST_KNOWN"]["candidate_cell_id"].tolist(),
            ["c1", "c2", "c3", "c4"],
        )

    def test_abstain_cannot_be_ranked(self) -> None:
        assessment, _ = assess_occurrence_evidence(self.occurrence_frame())
        with self.assertRaisesRegex(ValueError, "ABSTAIN"):
            rank_discovery_frame(
                self.candidate_frame(),
                assessment=assessment,
                source_manifest=self.manifest(),
            )

    def test_structural_family_missing_columns_returns_actionable_error(self) -> None:
        assessment, _ = assess_occurrence_evidence(
            self.occurrence_frame(),
            context=DiscoveryContext(local_component_justified=True),
        )
        with self.assertRaisesRegex(ValueError, "Required source roles"):
            rank_discovery_frame(
                self.candidate_frame(),
                assessment=assessment,
                source_manifest=self.manifest(),
                feature_family="WETLAND_MOISTURE_STRUCTURE",
            )

    def test_cli_template_and_assess_are_runnable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "template"
            subprocess.run(
                [sys.executable, "-m", "acsp.discovery.cli", "template", "--out-dir", str(out)],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertTrue((out / "occurrences.csv").exists())
            assess_out = Path(tmp) / "assessment"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "acsp.discovery.cli",
                    "assess",
                    str(out / "occurrences.csv"),
                    "--out-dir",
                    str(assess_out),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(completed.stdout)
            self.assertIn(payload["status"], {"CONTEXT_REQUIRED", "ABSTAIN_INSUFFICIENT_EXACT_EVIDENCE"})
            self.assertTrue((assess_out / "population_anchors.csv").exists())


if __name__ == "__main__":
    unittest.main()
