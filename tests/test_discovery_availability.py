from __future__ import annotations

import unittest

from acsp.discovery.availability import AvailabilityState, resolve_availability_state


class DiscoveryAvailabilityTests(unittest.TestCase):
    def test_provider_failure_is_not_ecological_prediction_failure(self) -> None:
        decision = resolve_availability_state(
            country_or_outer_frame_available=False,
            historical_evidence_sufficient=False,
            robust_candidate_generation_status="not_attempted",
            recent_heldout_available=False,
        )
        self.assertEqual(decision.state, AvailabilityState.PROVIDER_BLOCKED)
        self.assertFalse(decision.robust_prediction_constructible)
        self.assertFalse(decision.ecological_prediction_failure)

    def test_sparse_historical_evidence_routes_to_sentinel_or_abstain(self) -> None:
        decision = resolve_availability_state(
            country_or_outer_frame_available=True,
            historical_evidence_sufficient=False,
            robust_candidate_generation_status="not_attempted",
            recent_heldout_available=True,
        )
        self.assertEqual(decision.state, AvailabilityState.SENTINEL_OR_ABSTAIN)
        self.assertFalse(decision.robust_prediction_constructible)
        self.assertTrue(decision.retrospective_evaluation_available)

    def test_empty_robust_result_stays_distinct_from_sparse_input(self) -> None:
        decision = resolve_availability_state(
            country_or_outer_frame_available=True,
            historical_evidence_sufficient=True,
            robust_candidate_generation_status="empty",
            recent_heldout_available=True,
        )
        self.assertEqual(decision.state, AvailabilityState.ROBUST_EMPTY)
        self.assertTrue(decision.robust_prediction_constructible)
        self.assertFalse(decision.ecological_prediction_failure)

    def test_generated_without_recent_data_is_prediction_ready_but_not_evaluable(self) -> None:
        decision = resolve_availability_state(
            country_or_outer_frame_available=True,
            historical_evidence_sufficient=True,
            robust_candidate_generation_status="generated",
            recent_heldout_available=False,
        )
        self.assertEqual(decision.state, AvailabilityState.ROBUST_READY_NOT_RETROSPECTIVELY_EVALUABLE)
        self.assertTrue(decision.robust_prediction_constructible)
        self.assertFalse(decision.retrospective_evaluation_available)

    def test_generated_with_recent_data_is_evaluable(self) -> None:
        decision = resolve_availability_state(
            country_or_outer_frame_available=True,
            historical_evidence_sufficient=True,
            robust_candidate_generation_status="generated",
            recent_heldout_available=True,
        )
        self.assertEqual(decision.state, AvailabilityState.ROBUST_READY_EVALUABLE)
        self.assertTrue(decision.robust_prediction_constructible)
        self.assertTrue(decision.retrospective_evaluation_available)

    def test_inconsistent_generation_state_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            resolve_availability_state(
                country_or_outer_frame_available=False,
                historical_evidence_sufficient=False,
                robust_candidate_generation_status="generated",
                recent_heldout_available=False,
            )
        with self.assertRaises(ValueError):
            resolve_availability_state(
                country_or_outer_frame_available=True,
                historical_evidence_sufficient=False,
                robust_candidate_generation_status="empty",
                recent_heldout_available=False,
            )


if __name__ == "__main__":
    unittest.main()
