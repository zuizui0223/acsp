import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from paper import validate_submission_alignment as validator


ROOT = Path(__file__).resolve().parents[1]


class RobustPatchSubmissionAlignmentTests(unittest.TestCase):
    def test_submission_alignment_validator_passes_network_free(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "paper" / "validate_submission_alignment.py")],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "submission_alignment_passed")
        self.assertEqual(payload["authoritative_product"], "non-ranked robust candidate patches")
        self.assertEqual(payload["validated_scope"], "fixed Japanese 12-region frame")
        self.assertEqual(payload["confirmation_pairs"], 96)
        self.assertEqual(payload["confirmation_folds"], 480)
        self.assertTrue(payload["historical_top5_package_preserved"])
        self.assertFalse(payload["global_product_promoted"])

    def test_historical_top5_paper_remains_separate_provenance(self):
        historical_manuscript = ROOT / "paper" / "MANUSCRIPT_DRAFT.md"
        historical_table = ROOT / "paper" / "generated" / "table_1_retrospective_validation.csv"
        robust_manuscript = ROOT / "paper" / "MANUSCRIPT_ROBUST_PATCH_DRAFT.md"
        robust_table = ROOT / "paper" / "generated" / "table_1_robust_patch_confirmation.csv"

        self.assertTrue(historical_manuscript.exists())
        self.assertTrue(historical_table.exists())
        self.assertTrue(robust_manuscript.exists())
        self.assertTrue(robust_table.exists())

        historical = historical_manuscript.read_text(encoding="utf-8")
        robust = robust_manuscript.read_text(encoding="utf-8")
        self.assertIn("fixed Top-5 decisions", historical)
        self.assertIn("non-ranked set of bounded robust candidate patches", robust)

    def test_frozen_method_claim_drift_fails_closed(self):
        constants = validator._load_literal_constants(validator.VALIDATED_SOURCE)
        original = validator.MANUSCRIPT.read_text(encoding="utf-8")
        mutations = (
            ("frozen 2.5% consensus tier", "frozen 5% consensus tier"),
            ("stored the resulting world as `float32`", "stored the resulting world as `float64`"),
            (
                "deterministic 1-km same-area complete-link rule",
                "deterministic 5-km same-area complete-link rule",
            ),
            ("The 2.5% quantity is a frozen method parameter", "The 5% quantity is a frozen method parameter"),
            ("U_{0.025}=\\{u_i:r_i\\le 0.025\\}", "U_{0.05}=\\{u_i:r_i\\le 0.05\\}"),
            ("at most 1,000 m", "at most 5,000 m"),
            ("`float32` leave-one-out worlds", "`float64` leave-one-out worlds"),
        )
        with tempfile.TemporaryDirectory() as directory:
            mutated_path = Path(directory) / "manuscript.md"
            for old, new in mutations:
                self.assertIn(old, original)
                mutated_path.write_text(original.replace(old, new, 1), encoding="utf-8")
                with mock.patch.object(validator, "MANUSCRIPT", mutated_path):
                    with self.assertRaises(AssertionError):
                        validator._validate_text_boundaries(constants, "float32")

    def test_fresh_transfer_decision_drift_fails_closed(self):
        with validator.TABLE_2.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = list(reader.fieldnames or ())
            original_rows = list(reader)
        fresh_index = next(
            index
            for index, row in enumerate(original_rows)
            if row["experiment_id"] == "country_framed_fresh_confirmation"
        )
        mutations = {
            "terminal_status": "globally_validated",
            "failed_gate": "none",
        }
        with tempfile.TemporaryDirectory() as directory:
            mutated_path = Path(directory) / "transfer.csv"
            for field, value in mutations.items():
                rows = [dict(row) for row in original_rows]
                rows[fresh_index][field] = value
                with mutated_path.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
                with mock.patch.object(validator, "TABLE_2", mutated_path):
                    with self.assertRaises(AssertionError):
                        validator.run()


if __name__ == "__main__":
    unittest.main()
