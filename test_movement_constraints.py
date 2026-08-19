import unittest

import pandas as pd

from acsp.auto_budget import infer_recommended_effort_from_matrix
from acsp.movement_constraints import apply_movement_constraints


PROTOCOL = {
    "daily_field_hours": 8.0,
    "search_minutes_per_cell": 30,
    "access_buffer_minutes_per_cell": 0,
    "protocol_id": "test",
    "taxon_group": "plant",
}


class MovementConstraintTests(unittest.TestCase):
    def test_forbidden_modes_are_removed(self):
        matrix = pd.DataFrame({
            "from_id": ["hub", "hub", "a"],
            "to_id": ["a", "b", "hub"],
            "travel_minutes": [10, 1, 10],
            "mode": ["walk", "flight", "walk"],
        })
        constrained = apply_movement_constraints(matrix, allowed_modes=["walk"])
        self.assertEqual(len(constrained), 2)
        self.assertNotIn("flight", constrained["mode"].tolist())

    def test_auto_effort_does_not_use_flight_edge(self):
        ordered = pd.DataFrame({
            "site_id": ["a", "b"],
            "latitude": [35.0, 35.1],
            "longitude": [139.0, 139.1],
            "cumulative_coverage_fraction": [0.7, 1.0],
        })
        matrix = pd.DataFrame({
            "from_id": ["hub", "a", "hub", "b"],
            "to_id": ["a", "hub", "b", "hub"],
            "travel_minutes": [10, 10, 1, 1],
            "mode": ["walk", "walk", "flight", "flight"],
        })
        selected, audit, frontier = infer_recommended_effort_from_matrix(
            ordered,
            travel_matrix=matrix,
            hub_id="hub",
            allowed_modes=["walk"],
            survey_protocol=PROTOCOL,
        )
        self.assertEqual(selected["site_id"].tolist(), ["a"])
        self.assertEqual(audit.unreachable_prefixes, 1)
        self.assertFalse(bool(frontier.loc[1, "reachable"]))

    def test_mode_column_is_required_for_automatic_movement_constraints(self):
        matrix = pd.DataFrame({
            "from_id": ["hub"],
            "to_id": ["a"],
            "travel_minutes": [10],
        })
        with self.assertRaisesRegex(ValueError, "explicit mode column"):
            apply_movement_constraints(matrix, allowed_modes=["walk"])


if __name__ == "__main__":
    unittest.main()
