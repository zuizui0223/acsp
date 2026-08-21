import inspect
import unittest

import pandas as pd

from acsp.operational_selector import select_movement_constrained_patches


class MovementConstrainedOperationalSelectorTests(unittest.TestCase):
    def test_site_count_is_automatic_and_cluster_knee_stops_at_one_per_component(self):
        candidates = pd.DataFrame(
            {
                "candidate_patch_id": [f"p{i}" for i in range(6)],
                "survey_area_id": ["A"] * 6,
                "latitude": [0.0] * 6,
                "longitude": [0.000, 0.005, 0.010, 1.000, 1.005, 1.010],
                "candidate_patch_radius_m": [100.0] * 6,
            }
        )
        selected, audit = select_movement_constrained_patches(
            candidates, max_transition_km=2.0
        )
        self.assertEqual(audit.movement_component_count, 2)
        self.assertEqual(audit.selected_count, 2)
        self.assertEqual(selected["_input_index"].tolist(), [1, 4])
        self.assertEqual(selected["operational_segment"].tolist(), [1, 2])
        self.assertTrue(selected["movement_parent_input_index"].isna().all())
        self.assertFalse(audit.user_site_count_required)
        self.assertFalse(audit.user_coverage_target_required)
        self.assertFalse(audit.validated_candidate_membership_changed)

    def test_linear_coverage_curve_keeps_all_candidates_conservatively(self):
        candidates = pd.DataFrame(
            {
                "survey_area_id": ["A"] * 3,
                "latitude": [0.0, 0.0, 0.0],
                "longitude": [0.000, 0.015, 0.030],
                "candidate_patch_radius_m": [50.0, 50.0, 50.0],
            }
        )
        selected, audit = select_movement_constrained_patches(
            candidates, max_transition_km=2.0
        )
        self.assertEqual(audit.movement_component_count, 1)
        self.assertEqual(audit.selected_count, 3)
        self.assertEqual(selected["_input_index"].tolist(), [0, 1, 2])
        parents = selected["movement_parent_input_index"]
        self.assertTrue(pd.isna(parents.iloc[0]))
        self.assertEqual(parents.iloc[1:].astype(int).tolist(), [0, 1])
        self.assertAlmostEqual(audit.final_coverage_fraction, 1.0)

    def test_survey_area_is_a_hard_movement_and_coverage_barrier(self):
        candidates = pd.DataFrame(
            {
                "survey_area_id": ["island-a", "island-b"],
                "latitude": [35.0, 35.0],
                "longitude": [139.0, 139.0],
                "candidate_patch_radius_m": [5000.0, 5000.0],
            }
        )
        selected, audit = select_movement_constrained_patches(
            candidates, max_transition_km=100.0
        )
        self.assertEqual(audit.movement_component_count, 2)
        self.assertEqual(audit.selected_count, 2)
        self.assertEqual(selected["operational_segment"].tolist(), [1, 2])
        self.assertAlmostEqual(audit.final_coverage_fraction, 1.0)

    def test_movement_components_do_not_share_coverage_when_transition_is_tighter(self):
        candidates = pd.DataFrame(
            {
                "survey_area_id": ["A", "A"],
                "latitude": [0.0, 0.0],
                "longitude": [0.000, 0.006],
                "candidate_patch_radius_m": [500.0, 500.0],
            }
        )
        # The internal coverage floor is 1 km, so these points could cover each
        # other geometrically. The 0.5 km movement limit splits them into two
        # components; coverage must stay component-local rather than leaking.
        selected, audit = select_movement_constrained_patches(
            candidates, max_transition_km=0.5
        )
        self.assertEqual(audit.movement_component_count, 2)
        self.assertEqual(audit.selected_count, 2)
        self.assertAlmostEqual(audit.final_coverage_fraction, 1.0)

    def test_api_has_no_site_budget_or_coverage_target_argument(self):
        parameters = inspect.signature(select_movement_constrained_patches).parameters
        self.assertIn("max_transition_km", parameters)
        self.assertNotIn("max_sites", parameters)
        self.assertNotIn("target_coverage", parameters)
        self.assertNotIn("survey_days", parameters)
        self.assertNotIn("budget", parameters)

    def test_invalid_transition_limit_is_rejected(self):
        candidates = pd.DataFrame(
            {"survey_area_id": ["A"], "latitude": [35.0], "longitude": [139.0]}
        )
        with self.assertRaises(ValueError):
            select_movement_constrained_patches(candidates, max_transition_km=0.0)


if __name__ == "__main__":
    unittest.main()
