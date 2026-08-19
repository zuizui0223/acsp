import unittest

import pandas as pd

from acsp.movement_constraints import apply_movement_constraints


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
