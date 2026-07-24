import unittest

import pandas as pd

from acsp.comparator_benchmark import (
    ALL_METHODS,
    StandardBaselineProtocol,
    comparator_inference,
    evaluate_candidate_fold,
    pair_level_intention_to_evaluate,
)


class ComparatorBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.protocol = StandardBaselineProtocol(
            repeats=2,
            random_draws=20,
            bootstrap_draws=200,
            sign_flip_draws=200,
            random_state=17,
        )
        self.candidates = pd.DataFrame({
            "candidate_id": [f"c{i}" for i in range(1, 7)],
            "candidate_type": ["habitat"] * 6,
            "latitude": [0.0, 0.02, 0.04, 1.0, 1.02, 1.04],
            "longitude": [0.0, 0.02, 0.04, 1.0, 1.02, 1.04],
            "component_local_habitat_score": [0.95, 0.90, 0.85, 0.80, 0.75, 0.70],
            "elevation": [10, 20, 30, 200, 220, 240],
            "slope": [1, 2, 3, 12, 13, 14],
            "aspect": [359, 1, 5, 170, 180, 190],
            "roughness": [0.1, 0.2, 0.3, 1.0, 1.1, 1.2],
            "tpi": [-1.0, -0.5, 0.0, 0.5, 1.0, 1.5],
            "covered_heldout_ids": ["h1", "h1;h2", "h2", "h3", "h2;h3", ""],
            "all_heldout_ids": ["h1;h2;h3"] * 6,
        })

    def test_all_frozen_methods_are_reported(self):
        result = evaluate_candidate_fold(
            self.candidates,
            "plant",
            self.protocol,
            pair_id=1,
            repeat=1,
        )
        self.assertEqual(set(result["decision_method"]), set(ALL_METHODS))
        self.assertTrue(result["status"].eq("ok").all())
        oracle = result.loc[result["decision_method"].eq("heldout_greedy_oracle"), "heldout_recall"].iloc[0]
        self.assertGreaterEqual(oracle, result["heldout_recall"].max() - 1e-12)

    def test_pair_level_ite_retains_missing_pair_as_zero(self):
        first = evaluate_candidate_fold(
            self.candidates,
            "plant",
            self.protocol,
            pair_id=1,
            repeat=1,
        )
        second = evaluate_candidate_fold(
            self.candidates,
            "plant",
            self.protocol,
            pair_id=1,
            repeat=2,
        )
        declared = pd.DataFrame({
            "pair_id": [1, 2],
            "taxon_group": ["plant", "plant"],
        })
        pair_table = pair_level_intention_to_evaluate(
            pd.concat([first, second], ignore_index=True),
            declared,
            self.protocol,
        )
        missing_random = pair_table[
            pair_table["pair_id"].eq(2)
            & pair_table["decision_method"].eq("random_same_pool_mean")
        ].iloc[0]
        self.assertEqual(missing_random["ite_recall"], 0.0)
        missing_environment = pair_table[
            pair_table["pair_id"].eq(2)
            & pair_table["decision_method"].eq("environmental_maximin")
        ].iloc[0]
        self.assertFalse(missing_environment["pair_method_eligible"])
        self.assertTrue(pd.isna(missing_environment["ite_recall"]))

    def test_pair_level_inference_uses_pairs_not_folds(self):
        rows = []
        for pair_id, shift in ((1, 0.0), (2, -0.1), (3, 0.05)):
            for method, value in (
                ("frozen_acsp", 0.4 + shift),
                ("random_same_pool_mean", 0.2 + shift),
                ("local_evidence_top_k", 0.35 + shift),
            ):
                rows.append({
                    "pair_id": pair_id,
                    "taxon_group": "plant",
                    "decision_method": method,
                    "ite_recall": value,
                })
        inference = comparator_inference(pd.DataFrame(rows), self.protocol)
        comparison = inference[
            inference["decision_method"].eq("frozen_acsp")
            & inference["reference_method"].eq("random_same_pool_mean")
        ].iloc[0]
        self.assertEqual(comparison["eligible_pairs"], 3)
        self.assertAlmostEqual(comparison["mean_pair_difference"], 0.2)

    def test_protocol_fingerprint_is_stable(self):
        self.assertEqual(
            self.protocol.manifest()["fingerprint"],
            self.protocol.manifest()["fingerprint"],
        )


if __name__ == "__main__":
    unittest.main()
