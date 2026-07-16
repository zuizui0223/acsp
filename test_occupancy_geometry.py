import unittest

import numpy as np

from acsp.occupancy_geometry import (
    infer_occupancy_geometry,
    pairwise_distances,
    project_states,
    robust_scale,
)


class OccupancyGeometryTests(unittest.TestCase):
    def test_invariant_to_feature_units_and_offsets(self):
        values = np.array([[0.0, 2.0], [0.2, 2.2], [3.0, 8.0], [3.2, 8.2]])
        transformed = values * np.array([1000.0, 0.01]) + np.array([50.0, -4.0])
        first = infer_occupancy_geometry(values)
        second = infer_occupancy_geometry(transformed)
        self.assertAlmostEqual(first.span, second.span)
        self.assertAlmostEqual(first.continuity, second.continuity)
        self.assertAlmostEqual(first.gap_strength, second.gap_strength)
        np.testing.assert_array_equal(first.labels, second.labels)

    def test_two_modes_are_separated_by_large_gap(self):
        values = np.array(
            [
                [0.0, 0.0],
                [0.1, -0.1],
                [-0.1, 0.1],
                [8.0, 8.0],
                [8.1, 7.9],
                [7.9, 8.1],
            ]
        )
        geometry = infer_occupancy_geometry(values, gap_multiplier=2.0)
        self.assertEqual(geometry.component_count, 2)
        self.assertGreater(geometry.gap_strength, 10.0)
        self.assertEqual(len(set(geometry.labels[:3])), 1)
        self.assertEqual(len(set(geometry.labels[3:])), 1)
        self.assertNotEqual(geometry.labels[0], geometry.labels[3])

    def test_continuous_chain_remains_one_component(self):
        values = np.column_stack([np.arange(8, dtype=float), np.arange(8, dtype=float)])
        geometry = infer_occupancy_geometry(values)
        self.assertEqual(geometry.component_count, 1)
        self.assertAlmostEqual(geometry.gap_strength, 1.0)

    def test_constant_features_are_neutral(self):
        values = np.array([[0.0, 4.0], [1.0, 4.0], [2.0, 4.0]])
        scaled = robust_scale(values)
        self.assertTrue(np.allclose(scaled[:, 1], 0.0))
        distances = pairwise_distances(values)
        self.assertTrue(np.isfinite(distances).all())

    def test_projection_preserves_disjunct_components(self):
        occurrences = np.array([[0.0], [0.2], [10.0], [10.2]])
        geometry = infer_occupancy_geometry(occurrences, gap_multiplier=2.0)
        distance, label = project_states(
            occurrences,
            np.array([[0.1], [10.1], [5.0]]),
            geometry,
        )
        self.assertEqual(label[0], geometry.labels[0])
        self.assertEqual(label[1], geometry.labels[2])
        self.assertGreater(distance[2], distance[0])
        self.assertGreater(distance[2], distance[1])

    def test_input_validation(self):
        with self.assertRaises(ValueError):
            infer_occupancy_geometry(np.array([[1.0, 2.0]]))
        with self.assertRaises(ValueError):
            infer_occupancy_geometry(np.array([[0.0], [np.nan]]))


if __name__ == "__main__":
    unittest.main()
