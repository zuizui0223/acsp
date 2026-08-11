import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from score_practical_core_secondary_sdm import (
    EXPECTED_PROTOCOL,
    _canonical,
    _sha256,
    score_fold,
)


class PracticalCoreSecondarySdmTests(unittest.TestCase):
    def test_secondary_protocol_fingerprint_is_frozen(self):
        payload, fingerprint = _canonical(
            Path("validation/acsp_practical_core_secondary_sdm_protocol.json"),
            "fingerprint",
            EXPECTED_PROTOCOL,
        )
        self.assertEqual(fingerprint, EXPECTED_PROTOCOL)
        self.assertIsNone(payload["reporting"]["superiority_gate"])
        self.assertTrue(payload["no_retuning_after_outcome"])

    def make_primary_fold(self, root: Path):
        training = pd.DataFrame({
            "latitude": [35.0, 35.1, 35.2, 35.3, 35.4, 35.5],
            "longitude": [139.0, 139.1, 139.2, 139.3, 139.4, 139.5],
        })
        candidates = pd.DataFrame({
            "candidate_id": [f"c{i}" for i in range(1, 7)],
            "latitude": [35.00, 35.05, 35.10, 35.15, 35.20, 35.25],
            "longitude": [139.00, 139.05, 139.10, 139.15, 139.20, 139.25],
            "component_local_habitat_score": [0.95, 0.90, 0.85, 0.80, 0.75, 0.70],
            "candidate_type": ["habitat-match"] * 6,
        })
        decisions = {
            "methods": {"acsp_practical_core": ["c1", "c2", "c3", "c4", "c5"]},
            "method_status": {"acsp_practical_core": "ok"},
            "random_same_pool_draws": [],
            "outcomes_available_to_selectors": False,
        }
        heldout = pd.DataFrame({
            "_outer_occurrence_id": ["h1", "h2"],
            "_outer_block": ["a", "b"],
            "_latitude": [35.001, 35.249],
            "_longitude": [139.001, 139.249],
        })
        training_path = root / "training_occurrences.csv"
        candidate_path = root / "candidate_pool_pre_outcome.csv"
        decisions_path = root / "deterministic_decisions_pre_outcome.json"
        heldout_path = root / "held_out_occurrences.csv"
        training.to_csv(training_path, index=False)
        candidates.to_csv(candidate_path, index=False)
        decisions_path.write_text(json.dumps(decisions), encoding="utf-8")
        heldout.to_csv(heldout_path, index=False)

        files = {}
        for name, path in {
            "training_occurrences": training_path,
            "candidate_pool_pre_outcome": candidate_path,
            "deterministic_decisions_pre_outcome": decisions_path,
            "held_out_occurrences": heldout_path,
        }.items():
            files[name] = {"path": path.name, "sha256": _sha256(path)}
        manifest = {
            "pair_id": 1,
            "repeat": 1,
            "scientific_name": "Species alpha",
            "taxon_group": "plant",
            "practical_core_fingerprint": "3dafe65b6bef09b1878d688730d5feb64a8de58843b06ff9fb14a876512d4905",
            "confirmation_protocol_fingerprint": "cd27dc5416057b574e58742bfe001307338a20aedb63ce1bac431588dc58eee9",
            "outcomes_available_to_operational_selectors": False,
            "pre_outcome_files_written_once": True,
            "files": files,
        }
        (root / "fold_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return training, candidates

    def test_sdm_decision_is_frozen_before_heldout_scoring_and_overlap_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            primary = Path(temporary) / "primary"
            secondary = Path(temporary) / "secondary"
            primary.mkdir()
            _, candidates = self.make_primary_fold(primary)

            def fake_fit(training, input_candidates):
                scored = input_candidates.copy()
                scored["sdm_suitability"] = [0.1, 0.2, 0.3, 0.9, 0.8, 0.7]
                return scored, {"status": "sdm_ok", "finite_candidate_scores": 6}

            with patch(
                "score_practical_core_secondary_sdm.legacy_sdm._fit_and_score_production_sdm",
                side_effect=fake_fit,
            ):
                manifest = score_fold(
                    primary,
                    secondary,
                    core_fp="3dafe65b6bef09b1878d688730d5feb64a8de58843b06ff9fb14a876512d4905",
                    primary_fp="cd27dc5416057b574e58742bfe001307338a20aedb63ce1bac431588dc58eee9",
                    secondary_fp=EXPECTED_PROTOCOL,
                )

            decision = json.loads((secondary / "sdm_decision_pre_outcome.json").read_text())
            result = pd.read_csv(secondary / "sdm_fold_result.csv").iloc[0]
            scored = pd.read_csv(secondary / "sdm_scored_candidates_pre_outcome.csv")

        self.assertEqual(decision["status"], "sdm_ok")
        self.assertEqual(decision["selected_candidate_ids"], ["c4", "c5", "c6", "c3", "c2"])
        self.assertFalse(decision["outcomes_available_to_sdm_selector"])
        self.assertNotIn("heldout_recall", scored.columns)
        self.assertNotIn("_outer_occurrence_id", scored.columns)
        self.assertAlmostEqual(result["top5_jaccard"], 4 / 6)
        self.assertFalse(bool(result["exact_set_agreement"]))
        self.assertTrue(manifest["preoutcome_files_not_rewritten_after_scoring"])
        self.assertFalse(manifest["outcomes_available_to_sdm_selector"])

    def test_sdm_fit_failure_is_retained_as_zero_not_retuned(self):
        with tempfile.TemporaryDirectory() as temporary:
            primary = Path(temporary) / "primary"
            secondary = Path(temporary) / "secondary"
            primary.mkdir()
            self.make_primary_fold(primary)
            with patch(
                "score_practical_core_secondary_sdm.legacy_sdm._fit_and_score_production_sdm",
                side_effect=RuntimeError("synthetic fit failure"),
            ):
                manifest = score_fold(
                    primary,
                    secondary,
                    core_fp="3dafe65b6bef09b1878d688730d5feb64a8de58843b06ff9fb14a876512d4905",
                    primary_fp="cd27dc5416057b574e58742bfe001307338a20aedb63ce1bac431588dc58eee9",
                    secondary_fp=EXPECTED_PROTOCOL,
                )
            result = pd.read_csv(secondary / "sdm_fold_result.csv").iloc[0]
            audit = json.loads((secondary / "sdm_audit_pre_outcome.json").read_text())
        self.assertEqual(manifest["sdm_status"], "sdm_failure")
        self.assertEqual(result["fitted_sdm_top_k_recall"], 0.0)
        self.assertTrue(pd.isna(result["top5_jaccard"]))
        self.assertEqual(audit["error_message"], "synthetic fit failure")


if __name__ == "__main__":
    unittest.main()
