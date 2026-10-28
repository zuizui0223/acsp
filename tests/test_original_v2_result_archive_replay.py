"""Original ACSP v2 receipt/guard tests, no old ZIP required in CI."""
from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from research import replay_original_robust_patch_v2_artifacts as m


class OriginalRobustPatchArchiveTests(unittest.TestCase):
    def test_original_receipt_is_source_bounded(self):
        receipt = m.read_receipt()
        m.check_primary_table(receipt)
        self.assertEqual(receipt["artifacts"]["cohort"]["id"], 9394691112)
        self.assertEqual(receipt["artifacts"]["confirmation"]["id"], 9396133154)
        self.assertEqual(receipt["source_runs"]["confirmation"], 32337884576)
        self.assertEqual(receipt["independent_recomputation"]["bootstrap_draws"], 30000)
        self.assertEqual(receipt["archive_contents"]["fold_rows_all_radii"], 1920)
        self.assertFalse(receipt["scientific_claims"]["original_occurrence_inputs_recovered"])
        self.assertFalse(receipt["scientific_claims"]["original_GBIF_download_DOI_verified"])
        self.assertFalse(receipt["scientific_claims"]["new_biological_validation"])

    def test_claim_of_original_GBIF_input_recovery_must_fail_closed(self):
        document = m.read_receipt()
        document["scientific_claims"]["original_occurrence_inputs_recovered"] = True
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "receipt.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "raw GBIF input"):
                m.read_receipt(path)

    def test_changed_zip_checksum_cannot_pass(self):
        source = m.read_receipt()["artifacts"]["confirmation"]
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "not-the-original.zip"
            with zipfile.ZipFile(path, mode="w") as z:
                z.writestr("confirmation-results/confirmation_summary.json", "{}")
            with self.assertRaisesRegex(ValueError, "archive SHA256 differs"):
                m._members(path, source)

    def test_no_raw_fold_files_in_original_member_allowlist(self):
        record = m.read_receipt()
        sources = set(record["artifacts"]["confirmation"]["member_sha256"])
        self.assertEqual(len(sources), 6)
        self.assertEqual(sources, {
            "confirmation-folds/export_manifest.json",
            "confirmation-folds/pair_export_status.csv",
            "confirmation-results/confirmation_fold_results.csv",
            "confirmation-results/confirmation_pair_results.csv",
            "confirmation-results/confirmation_radius_summary.csv",
            "confirmation-results/confirmation_summary.json",
        })
        self.assertFalse(any("held_out_occurrences" in p or "training_occurrences" in p
                             for p in sources))

    def test_incorrect_paper_result_is_detected(self):
        receipt = m.read_receipt()
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "table.csv"
            original = m.PRIMARY_TABLE.read_text(encoding="utf-8")
            self.assertIn("0.08558708102617191", original)
            p.write_text(original.replace("0.08558708102617191",
                                          "0.18558708102617191", 1), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "primary table changed"):
                m.check_primary_table(receipt, p)


if __name__ == "__main__":
    unittest.main()
