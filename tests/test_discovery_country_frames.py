from __future__ import annotations

import unittest

from acsp.discovery.country_frames import (
    CountryFrameState,
    plan_automatic_global_country,
    plan_explicit_target_country,
    rank_historical_country_frames,
)


class DiscoveryCountryFrameTests(unittest.TestCase):
    def test_auto_mode_prefers_evidence_rich_supported_country(self) -> None:
        plan = plan_automatic_global_country(
            {"LV": 6, "CN": 7207, "JP": 3445},
            provider_supported_country_codes={"LV", "CN", "JP"},
            historical_min_count=5,
            tie_break_seed=7,
        )
        self.assertEqual(plan.state, CountryFrameState.READY)
        self.assertEqual(plan.selected_country_code, "CN")
        self.assertEqual(plan.candidates[0].historical_record_count, 7207)
        self.assertFalse(plan.heldout_used)
        self.assertFalse(plan.field_outcomes_used)

    def test_auto_mode_skips_provider_unsupported_country_without_outcomes(self) -> None:
        plan = plan_automatic_global_country(
            {"HK": 8, "TW": 17881, "JP": 1351},
            provider_supported_country_codes={"TW", "JP"},
            historical_min_count=5,
        )
        self.assertEqual(plan.selected_country_code, "TW")
        hk = next(candidate for candidate in plan.candidates if candidate.country_code == "HK")
        self.assertEqual(hk.state, CountryFrameState.PROVIDER_UNSUPPORTED)

    def test_explicit_country_never_substitutes_an_easier_country(self) -> None:
        plan = plan_explicit_target_country(
            "HK",
            {"HK": 8, "TW": 17881},
            provider_supported_country_codes={"TW"},
            historical_min_count=5,
        )
        self.assertEqual(plan.mode, "explicit_target")
        self.assertEqual(plan.state, CountryFrameState.PROVIDER_UNSUPPORTED)
        self.assertIsNone(plan.selected_country_code)
        self.assertFalse(plan.country_substitution_after_target_declaration)

    def test_insufficient_history_is_not_promoted_by_another_country_in_target_mode(self) -> None:
        plan = plan_explicit_target_country(
            "CN",
            {"CN": 4, "JP": 987},
            provider_supported_country_codes={"CN", "JP"},
            historical_min_count=5,
        )
        self.assertEqual(plan.state, CountryFrameState.INSUFFICIENT_HISTORICAL_EVIDENCE)
        self.assertIsNone(plan.selected_country_code)

    def test_rank_keeps_ineligible_countries_in_audit(self) -> None:
        candidates = rank_historical_country_frames(
            {"A": 10, "B": 4, "C": 100},
            provider_supported_country_codes={"A", "B"},
            historical_min_count=5,
            tie_break_seed=1,
        )
        lookup = {candidate.country_code: candidate for candidate in candidates}
        self.assertEqual(lookup["A"].state, CountryFrameState.READY)
        self.assertEqual(lookup["B"].state, CountryFrameState.INSUFFICIENT_HISTORICAL_EVIDENCE)
        self.assertEqual(lookup["C"].state, CountryFrameState.PROVIDER_UNSUPPORTED)
        self.assertEqual(lookup["A"].evidence_rank, 1)

    def test_negative_historical_count_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            rank_historical_country_frames(
                {"JP": -1},
                provider_supported_country_codes={"JP"},
            )


if __name__ == "__main__":
    unittest.main()
