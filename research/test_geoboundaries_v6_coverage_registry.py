from __future__ import annotations

import copy
import unittest

import geoboundaries_v6_coverage_contract as mod


class FrozenGeoBoundariesCoverageRegistryTests(unittest.TestCase):
    def test_frozen_registry_validates_without_network(self) -> None:
        payload = mod.load_contract()
        coverage = payload["coverage"]
        self.assertEqual(coverage["simplified_adm0_count"], 230)
        self.assertEqual(len(coverage["unsupported_iso_alpha2_alpha3"]), 20)
        self.assertEqual(coverage["provider_only_alpha3"], ["XKX"])

    def test_iso_mapping_partitions_exactly_by_frozen_provider_support(self) -> None:
        payload = mod.load_contract()
        supported = set(payload["coverage"]["supported_alpha3"])
        mapping = mod.load_iso_mapping()
        supported_iso = {alpha2 for alpha2, alpha3 in mapping.items() if alpha3 in supported}
        unsupported_iso = {alpha2 for alpha2, alpha3 in mapping.items() if alpha3 not in supported}
        self.assertEqual(len(supported_iso), 229)
        self.assertEqual(len(unsupported_iso), 20)
        self.assertEqual(supported_iso | unsupported_iso, set(mapping))
        self.assertFalse(supported_iso & unsupported_iso)

    def test_future_eligibility_is_deterministic_and_has_no_fallback(self) -> None:
        payload = mod.load_contract()
        mapping = mod.load_iso_mapping()
        supported = set(payload["coverage"]["supported_alpha3"])
        for alpha2, alpha3 in mapping.items():
            observed = mod.alpha2_to_alpha3_if_supported(alpha2)
            if alpha3 in supported:
                self.assertEqual(observed, alpha3)
                self.assertEqual(mod.require_supported_alpha2(alpha2), alpha3)
            else:
                self.assertIsNone(observed)
                with self.assertRaises(mod.ProviderCoverageError):
                    mod.require_supported_alpha2(alpha2)

    def test_contract_fingerprint_detects_tampering(self) -> None:
        payload = mod.load_contract()
        tampered = copy.deepcopy(payload)
        tampered["policy"]["alternate_geometry_provider_fallback_allowed"] = True
        with self.assertRaises(ValueError):
            mod.validate_contract(tampered)

    def test_provider_only_code_does_not_create_an_iso_alpha2_alias(self) -> None:
        payload = mod.load_contract()
        self.assertEqual(payload["coverage"]["provider_only_alpha3"], ["XKX"])
        self.assertNotIn("XKX", set(mod.load_iso_mapping().values()))


if __name__ == "__main__":
    unittest.main()
