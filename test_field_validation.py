import unittest

import pandas as pd

from acsp.field_validation import (
    cluster_field_detections,
    detection_recovery_table,
    recovery_summary,
    stratified_random_recovery_benchmark,
)


class FieldValidationTests(unittest.TestCase):
    def test_forward_fills_islands_and_clusters_duplicate_points(self):
        locations = pd.DataFrame(
            {
                "island": ["oshima", None, "toshima", None],
                "latitude": [34.70, 34.7001, 34.53, 34.53],
                "longitude": [139.40, 139.4001, 139.28, 139.28],
            }
        )
        rows, clusters = cluster_field_detections(locations, cluster_radius_m=100)
        self.assertEqual(rows["island"].tolist(), ["oshima", "oshima", "toshima", "toshima"])
        self.assertEqual(len(clusters), 2)
        self.assertEqual(sorted(clusters["n_source_points"].tolist()), [2, 2])

    def test_recovery_is_computed_at_multiple_radii(self):
        candidates = pd.DataFrame(
            {"site_id": [1], "survey_area_id": ["a"], "latitude": [35.0], "longitude": [139.0]}
        )
        detections = pd.DataFrame(
            {"detection_cluster_id": [1], "island": ["a"], "latitude": [35.004], "longitude": [139.0]}
        )
        recovery = detection_recovery_table(candidates, detections, radii_km=(0.2, 1.0))
        self.assertFalse(bool(recovery.loc[0, "recovered_0.2km"]))
        self.assertTrue(bool(recovery.loc[0, "recovered_1km"]))
        summary = recovery_summary(recovery, radii_km=(0.2, 1.0))
        self.assertEqual(summary["n_recovered"].tolist(), [0, 1])

    def test_random_benchmark_keeps_area_quotas(self):
        pool = pd.DataFrame(
            {
                "site_id": [1, 2, 3, 4],
                "survey_area_id": ["a", "a", "b", "b"],
                "latitude": [35.0, 35.5, 34.0, 34.5],
                "longitude": [139.0, 139.5, 138.0, 138.5],
            }
        )
        detections = pd.DataFrame(
            {
                "detection_cluster_id": [1, 2],
                "latitude": [35.0, 34.0],
                "longitude": [139.0, 138.0],
            }
        )
        benchmark, draws = stratified_random_recovery_benchmark(
            pool,
            [1, 3],
            detections,
            radii_km=(1.0,),
            iterations=50,
            seed=7,
        )
        self.assertEqual(len(draws), 50)
        self.assertEqual(float(benchmark.loc[0, "acsp_detection_recall"]), 1.0)
        self.assertGreaterEqual(float(benchmark.loc[0, "lift_over_random"]), 0.0)


if __name__ == "__main__":
    unittest.main()
