import unittest

import pandas as pd

from acsp.validated_core import ValidatedCorePolicy, select_validated_core


class ValidatedCoreComplementarityTests(unittest.TestCase):
    def test_animal_policy_can_select_a_distant_lower_score_candidate(self):
        candidates = pd.DataFrame({
            "site_id": ["near-a", "near-b", "far"],
            "candidate_type": ["habitat", "habitat", "habitat"],
            "latitude": [0.0, 0.0, 10.0],
            "longitude": [0.1, 0.2, 10.0],
            "component_local_habitat_score": [0.9, 0.8, 0.7],
        })
        policy = ValidatedCorePolicy(
            taxon_group="animal",
            top_k=2,
            evidence_weight=0.75,
        )
        selected = select_validated_core(candidates, policy)
        self.assertEqual(selected["site_id"].tolist(), ["near-a", "far"])


if __name__ == "__main__":
    unittest.main()
