import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from aggregate_sdm_topk_benchmark import _sha256
from reaggregate_sdm_topk_benchmark import verify_pair_strict


class SdmTopKReaggregationTests(unittest.TestCase):
    def _build_pair(self, root: Path, *, include_fold: bool = True) -> Path:
        pair = root / "pair_001"
        pair.mkdir()
        result = pair / "fold_results.csv"
        pd.DataFrame({"pair_id": [1], "repeat": [1], "decision_method": ["frozen_acsp"]}).to_csv(result, index=False)
        pair_manifest = {
            "protocol_fingerprint": "protocol",
            "execution_contract_fingerprint": "contract",
            "expected_repeats": 1,
            "fold_result_sha256": _sha256(result),
        }
        (pair / "pair_manifest.json").write_text(json.dumps(pair_manifest))
        if include_fold:
            fold = pair / "fold_001"
            fold.mkdir()
            data = fold / "fold_result.csv"
            data.write_text("decision_method,heldout_recall\nfrozen_acsp,0.5\n")
            fold_manifest = {
                "protocol_fingerprint": "protocol",
                "execution_contract_fingerprint": "contract",
                "files": {
                    "fold_result": {"path": "fold_result.csv", "sha256": _sha256(data)}
                },
            }
            (fold / "fold_manifest.json").write_text(json.dumps(fold_manifest))
        return pair

    def test_top_level_fold_results_csv_is_not_treated_as_fold_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            pair = self._build_pair(Path(temp))
            manifest = verify_pair_strict(pair, "protocol", "contract")
            self.assertEqual(manifest["expected_repeats"], 1)

    def test_missing_expected_fold_directory_fails_verification(self):
        with tempfile.TemporaryDirectory() as temp:
            pair = self._build_pair(Path(temp), include_fold=False)
            with self.assertRaisesRegex(ValueError, "expected 1 fold directories"):
                verify_pair_strict(pair, "protocol", "contract")


if __name__ == "__main__":
    unittest.main()
