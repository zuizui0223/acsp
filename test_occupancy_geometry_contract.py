import unittest

import numpy as np

from acsp.occupancy_geometry import (
    OccupancyGeometry,
    infer_occupancy_geometry,
    minimum_spanning_tree,
    pairwise_distances,
    project_states,
    robust_scale,
)


class OccupancyGeometryContractTests(unittest.TestCase):
    def test_public_result_fields_are_stable(self):
        geometry = infer_occupancy_geometry(np.array([[0.0], [1.0], [2.0]]))
        self.assertIsInstance(geometry, OccupancyGeometry)
        self.assertEqual(
            tuple(geometry.__dataclass_fields__),
            (
                "n_occurrences",
                "n_features",
                "span",
                "mst_length",
                "continuity",
                "gap_strength",
                "component_count",
                "labels",
                "mst_edges",
            ),
        )

    def test_one_dimensional_input_is_supported(self):
        values = np.array([[0.0], [1.0], [2.0], [3.0]])
        geometry = infer_occupancy_geometry(values)
        self.assertEqual(geometry.n_features, 1)
        self.assertAlmostEqual(geometry.continuity, 1.0)
        self.assertAlmostEqual(geometry.gap_strength, 1.0)

    def test_duplicate_rows_are_supported(self):
        values = np.array([[0.0], [0.0], [1.0], [1.0]])
        geometry = infer_occupancy_geometry(values)
        self.assertEqual(geometry.n_occurrences, 4)
        self.assertTrue(np.isfinite(geometry.mst_edges).all())
        self.assertGreaterEqual(geometry.component_count, 1)

    def test_all_identical_rows_have_neutral_geometry(self):
        values = np.ones((4, 3), dtype=float)
        geometry = infer_occupancy_geometry(values)
        self.assertEqual(geometry.span, 0.0)
        self.assertEqual(geometry.mst_length, 0.0)
        self.assertEqual(geometry.continuity, 1.0)
        self.assertEqual(geometry.gap_strength, 1.0)
        self.assertEqual(geometry.component_count, 1)

    def test_mst_shape_and_total_length_are_stable(self):
        values = np.array([[0.0], [1.0], [2.0]])
        distances = pairwise_distances(values)
        edges = minimum_spanning_tree(distances)
        self.assertEqual(edges.shape, (2, 3))
        self.assertAlmostEqual(float(edges[:, 2].sum()), 2.0 / 1.4826)

    def test_empty_candidate_projection_is_supported(self):
        occurrences = np.array([[0.0], [1.0], [2.0]])
        geometry = infer_occupancy_geometry(occurrences)
        distances, labels = project_states(occurrences, np.empty((0, 1)), geometry)
        self.assertEqual(distances.shape, (0,))
        self.assertEqual(labels.shape, (0,))

    def test_parameter_contract_is_enforced(self):
        values = np.array([[0.0], [1.0]])
        with self.assertRaises(ValueError):
            infer_occupancy_geometry(values, gap_multiplier=-1.0)
        for invalid in (0.0, -0.1, 1.1):
            with self.assertRaises(ValueError):
                infer_occupancy_geometry(values, span_quantile=invalid)

    def test_scaling_is_offset_and_positive_unit_invariant(self):
        values = np.array([[0.0, 2.0], [1.0, 3.0], [4.0, 8.0]])
        transformed = values * np.array([10.0, 0.5]) + np.array([100.0, -9.0])
        np.testing.assert_allclose(robust_scale(values), robust_scale(transformed))
        np.testing.assert_allclose(pairwise_distances(values), pairwise_distances(transformed))


if __name__ == "__main__":
    unittest.main()
