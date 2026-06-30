import unittest

import pandas as pd

from acsp import (
    choose_spatial_partition,
    model_performance_table,
    recommend_candidates,
    sdm_method_record,
)


class AcspPackageTests(unittest.TestCase):
    def test_area_quota(self):
        candidates = pd.DataFrame({
            "site_id": range(1, 9),
            "survey_area_id": [1, 1, 1, 1, 2, 2, 2, 2],
            "priority_score": [0.9, 0.8, 0.7, 0.6] * 2,
        })
        selected = recommend_candidates(candidates, per_area=3)
        self.assertEqual(selected.groupby("survey_area_id").size().to_dict(), {1: 3, 2: 3})

    def test_partition_and_method_reporting(self):
        method, reason = choose_spatial_partition(86, 1.8)
        self.assertEqual(method, "random holdout")
        metrics = pd.DataFrame({
            "algorithm": ["Random forest", "ExtraTrees"],
            "fold": ["diagnostic", "diagnostic"],
            "auc": [0.81, 0.87],
            "warning": ["random split may be optimistic", "random split may be optimistic"],
        })
        performance = model_performance_table(metrics)
        best = performance.loc[performance["model_role"].str.startswith("best"), "algorithm"].iloc[0]
        self.assertEqual(best, "ExtraTrees")
        record = sdm_method_record(
            n_source_records=87,
            n_qc_excluded=1,
            n_presence_used=86,
            n_background=500,
            partition_method=method,
            partition_reason=reason,
            variables=["bio1", "bio12"],
            performance=performance,
            environment_source="CHELSA 30-second COG",
            prediction_extent="QC-derived bounding box",
        )
        self.assertEqual(record["best_individual_model"], "ExtraTrees")
        self.assertIn("equal-weight mean", record["ensemble_method"])
        self.assertIn("optimistic", record["validation_caution"])


if __name__ == "__main__":
    unittest.main()
