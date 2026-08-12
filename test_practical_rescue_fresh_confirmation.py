#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from aggregate_practical_rescue_fresh_confirmation import parser, run
import run_practical_rescue_fresh_confirmation_pair_v2 as fresh_pair_v2


def _protocol(path: Path, pair_count: int = 4) -> str:
    payload = {
        "protocol_id": "test-fresh-rescue-confirmation",
        "cohort": {"pair_count": pair_count},
        "final_model": {"model_sha256": "frozen-model-hash"},
        "inference": {
            "primary_contrast": "practical_rescue - official_grts_proportional_local_mindis10km",
            "bootstrap_draws": 1000,
            "seed": 7,
            "minimum_absolute_recall_gain": 0.015,
        },
        "no_retuning_after_confirmation_outcome": True,
    }
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    payload["protocol_fingerprint"] = fingerprint
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return fingerprint


def _summary(pair_id: int, fingerprint: str) -> dict[str, object]:
    return {
        "pair_id": pair_id,
        "taxon_group": "plant" if pair_id % 2 else "animal",
        "protocol_fingerprint": fingerprint,
        "verified_scientific_artifact": True,
        "outcomes_available_to_rescue_selector": False,
        "outcomes_available_to_grts_selector": False,
        "final_model_sha256": "frozen-model-hash",
        "rescue_mean_recovery_10km": 0.40,
        "grts_mean_recovery_10km": 0.30,
    }


def _fresh_grts_protocol(draws: int = 2) -> dict[str, object]:
    return {
        "official_grts": {
            "draws_per_fold": draws,
            "seed_base": 20260811,
            "top_k": 5,
            "replacement_sites_requested": 3,
            "score_col": "component_local_habitat_score",
        }
    }


class FreshRescueConfirmationTests(unittest.TestCase):
    def test_complete_verified_cohort_can_be_aggregated(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cohort = root / "cohort.csv"
            protocol = root / "protocol.json"
            pair_root = root / "pairs"
            fingerprint = _protocol(protocol)
            pd.DataFrame({
                "pair_id": [1, 2, 3, 4],
                "scientific_name": ["a", "b", "c", "d"],
            }).to_csv(cohort, index=False)
            for pair_id in range(1, 5):
                directory = pair_root / f"pair_{pair_id:03d}"
                directory.mkdir(parents=True)
                (directory / "pair_summary.json").write_text(
                    json.dumps(_summary(pair_id, fingerprint)) + "\n"
                )
            result = run(cohort, pair_root, protocol, root / "aggregate")
            self.assertEqual(result["verified_pair_artifacts"], 4)
            self.assertFalse(result["missing_pair_artifacts_scored_as_zero"])
            self.assertAlmostEqual(result["primary_inference"]["mean_difference"], 0.10)
            self.assertGreater(result["primary_inference"]["bootstrap_95ci_low"], 0.0)
            # Four synthetic pairs are intentionally too few to require the
            # production p<0.05 sign-flip gate. The production cohort is 192.
            self.assertFalse(result["promotion_gate_passed"])

    def test_missing_pair_artifact_invalidates_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cohort = root / "cohort.csv"
            protocol = root / "protocol.json"
            pair_root = root / "pairs"
            fingerprint = _protocol(protocol)
            pd.DataFrame({
                "pair_id": [1, 2, 3, 4],
                "scientific_name": ["a", "b", "c", "d"],
            }).to_csv(cohort, index=False)
            for pair_id in range(1, 4):
                directory = pair_root / f"pair_{pair_id:03d}"
                directory.mkdir(parents=True)
                (directory / "pair_summary.json").write_text(
                    json.dumps(_summary(pair_id, fingerprint)) + "\n"
                )
            with self.assertRaisesRegex(RuntimeError, "missing or duplicate verified pair artifacts"):
                run(cohort, pair_root, protocol, root / "aggregate")

    def test_cli_maps_protocol_to_protocol_path(self) -> None:
        args = parser().parse_args([
            "--cohort", "cohort.csv",
            "--pair-root", "pairs",
            "--protocol", "protocol.json",
            "--output", "aggregate",
        ])
        self.assertEqual(args.cohort, Path("cohort.csv"))
        self.assertEqual(args.pair_root, Path("pairs"))
        self.assertEqual(args.protocol_path, Path("protocol.json"))
        self.assertEqual(args.output, Path("aggregate"))
        self.assertNotIn("protocol", vars(args))

    def test_fresh_v2_rejects_nonempty_grts_draw_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            candidate = root / "candidates.csv"
            output = root / "draws.csv"
            candidate.write_text("candidate_id,latitude,longitude\na,35,139\n", encoding="utf-8")
            pd.DataFrame({
                "outcomes_available_to_selector": [False, False],
                "effective_replacements": [1, 1],
                "candidate_frame_rows": [6, 6],
                "error_message": ["", "simpleError: adapter failure"],
            }).to_csv(output, index=False)
            completed = SimpleNamespace(returncode=0, stderr="")
            with patch.object(fresh_pair_v2.subprocess, "run", return_value=completed):
                with self.assertRaisesRegex(RuntimeError, "refusing failure-as-zero"):
                    fresh_pair_v2._run_grts_v2(
                        candidate,
                        output,
                        pair_id=1,
                        repeat=1,
                        protocol=_fresh_grts_protocol(),
                    )

    def test_fresh_v2_accepts_error_free_feasible_draws(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            candidate = root / "candidates.csv"
            output = root / "draws.csv"
            candidate.write_text("candidate_id,latitude,longitude\na,35,139\n", encoding="utf-8")
            pd.DataFrame({
                "outcomes_available_to_selector": [False, False],
                "effective_replacements": [0, 0],
                "candidate_frame_rows": [5, 5],
                "error_message": ["", ""],
            }).to_csv(output, index=False)
            completed = SimpleNamespace(returncode=0, stderr="")
            with patch.object(fresh_pair_v2.subprocess, "run", return_value=completed):
                draws = fresh_pair_v2._run_grts_v2(
                    candidate,
                    output,
                    pair_id=1,
                    repeat=1,
                    protocol=_fresh_grts_protocol(),
                )
            self.assertEqual(len(draws), 2)


if __name__ == "__main__":
    unittest.main()
