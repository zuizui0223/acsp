import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from aggregate_practical_core_confirmation import (
    PRIMARY,
    build_pair_level_table,
    paired_inference,
)
from execute_practical_core_confirmation_pair import (
    _finalize_fold,
    _write_pre_outcome_artifacts,
)
from run_practical_core_confirmation_pair import (
    _canonical_fingerprint,
    _sha256,
    score_frozen_decisions,
)


class PracticalCoreConfirmationRunnerTests(unittest.TestCase):
    def protocol(self):
        payload, fingerprint = _canonical_fingerprint(
            Path("validation/acsp_practical_core_untouched_confirmation_protocol.json"),
            "protocol_fingerprint",
        )
        self.assertEqual(
            fingerprint,
            "cd27dc5416057b574e58742bfe001307338a20aedb63ce1bac431588dc58eee9",
        )
        return payload

    def pair(self):
        return pd.Series({
            "pair_id": 1,
            "taxon_group": "plant",
            "scientific_name": "Species alpha",
            "region_name": "Synthetic",
        })

    def candidates(self):
        return pd.DataFrame({
            "candidate_id": [f"c{i}" for i in range(1, 7)],
            "latitude": [35.000, 35.010, 35.020, 35.030, 35.040, 35.050],
            "longitude": [139.000, 139.010, 139.020, 139.030, 139.040, 139.050],
            "component_local_habitat_score": [0.95, 0.9, 0.85, 0.8, 0.75, 0.7],
            "candidate_type": ["habitat-match"] * 6,
        })

    def heldout(self):
        return pd.DataFrame({
            "_outer_occurrence_id": ["h1", "h2"],
            "_outer_block": ["a", "b"],
            "_latitude": [35.001, 35.049],
            "_longitude": [139.001, 139.049],
        })

    def test_pre_outcome_hashes_do_not_change_after_outcome_finalize(self):
        pair = self.pair()
        candidates = self.candidates()
        training = pd.DataFrame({"latitude": [35.0], "longitude": [139.0]})
        deterministic = {"acsp_practical_core": ["c1", "c2", "c3", "c4", "c5"]}
        statuses = {"acsp_practical_core": "ok"}
        random_sets = [["c1", "c2", "c3", "c4", "c5"]]

        with tempfile.TemporaryDirectory() as temporary:
            fold_dir = Path(temporary)
            pre = _write_pre_outcome_artifacts(
                fold_dir,
                training,
                candidates,
                deterministic,
                statuses,
                random_sets,
            )
            grts_draws = fold_dir / "grts_draws_pre_outcome.csv"
            pd.DataFrame({
                "variant": ["official_grts_equal"],
                "draw_index": [1],
                "base_ids": ["c1;c2;c3;c4;c5"],
                "outcomes_available_to_selector": [False],
            }).to_csv(grts_draws, index=False)
            grts_audit = fold_dir / "grts_process_audit.json"
            grts_audit.write_text(
                json.dumps({"status": "ok", "outcomes_available_to_selector": False}),
                encoding="utf-8",
            )
            grts_paths = {
                "grts_draws_pre_outcome": grts_draws,
                "grts_process_audit": grts_audit,
            }
            before = {name: _sha256(path) for name, path in {**pre, **grts_paths}.items()}

            _finalize_fold(
                fold_dir,
                pre,
                grts_paths,
                self.heldout(),
                pd.DataFrame({"decision_method": [PRIMARY], "heldout_recall": [1.0]}),
                pd.DataFrame({"variant": ["official_grts_equal"], "heldout_recall": [1.0]}),
                ["c1"],
                pair,
                1,
                {"b"},
                "3dafe65b6bef09b1878d688730d5feb64a8de58843b06ff9fb14a876512d4905",
                "cd27dc5416057b574e58742bfe001307338a20aedb63ce1bac431588dc58eee9",
                len(training),
                len(candidates),
            )
            after = {name: _sha256(path) for name, path in {**pre, **grts_paths}.items()}
            manifest = json.loads((fold_dir / "fold_manifest.json").read_text())

        self.assertEqual(before, after)
        self.assertTrue(manifest["pre_outcome_files_written_once"])
        self.assertTrue(manifest["pre_outcome_files_not_rewritten_after_scoring"])
        candidate_columns = set(candidates.columns)
        self.assertNotIn("_outer_occurrence_id", candidate_columns)
        self.assertNotIn("heldout_recall", candidate_columns)

    def test_grts_missing_draws_are_zero_in_fixed_draw_mean(self):
        protocol = self.protocol()
        protocol["grts"]["draws_per_fold"] = 2
        candidates = self.candidates()
        deterministic = {
            "acsp_practical_core": ["c1", "c2", "c3", "c4", "c5"],
            "frozen_acsp_v1_historical": ["c1", "c2", "c3", "c4", "c5"],
            "geographic_maximin": ["c1", "c2", "c3", "c4", "c5"],
            "environmental_maximin_when_eligible": [],
            "dual_space_maximin_when_eligible": [],
        }
        statuses = {
            "acsp_practical_core": "ok",
            "frozen_acsp_v1_historical": "ok",
            "geographic_maximin": "ok",
            "environmental_maximin_when_eligible": "not_eligible",
            "dual_space_maximin_when_eligible": "not_eligible",
        }
        # Only draw 1 is present for each GRTS variant; draw 2 must score zero.
        rows = []
        for variant in (
            "official_grts_equal",
            "official_grts_proportional_local",
            "official_grts_proportional_local_mindis10km",
        ):
            rows.append({
                "variant": variant,
                "draw_index": 1,
                "base_ids": "c1;c2;c3;c4;c5",
                "error_message": "",
            })
        grts = pd.DataFrame(rows)
        results, scored, _ = score_frozen_decisions(
            candidates,
            self.heldout(),
            deterministic,
            statuses,
            [["c1", "c2", "c3", "c4", "c5"]],
            grts,
            self.pair(),
            1,
            protocol,
        )
        primary_grts = results[
            results["decision_method"].eq(
                "official_grts_proportional_local_mindis10km"
            )
        ].iloc[0]
        self.assertEqual(primary_grts["grts_successful_draws"], 1)
        self.assertEqual(primary_grts["grts_expected_draws"], 2)
        self.assertEqual(primary_grts["method_status"], "partial_grts_failure")
        self.assertEqual(len(scored[scored["variant"].eq(
            "official_grts_proportional_local_mindis10km"
        )]), 2)
        self.assertGreaterEqual(primary_grts["heldout_recall"], 0.0)
        self.assertLessEqual(primary_grts["heldout_recall"], 0.5)

    def test_missing_declared_pair_artifact_is_retained_as_zero(self):
        protocol = self.protocol()
        cohort = pd.DataFrame({
            "pair_id": [1],
            "scientific_name": ["Species alpha"],
            "taxon_group": ["plant"],
            "geographic_stratum": ["east"],
            "region_name": ["Synthetic"],
            "record_count_stratum": [0],
        })
        with tempfile.TemporaryDirectory() as temporary:
            pair_level, audit, folds = build_pair_level_table(
                cohort,
                Path(temporary),
                protocol,
                "3dafe65b6bef09b1878d688730d5feb64a8de58843b06ff9fb14a876512d4905",
                "cd27dc5416057b574e58742bfe001307338a20aedb63ce1bac431588dc58eee9",
            )
        primary = pair_level[pair_level["decision_method"].eq(PRIMARY)].iloc[0]
        grts = pair_level[
            pair_level["decision_method"].eq(
                "official_grts_proportional_local_mindis10km"
            )
        ].iloc[0]
        self.assertEqual(primary["pair_mean_recall"], 0.0)
        self.assertEqual(grts["pair_mean_recall"], 0.0)
        self.assertFalse(primary["pair_artifact_present"])
        self.assertEqual(audit.iloc[0]["artifact_status"], "missing_pair_artifact_scored_zero")
        self.assertTrue(folds.empty)

    def test_pair_level_inference_uses_pairs_not_fold_rows(self):
        pair_level = pd.DataFrame({
            "pair_id": [1, 1, 2, 2, 3, 3],
            "decision_method": [PRIMARY, "baseline"] * 3,
            "pair_mean_recall": [0.3, 0.1, 0.2, 0.1, 0.4, 0.2],
        })
        result = paired_inference(
            pair_level,
            PRIMARY,
            "baseline",
            bootstrap_draws=1000,
            sign_flip_draws=1000,
            seed=7,
        )
        self.assertEqual(result["pairs"], 3)
        self.assertAlmostEqual(result["mean_difference"], (0.2 + 0.1 + 0.2) / 3)


if __name__ == "__main__":
    unittest.main()
