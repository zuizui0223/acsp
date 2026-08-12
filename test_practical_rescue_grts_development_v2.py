#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

import pandas as pd

import benchmark_practical_rescue_grts_pair_v2 as pair_v2
import aggregate_practical_rescue_grts_development_v2 as aggregate_v2


V1_PROTOCOL = "950f7d9de90da2f2bd2561a18b7cc1eb74a60568ccc801875b96119db53bddf2"


def _canonical_v2_protocol(path: Path) -> tuple[dict[str, object], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    stored = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if stored != calculated:
        raise ValueError(
            f"corrected GRTS v2 protocol self-hash mismatch: stored={stored}, calculated={calculated}"
        )
    payload["protocol_fingerprint"] = stored
    return payload, calculated


class PracticalRescueGrtsDevelopmentV2Tests(unittest.TestCase):
    def test_corrected_protocol_fingerprint_is_frozen(self):
        payload, fingerprint = _canonical_v2_protocol(
            Path("validation/acsp_practical_rescue_grts_development_protocol_v2.json")
        )
        self.assertEqual(fingerprint, pair_v2.EXPECTED_PROTOCOL)
        grts = payload["official_grts"]
        self.assertEqual(grts["spsurvey_version"], "5.6.1")
        self.assertEqual(
            grts["spsurvey_tag_commit"],
            "0914fcd071713fdab19f43d8d9a66436830bd917",
        )
        self.assertEqual(grts["top_k"], 5)
        self.assertEqual(grts["n_base_rule"], "min(top_k, candidate_frame_rows)")
        self.assertEqual(grts["replacement_sites_requested"], 3)
        self.assertEqual(
            grts["replacement_sites_effective_rule"],
            "min(replacement_sites_requested, max(candidate_frame_rows - n_base, 0))",
        )
        self.assertEqual(grts["draws_per_fold"], 50)
        self.assertEqual(grts["mindis_km"], 10.0)
        self.assertFalse(payload["v1_comparator_audit"]["rescue_model_or_hyperparameters_changed"])
        self.assertFalse(payload["v1_comparator_audit"]["v1_final_aggregate_used_to_choose_correction"])
        self.assertFalse(payload["v1_comparator_audit"]["v2_outcomes_inspected_at_freeze"])

    def test_pair_parser_defaults_to_corrected_protocol(self):
        args = pair_v2.parser().parse_args([
            "--group-id", "mixed_1",
            "--source-root", "source",
            "--rescue-fold-table", "rescue.csv",
            "--output", "out",
        ])
        self.assertEqual(
            args.protocol,
            Path("validation/acsp_practical_rescue_grts_development_protocol_v2.json"),
        )

    def test_aggregate_cli_binds_protocol_path(self):
        args = aggregate_v2.parser().parse_args([
            "--pair-root", "pairs",
            "--protocol", "validation/acsp_practical_rescue_grts_development_protocol_v2.json",
            "--output", "aggregate",
        ])
        self.assertEqual(args.pair_root, Path("pairs"))
        self.assertEqual(
            args.protocol_path,
            Path("validation/acsp_practical_rescue_grts_development_protocol_v2.json"),
        )
        self.assertEqual(args.output, Path("aggregate"))
        self.assertNotIn("protocol", vars(args))

    def test_protocol_bytes_self_report_expected_fingerprint(self):
        payload = json.loads(
            Path("validation/acsp_practical_rescue_grts_development_protocol_v2.json").read_text()
        )
        self.assertEqual(payload["protocol_fingerprint"], pair_v2.EXPECTED_PROTOCOL)

    def test_v2_import_does_not_mutate_v1_protocol_contracts(self):
        self.assertEqual(pair_v2.base.EXPECTED_PROTOCOL, V1_PROTOCOL)
        self.assertEqual(aggregate_v2.base.EXPECTED_PROTOCOL, V1_PROTOCOL)
        self.assertIsNot(pair_v2.base._run_grts, pair_v2._run_grts_v2)

    def test_nonempty_grts_errors_fail_closed(self):
        ok = pd.DataFrame({"error_message": ["", None, ""]})
        pair_v2._assert_nonempty_grts_draws_error_free(ok)
        bad = pd.DataFrame({"error_message": ["", "simpleError: adapter failure"]})
        with self.assertRaisesRegex(RuntimeError, "refusing failure-as-zero"):
            pair_v2._assert_nonempty_grts_draws_error_free(bad)

    def test_nonempty_grts_error_column_is_required(self):
        with self.assertRaisesRegex(RuntimeError, "lacks error_message"):
            pair_v2._assert_nonempty_grts_draws_error_free(pd.DataFrame({"seed": [1]}))


if __name__ == "__main__":
    unittest.main()
