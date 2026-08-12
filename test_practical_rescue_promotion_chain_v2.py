#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

import fit_practical_rescue_final_model_v2 as fit_v2
import freeze_practical_rescue_fresh_confirmation_protocol_v2 as freeze_v2
import run_practical_rescue_fresh_confirmation_pair_v2 as fresh_pair_v2


V2_FP = "74fec14b44035e897072b022d82ea30c00b27ce1bb95c16a0e9a5578a3d3da7a"
RESCUE_FP = "8f4f0a85ca636bf70b445ed1bb70b93a2df7de6a5b687b91d42c436b7e258c48"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PromotionChainV2Tests(unittest.TestCase):
    def test_final_fit_wrapper_binds_only_corrected_grts_identity(self):
        self.assertEqual(fit_v2.EXPECTED_GRTS_DEVELOPMENT_PROTOCOL, V2_FP)
        self.assertEqual(fit_v2.base.EXPECTED_GRTS_DEVELOPMENT_PROTOCOL, V2_FP)

    def test_fresh_pair_wrapper_substitutes_only_grts_runner(self):
        self.assertIs(fresh_pair_v2.run, fresh_pair_v2.base.run)
        self.assertIs(fresh_pair_v2.parser, fresh_pair_v2.base.parser)
        self.assertIs(fresh_pair_v2.base._run_grts, fresh_pair_v2._run_grts_v2)

    def test_fresh_protocol_freeze_is_model_bound_and_corrected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = root / "model.joblib"
            model.write_bytes(b"frozen-v2-model")
            model_manifest = root / "model_manifest.json"
            model_manifest.write_text(json.dumps({
                "status": "final_rescue_model_fitted_after_official_grts_development_gate",
                "development_pairs": 72,
                "development_folds": 360,
                "grts_outcomes_used_as_model_features_or_targets": False,
                "model_hyperparameters_changed_after_grts_gate": False,
                "rescue_protocol_fingerprint": RESCUE_FP,
                "grts_development_protocol_fingerprint": V2_FP,
                "model_sha256": sha(model),
            }) + "\n", encoding="utf-8")
            excluded = root / "excluded_taxa.csv"
            pd.DataFrame({
                "scientific_name": [f"taxon_{i:03d}" for i in range(264)],
                "exclusion_source": ["frozen"] * 264,
            }).to_csv(excluded, index=False)
            exclusion_manifest = root / "exclusion_manifest.json"
            exclusion_manifest.write_text(json.dumps({
                "excluded_unique_taxa": 264,
                "excluded_taxa_sha256": sha(excluded),
                "new_confirmation_taxa_sampled": False,
                "occurrence_outcomes_inspected": False,
            }) + "\n", encoding="utf-8")
            output = root / "fresh_v2_protocol.json"
            result = freeze_v2.run(
                model, model_manifest, excluded, exclusion_manifest, output
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["protocol_fingerprint"], payload["protocol_fingerprint"])
            self.assertEqual(payload["protocol_id"], "acsp-practical-rescue-fresh-confirmation-v2")
            self.assertEqual(payload["final_model"]["grts_development_protocol_fingerprint"], V2_FP)
            self.assertEqual(payload["official_grts"]["replacement_sites_requested"], 3)
            self.assertEqual(
                payload["official_grts"]["replacement_sites_effective_rule"],
                "min(replacement_sites_requested, max(candidate_frame_rows - n_base, 0))",
            )
            self.assertNotIn("replacement_sites", payload["official_grts"])
            self.assertEqual(payload["cohort"]["pair_count"], 192)
            self.assertEqual(payload["inference"]["minimum_absolute_recall_gain"], 0.015)
            self.assertFalse(payload["confirmation_taxa_sampled_at_protocol_freeze"])
            self.assertFalse(payload["confirmation_occurrence_outcomes_inspected_at_protocol_freeze"])
            self.assertFalse(payload["missing_pair_artifacts_scored_as_zero"])


if __name__ == "__main__":
    unittest.main()
