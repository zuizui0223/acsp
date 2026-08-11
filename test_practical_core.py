import json
from pathlib import Path
import unittest

import pandas as pd

from acsp.practical_core import (
    PRACTICAL_CORE_FINGERPRINT,
    PracticalCorePolicy,
    protocol_fingerprint,
    select_practical_core,
)


class PracticalCoreTests(unittest.TestCase):
    def candidates(self):
        return pd.DataFrame({
            "candidate_id": ["c3", "c1", "c2", "known", "c5", "c4"],
            "candidate_type": [
                "habitat-match", "survey-gap", "environmental-test",
                "known-location", "habitat-match", "other",
            ],
            "latitude": [35.3, 35.1, 35.2, 35.0, 35.5, 35.4],
            "longitude": [139.3, 139.1, 139.2, 139.0, 139.5, 139.4],
            "component_local_habitat_score": [0.80, 0.90, 0.90, 1.00, 0.70, 0.75],
            "heldout_distances_km": [0, 0, 0, 0, 0, 0],
            "covered_heldout_ids": ["x", "x", "x", "x", "x", "x"],
            "scientific_name": ["Species alpha"] * 6,
            "geographic_stratum": ["north"] * 6,
            "survey_gap_score": [1, 0, 0.5, 1, 0.2, 0.8],
            "access_score": [0, 1, 0.5, 1, 0.2, 0.8],
        })

    def test_protocol_fingerprint_matches_committed_artifact(self):
        payload = json.loads(
            (Path(__file__).parent / "validation" / "acsp_practical_core_protocol.json").read_text()
        )
        self.assertEqual(payload["fingerprint"], PRACTICAL_CORE_FINGERPRINT)
        self.assertEqual(protocol_fingerprint(payload), PRACTICAL_CORE_FINGERPRINT)

    def test_same_policy_for_plants_and_animals(self):
        candidates = self.candidates()
        plant = select_practical_core(candidates, PracticalCorePolicy())
        animal = select_practical_core(candidates, PracticalCorePolicy())
        self.assertEqual(plant["candidate_id"].tolist(), animal["candidate_id"].tolist())

    def test_filters_known_and_uses_deterministic_local_ranking(self):
        selected = select_practical_core(self.candidates(), PracticalCorePolicy(top_k=4))
        self.assertEqual(selected["candidate_id"].tolist(), ["c1", "c2", "c3", "c4"])
        self.assertNotIn("known", selected["candidate_id"].tolist())
        self.assertEqual(selected["practical_core_rank"].tolist(), [1, 2, 3, 4])

    def test_forbidden_columns_cannot_change_decision(self):
        first = self.candidates()
        second = first.copy()
        second["heldout_distances_km"] = [999, 1, 500, 0, 2, 100]
        second["covered_heldout_ids"] = ["a", "b", "c", "d", "e", "f"]
        second["scientific_name"] = ["Different species"] * len(second)
        second["geographic_stratum"] = ["south"] * len(second)
        second["survey_gap_score"] = list(reversed(second["survey_gap_score"].tolist()))
        second["access_score"] = list(reversed(second["access_score"].tolist()))
        a = select_practical_core(first)
        b = select_practical_core(second)
        self.assertEqual(a["candidate_id"].tolist(), b["candidate_id"].tolist())

    def test_missing_local_score_fails_closed(self):
        with self.assertRaises(ValueError):
            select_practical_core(self.candidates().drop(columns="component_local_habitat_score"))


if __name__ == "__main__":
    unittest.main()
