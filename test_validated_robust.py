import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from acsp.robust_cli import main as robust_cli_main
from acsp.validated_robust import (
    VALIDATED_ROBUST_CONFIRMATION_FOLDS,
    VALIDATED_ROBUST_CONFIRMATION_PAIRS,
    VALIDATED_ROBUST_PATCH_MERGE_DISTANCE_M,
    VALIDATED_ROBUST_PRIMARY_RADIUS_KM,
    VALIDATED_ROBUST_STATUS,
    VALIDATED_ROBUST_SUPPORT_FRACTION,
    validated_robust_candidate_patches,
)


class ValidatedRobustPatchTests(unittest.TestCase):
    def setUp(self):
        n = 100
        self.universe = pd.DataFrame(
            {
                "latitude": 35.0 + np.arange(n) * 0.0001,
                "longitude": 139.0 + np.arange(n) * 0.0001,
                "survey_area_id": ["a"] * n,
                "f1": np.linspace(0.0, 10.0, n),
                "f2": np.linspace(0.0, 5.0, n),
            }
        )
        self.prototypes = pd.DataFrame(
            {
                "f1": [0.0, 0.1, 0.2, 0.3, 0.4],
                "f2": [0.0, 0.05, 0.10, 0.15, 0.20],
            }
        )

    def test_validated_api_has_no_user_tunable_scientific_threshold(self):
        patches, audit = validated_robust_candidate_patches(
            self.universe,
            self.prototypes,
            feature_columns=["f1", "f2"],
        )
        self.assertGreater(len(patches), 0)
        self.assertEqual(audit.prototype_count, 5)
        self.assertTrue(patches["ecological_support_threshold"].eq(VALIDATED_ROBUST_SUPPORT_FRACTION).all())
        self.assertTrue(patches["validation_status"].eq(VALIDATED_ROBUST_STATUS).all())
        self.assertTrue(patches["validation_primary_radius_km"].eq(VALIDATED_ROBUST_PRIMARY_RADIUS_KM).all())
        self.assertTrue(patches["validation_confirmation_pairs"].eq(VALIDATED_ROBUST_CONFIRMATION_PAIRS).all())
        self.assertTrue(patches["validation_confirmation_folds"].eq(VALIDATED_ROBUST_CONFIRMATION_FOLDS).all())
        self.assertEqual(VALIDATED_ROBUST_PATCH_MERGE_DISTANCE_M, 1000.0)

    def test_empty_validated_tier_keeps_a_readable_patch_schema(self):
        patches, audit = validated_robust_candidate_patches(
            self.universe.iloc[:5].copy(),
            self.prototypes,
            feature_columns=["f1", "f2"],
        )
        self.assertEqual(len(patches), 0)
        self.assertEqual(audit.prototype_count, 5)
        required = {
            "zone_id",
            "survey_area_id",
            "latitude",
            "longitude",
            "ecological_support_threshold",
            "validation_status",
        }
        self.assertTrue(required.issubset(patches.columns))

    def test_cli_exports_candidate_patches_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            universe = root / "universe.csv"
            prototypes = root / "prototypes.csv"
            output = root / "patches.csv"
            summary = root / "summary.json"
            self.universe.to_csv(universe, index=False)
            self.prototypes.to_csv(prototypes, index=False)
            exit_code = robust_cli_main(
                [
                    "--universe", str(universe),
                    "--prototypes", str(prototypes),
                    "--feature-columns", "f1,f2",
                    "--output", str(output),
                    "--summary-json", str(summary),
                ]
            )
            self.assertEqual(exit_code, 0)
            patches = pd.read_csv(output)
            manifest = json.loads(summary.read_text())
        self.assertGreater(len(patches), 0)
        self.assertEqual(manifest["output_unit"], "candidate_patch")
        self.assertFalse(manifest["routing_or_budget_optimization"])
        self.assertFalse(manifest["occupancy_probability_claim"])
        self.assertEqual(manifest["validated_support_fraction"], 0.025)
        self.assertEqual(manifest["validation_confirmation_pairs"], 96)
        self.assertEqual(manifest["validation_confirmation_folds"], 480)


if __name__ == "__main__":
    unittest.main()
