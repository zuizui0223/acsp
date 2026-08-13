from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

import recover_practical_core_grts_pair as recovery
import recover_practical_core_grts_pair_entrypoint as entrypoint


class PracticalCoreGrtsRecoveryTests(unittest.TestCase):
    def test_compat_entrypoint_maps_draw_path_to_output_path(self) -> None:
        expected = (pd.DataFrame({"variant": ["official_grts_equal"]}), {"status": "ok"})
        with mock.patch.object(entrypoint, "_ORIGINAL_RUN_GRTS", return_value=expected) as target:
            result = entrypoint._run_grts_compat(
                candidate_path=Path("candidate.csv"),
                draw_path=Path("draws.csv"),
                pair_id=2,
                repeat_id=3,
                protocol={"grts": {}},
            )
        self.assertIs(result, expected)
        target.assert_called_once_with(
            candidate_path=Path("candidate.csv"),
            output_path=Path("draws.csv"),
            pair_id=2,
            repeat_id=3,
            protocol={"grts": {}},
        )

    def test_compat_entrypoint_rejects_ambiguous_output_keywords(self) -> None:
        with self.assertRaisesRegex(TypeError, "only one"):
            entrypoint._run_grts_compat(
                candidate_path=Path("candidate.csv"),
                draw_path=Path("draws-a.csv"),
                output_path=Path("draws-b.csv"),
                pair_id=1,
                repeat_id=1,
                protocol={"grts": {}},
            )

    def test_replace_grts_rows_preserves_non_grts_values(self) -> None:
        source = pd.DataFrame(
            [
                {"repeat": 1, "decision_method": "acsp_practical_core", "heldout_recall": 0.4, "method_status": "ok"},
                {"repeat": 1, "decision_method": "same_pool_random_mean", "heldout_recall": 0.1, "method_status": "ok"},
                {"repeat": 1, "decision_method": "official_grts_equal", "heldout_recall": 0.0, "method_status": "grts_failure"},
            ]
        )
        recovered = pd.DataFrame(
            [
                {"repeat": 1, "decision_method": "official_grts_equal", "heldout_recall": 0.25, "method_status": "ok", "grts_successful_draws": 50},
            ]
        )
        out = recovery._replace_grts_rows(source, recovered)
        pd.testing.assert_frame_equal(
            out.loc[out["decision_method"].eq("acsp_practical_core"), source.columns].reset_index(drop=True),
            source.loc[source["decision_method"].eq("acsp_practical_core")].reset_index(drop=True),
            check_dtype=False,
            check_exact=True,
        )
        pd.testing.assert_frame_equal(
            out.loc[out["decision_method"].eq("same_pool_random_mean"), source.columns].reset_index(drop=True),
            source.loc[source["decision_method"].eq("same_pool_random_mean")].reset_index(drop=True),
            check_dtype=False,
            check_exact=True,
        )
        grts = out.loc[out["decision_method"].eq("official_grts_equal")].iloc[0]
        self.assertEqual(grts["heldout_recall"], 0.25)
        self.assertEqual(grts["method_status"], "ok")
        self.assertEqual(grts["grts_successful_draws"], 50)

    def test_run_grts_writes_only_pre_outcome_command_inputs(self) -> None:
        protocol = {
            "grts": {"draws_per_fold": 2, "seed_base": 20260811, "replacement_sites": 3},
            "practical_core": {"top_k": 5},
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / "candidate.csv"
            output = root / "draws.csv"
            candidate.write_text("candidate_id,latitude,longitude,component_local_habitat_score\na,35,139,0.9\n", encoding="utf-8")

            def fake_subprocess(command, **kwargs):
                pd.DataFrame(
                    {
                        "variant": ["official_grts_equal"],
                        "outcomes_available_to_selector": [False],
                    }
                ).to_csv(output, index=False)
                return mock.Mock(returncode=0, stdout="", stderr="")

            with mock.patch.object(recovery.subprocess, "run", side_effect=fake_subprocess) as runner:
                draws, audit = recovery._run_grts(candidate, output, 7, 2, protocol)

            self.assertEqual(audit["status"], "ok")
            self.assertEqual(len(draws), 1)
            command = runner.call_args.args[0]
            self.assertIn(str(candidate), command)
            self.assertIn(str(output), command)
            self.assertIn("--repeat", command)
            self.assertEqual(command[command.index("--repeat") + 1], "2")
            self.assertFalse(any("held" in str(value).lower() for value in command))
            self.assertFalse(audit["outcomes_available_to_selector"])
            self.assertFalse(audit["candidate_regenerated"])
            self.assertFalse(audit["outer_split_regenerated"])
            self.assertFalse(audit["acsp_decision_regenerated"])


if __name__ == "__main__":
    unittest.main()
