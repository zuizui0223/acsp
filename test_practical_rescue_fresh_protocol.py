#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from freeze_practical_rescue_fresh_confirmation_protocol import (
    GRTS_DEVELOPMENT_PROTOCOL_FINGERPRINT,
    RESCUE_PROTOCOL_FINGERPRINT,
    run,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FreshRescueProtocolTests(unittest.TestCase):
    def test_protocol_is_bound_to_model_and_264_taxa_before_sampling(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = root / "model.joblib"
            model.write_bytes(b"frozen-model-bytes")
            model_manifest = root / "model_manifest.json"
            model_manifest.write_text(json.dumps({
                "status": "final_rescue_model_fitted_after_official_grts_development_gate",
                "development_pairs": 72,
                "development_folds": 360,
                "grts_outcomes_used_as_model_features_or_targets": False,
                "model_hyperparameters_changed_after_grts_gate": False,
                "rescue_protocol_fingerprint": RESCUE_PROTOCOL_FINGERPRINT,
                "grts_development_protocol_fingerprint": GRTS_DEVELOPMENT_PROTOCOL_FINGERPRINT,
                "model_sha256": _sha256(model),
            }) + "\n")
            excluded = root / "excluded_taxa.csv"
            pd.DataFrame({
                "scientific_name": [f"taxon_{i:03d}" for i in range(264)],
                "exclusion_source": ["frozen"] * 264,
            }).to_csv(excluded, index=False)
            exclusion_manifest = root / "exclusion_manifest.json"
            exclusion_manifest.write_text(json.dumps({
                "excluded_unique_taxa": 264,
                "excluded_taxa_sha256": _sha256(excluded),
                "new_confirmation_taxa_sampled": False,
                "occurrence_outcomes_inspected": False,
            }) + "\n")
            output = root / "protocol.json"
            result = run(model, model_manifest, excluded, exclusion_manifest, output)
            payload = json.loads(output.read_text())
            self.assertEqual(payload["cohort"]["pair_count"], 192)
            self.assertEqual(payload["official_grts"]["draws_per_fold"], 50)
            self.assertEqual(payload["inference"]["minimum_absolute_recall_gain"], 0.015)
            self.assertFalse(payload["confirmation_taxa_sampled_at_protocol_freeze"])
            self.assertFalse(payload["missing_pair_artifacts_scored_as_zero"])
            self.assertEqual(result["final_model_sha256"], _sha256(model))

    def test_wrong_development_pair_count_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = root / "model.joblib"
            model.write_bytes(b"x")
            model_manifest = root / "model_manifest.json"
            model_manifest.write_text(json.dumps({
                "status": "final_rescue_model_fitted_after_official_grts_development_gate",
                "development_pairs": 71,
                "development_folds": 360,
                "grts_outcomes_used_as_model_features_or_targets": False,
                "model_hyperparameters_changed_after_grts_gate": False,
                "rescue_protocol_fingerprint": RESCUE_PROTOCOL_FINGERPRINT,
                "grts_development_protocol_fingerprint": GRTS_DEVELOPMENT_PROTOCOL_FINGERPRINT,
                "model_sha256": _sha256(model),
            }) + "\n")
            excluded = root / "excluded_taxa.csv"
            pd.DataFrame({"scientific_name": [f"t{i}" for i in range(264)]}).to_csv(excluded, index=False)
            exclusion_manifest = root / "exclusion_manifest.json"
            exclusion_manifest.write_text(json.dumps({
                "excluded_unique_taxa": 264,
                "excluded_taxa_sha256": _sha256(excluded),
                "new_confirmation_taxa_sampled": False,
                "occurrence_outcomes_inspected": False,
            }) + "\n")
            with self.assertRaisesRegex(ValueError, "complete 72-pair"):
                run(model, model_manifest, excluded, exclusion_manifest, root / "protocol.json")


if __name__ == "__main__":
    unittest.main()
