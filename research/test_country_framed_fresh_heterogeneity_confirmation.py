from __future__ import annotations

import unittest

import pandas as pd

from predeclare_country_framed_fresh_heterogeneity_confirmation import (
    EXPECTED_PROTOCOL_FINGERPRINT,
    exclusion_sets,
    protocol,
    select_hash_min,
    target_strata,
)


class FreshHeterogeneityConfirmationContractTest(unittest.TestCase):
    def test_protocol_is_frozen_before_fresh_identities(self) -> None:
        cfg = protocol()
        self.assertEqual(cfg["protocol_fingerprint"], EXPECTED_PROTOCOL_FINGERPRINT)
        self.assertEqual(cfg["cohort"]["target_taxa"], 48)
        self.assertEqual(cfg["cohort"]["plant"], 24)
        self.assertEqual(cfg["cohort"]["animal"], 24)
        self.assertFalse(cfg["method"]["scientific_method_changed"])
        self.assertFalse(cfg["decision"]["retuning_allowed"])
        self.assertFalse(cfg["decision"]["subset_rescue_allowed"])

    def test_target_strata_are_balanced_before_identities(self) -> None:
        counts = {0: 0, 1: 0, 2: 0, 3: 0}
        for region in range(1, 13):
            a, b = target_strata(region)
            self.assertNotEqual(a, b)
            counts[a] += 1
            counts[b] += 1
        self.assertEqual(counts, {0: 6, 1: 6, 2: 6, 3: 6})

    def test_hash_selection_is_order_invariant(self) -> None:
        pool = pd.DataFrame(
            {
                "speciesKey": [90000003, 90000001, 90000002],
                "scientific_name": ["Fresh gamma", "Fresh alpha", "Fresh beta"],
                "coordinate_records": [50, 30, 40],
            }
        )
        kwargs = dict(seed=2026082601, region=3, group="plant", stratum=2)
        a = select_hash_min(pool, **kwargs)
        b = select_hash_min(pool.iloc[::-1].reset_index(drop=True), **kwargs)
        self.assertEqual(int(a["speciesKey"]), int(b["speciesKey"]))
        self.assertEqual(str(a["_identity_hash"]), str(b["_identity_hash"]))

    def test_prior_v4_taxa_are_explicitly_excluded(self) -> None:
        cfg = protocol()
        keys, names = exclusion_sets(cfg["exclusions"])
        self.assertIn(7308143, keys)
        self.assertIn("Scutellaria strigillosa Hemsl.", names)

    def test_heterogeneity_cannot_change_primary_decision(self) -> None:
        cfg = protocol()
        self.assertTrue(cfg["heterogeneity"]["prospective_from_prior_diagnostic"])
        self.assertFalse(cfg["heterogeneity"]["changes_primary_decision"])
        self.assertFalse(cfg["heterogeneity"]["permits_plant_exclusion"])
        self.assertTrue(cfg["primary_gates"]["all_required"])


if __name__ == "__main__":
    unittest.main()
