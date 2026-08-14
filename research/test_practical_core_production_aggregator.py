import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from aggregate_practical_core_confirmation import _canonical_fingerprint
from execute_aggregate_practical_core_confirmation import (
    build_pair_level_table_strict,
)


class PracticalCoreProductionAggregatorTests(unittest.TestCase):
    def protocol(self):
        protocol, fingerprint = _canonical_fingerprint(
            Path("validation/acsp_practical_core_untouched_confirmation_protocol.json"),
            "protocol_fingerprint",
        )
        self.assertEqual(
            fingerprint,
            "cd27dc5416057b574e58742bfe001307338a20aedb63ce1bac431588dc58eee9",
        )
        return protocol

    def cohort(self):
        return pd.DataFrame({
            "pair_id": [1],
            "scientific_name": ["Species alpha"],
            "taxon_group": ["plant"],
            "geographic_stratum": ["east"],
            "region_name": ["Synthetic"],
            "record_count_stratum": [0],
        })

    def test_infrastructure_marker_is_scored_zero_not_treated_as_scientific_artifact(self):
        protocol = self.protocol()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pair_dir = root / "pair_001"
            pair_dir.mkdir()
            (pair_dir / "unexpected_workflow_failure.json").write_text(
                json.dumps({
                    "pair_id": 1,
                    "pair_status": "unexpected_workflow_failure",
                }),
                encoding="utf-8",
            )
            pair_level, audit, folds = build_pair_level_table_strict(
                self.cohort(),
                root,
                protocol,
                "3dafe65b6bef09b1878d688730d5feb64a8de58843b06ff9fb14a876512d4905",
                "cd27dc5416057b574e58742bfe001307338a20aedb63ce1bac431588dc58eee9",
            )
        core = pair_level[pair_level["decision_method"].eq("acsp_practical_core")].iloc[0]
        grts = pair_level[
            pair_level["decision_method"].eq(
                "official_grts_proportional_local_mindis10km"
            )
        ].iloc[0]
        self.assertEqual(core["pair_mean_recall"], 0.0)
        self.assertEqual(grts["pair_mean_recall"], 0.0)
        self.assertFalse(core["pair_artifact_present"])
        self.assertEqual(
            core["pair_artifact_status"],
            "unexpected_workflow_failure_scored_zero",
        )
        self.assertEqual(
            audit.iloc[0]["artifact_status"],
            "unexpected_workflow_failure_scored_zero",
        )
        self.assertTrue(folds.empty)

    def test_incomplete_existing_scientific_directory_without_marker_aborts(self):
        protocol = self.protocol()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "pair_001").mkdir()
            with self.assertRaises(FileNotFoundError):
                build_pair_level_table_strict(
                    self.cohort(),
                    root,
                    protocol,
                    "3dafe65b6bef09b1878d688730d5feb64a8de58843b06ff9fb14a876512d4905",
                    "cd27dc5416057b574e58742bfe001307338a20aedb63ce1bac431588dc58eee9",
                )


if __name__ == "__main__":
    unittest.main()
