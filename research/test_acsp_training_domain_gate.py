from __future__ import annotations

import unittest

from acsp_training_domain_gate import infer_training_domain


class TrainingDomainGateTests(unittest.TestCase):
    def test_land_supported_vascular_plant_is_terrestrial(self):
        decision = infer_training_domain(
            {"kingdom": "Plantae", "phylum": "Tracheophyta", "class": "Magnoliopsida"},
            training_land_fraction=0.95,
        )
        self.assertEqual(decision.domain, "terrestrial")
        self.assertTrue(decision.terrestrial_policy_applicable)

    def test_training_land_fraction_overrides_plant_kingdom_for_seagrass_like_data(self):
        decision = infer_training_domain(
            {"kingdom": "Plantae", "phylum": "Tracheophyta", "class": "Liliopsida"},
            training_land_fraction=0.05,
        )
        self.assertEqual(decision.domain, "marine")
        self.assertFalse(decision.terrestrial_policy_applicable)

    def test_nonvascular_or_algal_plant_is_not_forced_into_terrestrial_policy(self):
        decision = infer_training_domain(
            {"kingdom": "Plantae", "phylum": "Chlorophyta"},
            training_land_fraction=0.95,
        )
        self.assertEqual(decision.domain, "non_vascular_or_algal_plant")
        self.assertFalse(decision.terrestrial_policy_applicable)

    def test_mixed_land_support_is_coastal_or_amphibious(self):
        decision = infer_training_domain(
            {"kingdom": "Animalia", "class": "Reptilia"},
            training_land_fraction=0.40,
        )
        self.assertEqual(decision.domain, "coastal_or_amphibious")
        self.assertFalse(decision.terrestrial_policy_applicable)

    def test_plant_without_land_support_measurement_remains_unverified(self):
        decision = infer_training_domain(
            {"kingdom": "Plantae", "phylum": "Tracheophyta"},
            training_land_fraction=None,
        )
        self.assertEqual(decision.domain, "terrestrial_candidate_unverified")
        self.assertFalse(decision.terrestrial_policy_applicable)

    def test_aquatic_taxonomy_not_overridden_by_merely_high_land_fraction(self):
        decision = infer_training_domain(
            {"kingdom": "Animalia", "class": "Actinopterygii"},
            training_land_fraction=0.95,
        )
        self.assertEqual(decision.domain, "inland_or_aquatic")
        self.assertFalse(decision.terrestrial_policy_applicable)


if __name__ == "__main__":
    unittest.main()
