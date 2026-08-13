import unittest

import numpy as np
import pandas as pd

from acsp.practical_rescue_router import (
    ROUTER_CATEGORICAL_FEATURES,
    ROUTER_NUMERIC_FEATURES,
    ROUTER_PROTOCOL_FINGERPRINT,
    build_router_features,
    choose_router_policy,
    export_linear_router_artifact,
    frozen_v1_ids,
    make_router_estimator,
    predict_linear_router_artifact,
    router_training_weights,
    select_routed_candidates,
)


class PracticalRescueRouterTests(unittest.TestCase):
    @staticmethod
    def _candidates():
        return pd.DataFrame({
            "candidate_id": [f"c{i}" for i in range(1, 8)],
            "latitude": [35.00, 35.03, 35.08, 35.20, 35.35, 35.50, 35.75],
            "longitude": [139.00, 139.02, 139.07, 139.18, 139.31, 139.51, 139.78],
            "component_local_habitat_score": [0.90, 0.83, 0.72, 0.65, 0.55, 0.42, 0.30],
            "candidate_type": [
                "Habitat-match", "Habitat-match", "Survey-gap", "Environmental-test",
                "Habitat-match", "Survey-gap", "Environmental-test",
            ],
            "surface_domain": ["terrestrial", "terrestrial", "coastal", "coastal", "marine", "marine", "terrestrial"],
            "distance_to_coast_m": [5000, 4000, 800, 500, 100, 50, 7000],
        })

    def test_build_router_features_is_outcome_free(self):
        candidates = self._candidates()
        v1 = frozen_v1_ids(candidates, "plant")
        rescue = ["c1", "c2", "c4", "c5", "c7"]
        clean = build_router_features(candidates, "plant", v1, rescue)
        contaminated = candidates.copy()
        contaminated["heldout_recovery_10km"] = np.linspace(0, 1, len(candidates))
        contaminated["distance_to_heldout_km"] = np.linspace(10, 0, len(candidates))
        contaminated["scientific_name"] = "forbidden-name"
        dirty = build_router_features(contaminated, "plant", v1, rescue)
        columns = [*ROUTER_NUMERIC_FEATURES, *ROUTER_CATEGORICAL_FEATURES]
        pd.testing.assert_frame_equal(clean[columns], dirty[columns])

    def test_threshold_fails_closed_to_frozen_v1(self):
        candidates = self._candidates()
        v1 = frozen_v1_ids(candidates, "plant")
        rescue = ["c1", "c2", "c4", "c5", "c7"]
        self.assertEqual(choose_router_policy(0.014999), "frozen_v1")
        self.assertEqual(choose_router_policy(float("nan")), "frozen_v1")
        selected = select_routed_candidates(candidates, v1, rescue, 0.014999)
        self.assertEqual(selected["candidate_id"].tolist(), v1)
        self.assertTrue((selected["router_chosen_policy"] == "frozen_v1").all())
        self.assertEqual(selected["router_protocol_fingerprint"].unique().tolist(), [ROUTER_PROTOCOL_FINGERPRINT])

    def test_threshold_can_select_rescue_without_modifying_its_set(self):
        candidates = self._candidates()
        v1 = frozen_v1_ids(candidates, "plant")
        rescue = ["c1", "c2", "c4", "c5", "c7"]
        selected = select_routed_candidates(candidates, v1, rescue, 0.015)
        self.assertEqual(selected["candidate_id"].tolist(), rescue)
        self.assertTrue((selected["router_chosen_policy"] == "frozen_rescue_v2").all())

    def test_pair_equal_training_weights(self):
        ids = pd.Series([1, 1, 1, 1, 1, 2, 2, 3])
        weights = router_training_weights(ids)
        totals = pd.DataFrame({"pair": ids, "weight": weights}).groupby("pair")["weight"].sum()
        np.testing.assert_allclose(totals.to_numpy(float), np.ones(3))

    def test_exported_json_reproduces_sklearn_ridge(self):
        candidates = self._candidates()
        rows = []
        targets = []
        pair_ids = []
        base_v1 = frozen_v1_ids(candidates, "plant")
        rescue_options = [
            ["c1", "c2", "c4", "c5", "c7"],
            ["c1", "c3", "c4", "c6", "c7"],
            ["c1", "c2", "c3", "c6", "c7"],
        ]
        for pair_id in range(1, 7):
            for repeat in range(3):
                shifted = candidates.copy()
                shifted["component_local_habitat_score"] = (
                    shifted["component_local_habitat_score"] - pair_id * 0.005 + repeat * 0.002
                ).clip(0, 1)
                group = "plant" if pair_id % 2 else "animal"
                v1 = frozen_v1_ids(shifted, group)
                rescue = rescue_options[(pair_id + repeat) % len(rescue_options)]
                rows.append(build_router_features(shifted, group, v1, rescue).iloc[0])
                targets.append((pair_id - 3.5) * 0.01 + repeat * 0.004)
                pair_ids.append(pair_id)
        frame = pd.DataFrame(rows)
        estimator = make_router_estimator()
        weights = router_training_weights(pd.Series(pair_ids))
        columns = [*ROUTER_NUMERIC_FEATURES, *ROUTER_CATEGORICAL_FEATURES]
        estimator.fit(frame[columns], np.asarray(targets, dtype=float), model__sample_weight=weights)
        expected = estimator.predict(frame[columns])
        artifact = export_linear_router_artifact(
            estimator,
            training_rows=len(frame),
            development_pairs=6,
            source_fingerprint="unit-test",
        )
        actual = predict_linear_router_artifact(frame[columns], artifact)
        np.testing.assert_allclose(actual, expected, atol=1e-12, rtol=1e-12)


if __name__ == "__main__":
    unittest.main()
