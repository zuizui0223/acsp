import unittest

import pandas as pd

from acsp.validated_core import ValidatedCorePolicy, select_validated_core


class ValidatedCoreTests(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame({
            "site_id": ["known", "near-a", "near-b", "far"],
            "candidate_type": ["known-location", "habitat", "habitat", "habitat"],
            "latitude": [0.0, 0.0, 0.0, 10.0],
            "longitude": [0.0, 0.1, 0.2, 10.0],
            "component_local_habitat_score": [1.0, 0.9, 0.8, 0.7],
        })

    def test_plant_policy_filters_known_and_uses_local_rank(self):
        policy = ValidatedCorePolicy.for_taxon_group("plant")
        selected = select_validated_core(self.frame, policy)
        self.assertNotIn("known", set(selected["site_id"]))
        self.assertEqual(selected["site_id"].tolist()[:2], ["near-a", "near-b"])
        self.assertEqual(
            selected["validated_core_policy"].iloc[0],
            "frozen_plant_10km_top5",
        )

    def test_animal_policy_retains_geographic_complementarity(self):
        policy = ValidatedCorePolicy.for_taxon_group("animal")
        selected = select_validated_core(self.frame, policy)
        self.assertIn("far", set(selected["site_id"]))
        self.assertAlmostEqual(policy.geographic_complementarity_weight, 0.25)

    def test_manifest_is_stable_and_bounded(self):
        policy = ValidatedCorePolicy.for_taxon_group("plant")
        first = policy.manifest()
        second = policy.manifest()
        self.assertEqual(first["fingerprint"], second["fingerprint"])
        self.assertIn("exact-site occupancy", first["unsupported_claims"])


if __name__ == "__main__":
    unittest.main()
