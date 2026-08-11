from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

import aggregate_practical_rescue_grts_development as aggregate
import benchmark_practical_rescue_grts_pair as pair


class PracticalRescueGrtsDevelopmentTests(unittest.TestCase):
    def test_protocol_fingerprint_is_frozen(self):
        payload, fingerprint = pair._canonical_protocol(
            Path("validation/acsp_practical_rescue_grts_development_protocol.json")
        )
        self.assertEqual(fingerprint, pair.EXPECTED_PROTOCOL)
        self.assertEqual(payload["official_grts"]["spsurvey_version"], "5.6.1")
        self.assertEqual(
            payload["official_grts"]["spsurvey_tag_commit"],
            "0914fcd071713fdab19f43d8d9a66436830bd917",
        )
        self.assertEqual(payload["official_grts"]["draws_per_fold"], 50)
        self.assertEqual(payload["official_grts"]["mindis_km"], 10.0)

    def test_global_pair_mapping_is_fixed(self):
        self.assertEqual(pair._group_parts("mixed_1"), ("mixed", 1, 1))
        self.assertEqual(pair._group_parts("mixed_24"), ("mixed", 24, 24))
        self.assertEqual(pair._group_parts("plants_1"), ("plants", 1, 25))
        self.assertEqual(pair._group_parts("plants_24"), ("plants", 24, 48))
        self.assertEqual(pair._group_parts("sdm_1"), ("sdm", 1, 49))
        self.assertEqual(pair._group_parts("sdm_24"), ("sdm", 24, 72))
        self.assertEqual(len(aggregate._expected_groups()), 72)

    def test_preoutcome_frame_drops_outcome_columns_but_retains_missing_local(self):
        frame = pd.DataFrame({
            "candidate_id": ["a", "b", "known"],
            "candidate_type": ["Habitat-match", "Survey-gap", "known-location"],
            "latitude": [35.0, 35.2, 35.4],
            "longitude": [139.0, 139.2, 139.4],
            "component_local_habitat_score": [0.9, np.nan, 0.8],
            "covered_heldout_ids": ["x", "y", "z"],
            "all_heldout_ids": ["x;y", "x;y", "x;y"],
            "heldout_distances_km": ["1", "2", "3"],
        })
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "candidates.csv"
            frame.to_csv(path, index=False)
            cleaned = pair._safe_preoutcome_candidates(path)
        self.assertEqual(cleaned["candidate_id"].tolist(), ["a", "b"])
        self.assertTrue(pd.isna(cleaned.loc[1, "component_local_habitat_score"]))
        self.assertNotIn("covered_heldout_ids", cleaned.columns)
        self.assertNotIn("all_heldout_ids", cleaned.columns)
        self.assertNotIn("heldout_distances_km", cleaned.columns)

    def test_empty_draw_contract_is_preoutcome(self):
        draws = pair._empty_draws(7, 3, 50, "5.6.1", "commit")
        self.assertEqual(len(draws), 50)
        self.assertEqual(draws["base_count"].sum(), 0)
        self.assertFalse(draws["outcomes_available_to_selector"].any())
        self.assertEqual(draws["draw_index"].tolist(), list(range(1, 51)))


if __name__ == "__main__":
    unittest.main()
