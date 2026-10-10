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

from acsp.discovery import DiscoveryContext, assess_occurrence_evidence, rank_discovery_frame


class DiscoveryWorkflowTests(unittest.TestCase):
    def occurrence_frame(self) -> pd.DataFrame:
        return pd.DataFrame([
            {"occurrence_id": "a", "latitude": 35.0, "longitude": 139.0000, "event_year": 2024, "coordinate_uncertainty_m": 100.0, "provider_id": "test"},
            {"occurrence_id": "b", "latitude": 35.0, "longitude": 139.0020, "event_year": 2024, "coordinate_uncertainty_m": 200.0, "provider_id": "test"},
            {"occurrence_id": "c", "latitude": 35.1, "longitude": 139.1, "event_year": 2024, "coordinate_uncertainty_m": None, "provider_id": "test"},
        ])

    def candidate_frame(self) -> pd.DataFrame:
        return pd.DataFrame([
            {"candidate_cell_id": "c1", "latitude": 35.01, "longitude": 139.01, "grid_row": 0, "grid_col": 0, "nearest_anchor_km": 0.8},
            {"candidate_cell_id": "c2", "latitude": 35.02, "longitude": 139.02, "grid_row": 0, "grid_col": 1, "nearest_anchor_km": 1.2},
            {"candidate_cell_id": "c3", "latitude": 35.03, "longitude": 139.03, "grid_row": 1, "grid_col": 0, "nearest_anchor_km": 1.5},
            {"candidate_cell_id": "c4", "latitude": 35.04, "longitude": 139.04, "grid_row": 1, "grid_col": 1, "nearest_anchor_km": 1.8},
        ])

    def manifest(self) -> dict:
        return {"schema_version": "test-v1", "sources": [{"provider_id": "TEST", "layer_role": "candidate_frame", "release_id": "v1", "retrieved_at": "2026-09-05T00:00:00+00:00", "source_uri": "synthetic://candidate-frame", "sha256": "0" * 64}]}

    def local_assessment(self):
        return assess_occurrence_evidence(self.occurrence_frame(), context=DiscoveryContext(local_component_justified=True))[0]

    def test_auto_context_does_not_promote_anchors_to_local(self) -> None:
        assessment, medoids = assess_occurrence_evidence(self.occurrence_frame())
        self.assertEqual(assessment.status, "CONTEXT_REQUIRED")
        self.assertEqual(assessment.regime, "ABSTAIN_LOCAL_PATCH")
        self.assertEqual(assessment.exact_anchor_rows, 2)
        self.assertEqual(assessment.population_anchor_count, 1)
        self.assertEqual(len(medoids), 1)
        self.assertEqual(assessment.rows_missing_declared_uncertainty, 1)

    def test_conflicting_regime_context_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "mutually exclusive"):
            assess_occurrence_evidence(self.occurrence_frame(), context=DiscoveryContext(local_component_justified=True, detached_component_available=True))

    def test_explicit_source_backed_local_context_makes_frame_ranking_eligible(self) -> None:
        assessment = self.local_assessment()
        self.assertEqual(assessment.status, "READY_FOR_DECLARED_LOCAL_FRAME")
        rankings, audit = rank_discovery_frame(self.candidate_frame(), assessment=assessment, source_manifest=self.manifest())
        self.assertEqual(set(rankings), {"DETERMINISTIC_SPATIAL_BALANCE", "ANNULAR_NEAREST_KNOWN"})
        self.assertTrue(audit.no_fitted_blend)
        self.assertTrue(audit.same_candidate_frame_for_all_methods)
        self.assertFalse(audit.human_access_used)
        self.assertEqual(rankings["ANNULAR_NEAREST_KNOWN"]["candidate_cell_id"].tolist(), ["c1", "c2", "c3", "c4"])

    def test_abstain_cannot_be_ranked(self) -> None:
        assessment, _ = assess_occurrence_evidence(self.occurrence_frame())
        with self.assertRaisesRegex(ValueError, "ABSTAIN"):
            rank_discovery_frame(self.candidate_frame(), assessment=assessment, source_manifest=self.manifest())

    def test_human_access_columns_cannot_create_ecological_ranking(self) -> None:
        candidate = self.candidate_frame(); candidate["distance_to_road_m"] = 100.0
        with self.assertRaisesRegex(ValueError, "downstream in G_F"):
            rank_discovery_frame(candidate, assessment=self.local_assessment(), source_manifest=self.manifest())

    def test_human_access_source_roles_are_rejected(self) -> None:
        manifest = self.manifest(); manifest["sources"][0]["layer_role"] = "road_access"
        with self.assertRaisesRegex(ValueError, "cannot create ecological support"):
            rank_discovery_frame(self.candidate_frame(), assessment=self.local_assessment(), source_manifest=manifest)

    def test_structural_family_missing_columns_returns_actionable_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "Required source roles"):
            rank_discovery_frame(self.candidate_frame(), assessment=self.local_assessment(), source_manifest=self.manifest(), feature_family="WETLAND_MOISTURE_STRUCTURE")

    def test_cli_template_assess_and_frame_builders_are_runnable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            template = root / "template"
            subprocess.run([sys.executable, "-m", "acsp.discovery.cli", "template", "--out-dir", str(template)], cwd=ROOT, check=True, capture_output=True, text=True)
            assess_out = root / "assessment"
            completed = subprocess.run([sys.executable, "-m", "acsp.discovery.cli", "assess", str(template / "occurrences.csv"), "--out-dir", str(assess_out)], cwd=ROOT, check=True, capture_output=True, text=True)
            payload = json.loads(completed.stdout)
            self.assertIn(payload["status"], {"CONTEXT_REQUIRED", "ABSTAIN_INSUFFICIENT_EXACT_EVIDENCE"})
            anchors = assess_out / "population_anchors.csv"
            self.assertTrue(anchors.exists())

            local_csv = root / "local.csv"
            local = subprocess.run([
                sys.executable, "-m", "acsp.discovery.cli", "build-frame", "local",
                "--anchors", str(anchors), "--outer-radius-km", "2", "--grid-spacing-m", "500", "--out", str(local_csv)
            ], cwd=ROOT, check=True, capture_output=True, text=True)
            local_payload = json.loads(local.stdout)
            self.assertEqual(local_payload["status"], "DECLARED_LOCAL_FRAME_BUILT")
            self.assertTrue(local_csv.exists())
            self.assertTrue(pd.read_csv(local_csv)["nearest_anchor_km"].between(0.5 - 1e-6, 2.0 + 1e-6).all())

            broad_csv = root / "broad.csv"
            broad = subprocess.run([
                sys.executable, "-m", "acsp.discovery.cli", "build-frame", "broad",
                "--bounds", "138.98", "34.98", "139.03", "35.03", "--anchors", str(anchors),
                "--grid-spacing-m", "1000", "--out", str(broad_csv)
            ], cwd=ROOT, check=True, capture_output=True, text=True)
            broad_payload = json.loads(broad.stdout)
            self.assertEqual(broad_payload["status"], "DECLARED_BROAD_FRAME_BUILT")
            self.assertTrue(pd.read_csv(broad_csv)["nearest_anchor_km"].notna().all())

    def test_cli_local_frame_requires_explicit_outer_radius(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            anchors = Path(tmp) / "anchors.csv"
            pd.DataFrame({"latitude": [35.0], "longitude": [139.0]}).to_csv(anchors, index=False)
            completed = subprocess.run([
                sys.executable, "-m", "acsp.discovery.cli", "build-frame", "local", "--anchors", str(anchors), "--out", str(Path(tmp) / "x.csv")
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("--outer-radius-km", completed.stderr)


if __name__ == "__main__":
    unittest.main()
