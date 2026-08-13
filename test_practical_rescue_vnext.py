import unittest

import numpy as np
import pandas as pd

from acsp.practical_rescue_vnext import (
    VNEXT_CATEGORICAL_FEATURES,
    VNEXT_NUMERIC_FEATURES,
    VNEXT_PROTOCOL_FINGERPRINT,
    build_vnext_features,
    frozen_v1_order,
    select_vnext_anchored_fifth,
)


class _FixedEstimator:
    def __init__(self, values):
        self.values = np.asarray(values, dtype=float)

    def predict(self, frame):
        if len(frame) != len(self.values):
            raise AssertionError(f"expected {len(self.values)} scoring rows, got {len(frame)}")
        return self.values.copy()


class PracticalRescueVNextTests(unittest.TestCase):
    @staticmethod
    def _candidates():
        return pd.DataFrame({
            "candidate_id": [f"c{i}" for i in range(1, 8)],
            "latitude": [35.00, 35.05, 35.10, 35.15, 35.20, 35.50, 35.80],
            "longitude": [139.00, 139.05, 139.10, 139.15, 139.20, 139.50, 139.80],
            "component_local_habitat_score": [0.90, 0.80, 0.70, 0.60, 0.50, 0.40, 0.30],
            "candidate_type": ["Habitat-match"] * 7,
            "surface_domain": ["terrestrial"] * 7,
            "distance_to_coast_m": [5000, 4000, 3000, 2000, 1500, 500, 100],
            "integrated_support_score": [0.8, 0.7, 0.6, 0.55, 0.5, 0.45, 0.4],
        })

    def test_frozen_v1_plant_order_is_the_anchor_source(self):
        order = frozen_v1_order(self._candidates(), "plant")
        self.assertEqual(order, ["c1", "c2", "c3", "c4", "c5"])

    def test_only_fifth_slot_can_be_replaced(self):
        # Scoring rows are c5, c6, c7 after c1-c4 are frozen anchors.
        estimator = _FixedEstimator([0.10, 0.11, 0.20])
        selected = select_vnext_anchored_fifth(self._candidates(), "plant", estimator)
        self.assertEqual(selected["candidate_id"].tolist(), ["c1", "c2", "c3", "c4", "c7"])
        self.assertEqual(selected["vnext_role"].tolist()[:4], ["frozen_v1_anchor"] * 4)
        self.assertEqual(selected["vnext_role"].iloc[4], "learned_residual_fifth")
        self.assertTrue(selected["vnext_replaced_frozen_v1_fifth"].all())
        self.assertEqual(selected["vnext_protocol_fingerprint"].unique().tolist(), [VNEXT_PROTOCOL_FINGERPRINT])

    def test_margin_below_0015_keeps_frozen_v1_fifth(self):
        estimator = _FixedEstimator([0.10, 0.11, 0.114])
        selected = select_vnext_anchored_fifth(self._candidates(), "plant", estimator)
        self.assertEqual(selected["candidate_id"].tolist(), ["c1", "c2", "c3", "c4", "c5"])
        self.assertEqual(selected["vnext_role"].iloc[4], "frozen_v1_fifth")
        self.assertFalse(selected["vnext_replaced_frozen_v1_fifth"].any())

    def test_features_include_domain_and_coast_context(self):
        features = build_vnext_features(self._candidates(), "plant")
        self.assertIn("surface_domain", features.columns)
        self.assertTrue((features["surface_domain"] == "terrestrial").all())
        self.assertAlmostEqual(features["pool_near_coast_1km_fraction"].iloc[0], 2 / 7)
        self.assertGreater(features.loc[6, "anchor_min_km"], features.loc[4, "anchor_min_km"])
        self.assertEqual(features["v1_selection_rank"].tolist(), [1, 2, 3, 4, 5, 6, 6])

    def test_heldout_columns_are_not_vnext_inputs(self):
        clean = self._candidates()
        contaminated = clean.copy()
        contaminated["held_out_occurrence_id"] = [f"h{i}" for i in range(len(clean))]
        contaminated["heldout_recovery_10km"] = np.linspace(0, 1, len(clean))
        contaminated["distance_to_heldout_km"] = np.linspace(10, 0, len(clean))
        a = build_vnext_features(clean, "animal")
        b = build_vnext_features(contaminated, "animal")
        columns = [*VNEXT_NUMERIC_FEATURES, *VNEXT_CATEGORICAL_FEATURES]
        pd.testing.assert_frame_equal(a[columns], b[columns])

    def test_small_pool_falls_back_without_model_call(self):
        class _NoCall:
            def predict(self, frame):
                raise AssertionError("estimator must not run when pool has <=Top-5 candidates")

        candidates = self._candidates().head(4)
        selected = select_vnext_anchored_fifth(candidates, "plant", _NoCall())
        self.assertEqual(selected["candidate_id"].tolist(), ["c1", "c2", "c3", "c4"])
        self.assertTrue((selected["vnext_role"] == "frozen_v1_fallback").all())


if __name__ == "__main__":
    unittest.main()
