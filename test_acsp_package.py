import unittest

import pandas as pd
import numpy as np

from acsp import (
    DEFAULT_ENSEMBLE_ALGORITHMS,
    choose_spatial_partition,
    filter_candidates_to_extent,
    integrated_candidate_scores,
    model_performance_table,
    make_classifier,
    predict_equal_weight_ensemble,
    recommend_candidates,
    sdm_method_record,
    spatial_block_recovery_validation,
)


class AcspPackageTests(unittest.TestCase):
    def test_integrated_score_renormalizes_when_model_is_unavailable(self):
        candidate = pd.DataFrame({
            "site_id": [1], "occurrence_support_score": [0.8],
            "analogue_score": [0.7], "access_score": [0.6],
        })
        without_model = integrated_candidate_scores(candidate)
        with_empty_model = integrated_candidate_scores(candidate.assign(sdm_suitability=np.nan))
        self.assertAlmostEqual(
            without_model.loc[0, "integrated_support_score"],
            with_empty_model.loc[0, "integrated_support_score"],
        )
        self.assertFalse(with_empty_model.loc[0, "component_macro_model_available"])

    def test_distance_excluded_score_ignores_occurrence_and_gap_evidence(self):
        candidates = pd.DataFrame({
            "site_id": [1, 2], "occurrence_support_score": [1.0, 0.0],
            "survey_gap_score": [0.0, 1.0], "environmental_novelty": [0.0, 1.0],
            "analogue_score": [0.8, 0.8], "sdm_suitability": [0.7, 0.7], "access_score": [0.6, 0.6],
        })
        scored = integrated_candidate_scores(candidates, exclude_occurrence_derived=True)
        self.assertEqual(scored["integrated_support_score"].nunique(), 1)
        self.assertTrue(scored["distance_excluded_validation_score"].all())

    def test_spatial_block_recovery_is_reproducible_and_uses_training_only(self):
        occurrences = pd.DataFrame({
            "record_id": range(8),
            "latitude": [35.0, 35.02, 35.5, 35.52, 36.0, 36.02, 36.5, 36.52],
            "longitude": [139.0, 139.02, 139.5, 139.52, 140.0, 140.02, 140.5, 140.52],
        })
        training_sizes = []

        def builder(training):
            training_sizes.append(len(training))
            return pd.DataFrame({
                "site_id": range(1, 9),
                "latitude": occurrences["latitude"], "longitude": occurrences["longitude"],
                "candidate_type": ["Habitat-match"] * 8,
                "analogue_score": np.linspace(1.0, 0.3, 8),
                "sdm_suitability": np.linspace(0.9, 0.2, 8),
                "access_score": [0.8] * 8,
            })

        folds, summary = spatial_block_recovery_validation(
            occurrences, builder, block_degrees=0.25, repeats=3, top_k=3,
            hit_radius_km=10.0, random_draws=10, random_state=7,
        )
        self.assertEqual(summary["valid_repeats"], 3)
        self.assertTrue(all(size < len(occurrences) for size in training_sizes))
        self.assertTrue(folds["distance_excluded_recall"].between(0, 1).all())

    def test_all_default_classifiers_produce_an_ensemble_probability(self):
        X = pd.DataFrame({"bio1": np.linspace(0, 1, 24), "bio12": np.tile([0.1, 0.9], 12)})
        y = np.array([0] * 12 + [1] * 12)
        models = {}
        for name in DEFAULT_ENSEMBLE_ALGORITHMS:
            model = make_classifier(name)
            model.fit(X, y)
            models[name] = model
        prediction = predict_equal_weight_ensemble(models, X)
        self.assertEqual(set(models), set(DEFAULT_ENSEMBLE_ALGORITHMS))
        self.assertEqual(len(prediction), len(X))
        self.assertTrue(np.all((prediction >= 0) & (prediction <= 1)))

    def test_area_quota(self):
        candidates = pd.DataFrame({
            "site_id": range(1, 9),
            "survey_area_id": [1, 1, 1, 1, 2, 2, 2, 2],
            "priority_score": [0.9, 0.8, 0.7, 0.6] * 2,
        })
        selected = recommend_candidates(candidates, per_area=3)
        self.assertEqual(selected.groupby("survey_area_id").size().to_dict(), {1: 3, 2: 3})

    def test_extent_filters_candidates_before_ranking(self):
        candidates = pd.DataFrame({
            "site_id": [1, 2, 3],
            "priority_score": [0.7, 0.9, 1.0],
            "latitude": [35.0, 35.2, 36.0],
            "longitude": [139.0, 139.2, 140.0],
        })
        extent = (138.9, 34.9, 139.3, 35.3)
        filtered = filter_candidates_to_extent(candidates, extent)
        selected = recommend_candidates(candidates, extent=extent)
        self.assertEqual(filtered["site_id"].tolist(), [1, 2])
        self.assertEqual(selected["site_id"].tolist(), [2, 1])

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
