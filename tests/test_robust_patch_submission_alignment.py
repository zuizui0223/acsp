import json
from pathlib import Path
import subprocess
import sys
import unittest


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


if __name__ == "__main__":
    unittest.main()
