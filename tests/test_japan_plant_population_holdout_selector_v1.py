from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

import develop_japan_plant_population_holdout_selector_v1 as d


class JapanPlantPopulationHoldoutSelectorTests(unittest.TestCase):
    def test_cluster_holdout_selection_is_deterministic_and_capped_at_two(self):
        clusters = [
            [(35.0, 139.0, "a")],
            [(35.1, 139.1, "b")],
            [(35.2, 139.2, "c")],
        ]
        first = d.select_holdout_clusters(clusters, 2)
        second = d.select_holdout_clusters(list(reversed(clusters)), 2)
        self.assertEqual([row[1] for row in first], [row[1] for row in second])
        self.assertEqual(len(first), 2)

    def test_training_frame_removes_entire_hidden_population(self):
        clusters = [
            [(35.0, 139.0, "a1"), (35.001, 139.001, "a2")],
            [(35.5, 139.5, "b1")],
            [(36.0, 140.0, "c1")],
        ]
        training = d.clusters_to_training_frame(clusters, 0)
        self.assertNotIn("a1", set(training["gbif_key"]))
        self.assertNotIn("a2", set(training["gbif_key"]))
        self.assertEqual(set(training["gbif_key"]), {"b1", "c1"})

    def test_build_selectors_uses_one_common_eligible_surface_and_exact_k(self):
        training = pd.DataFrame({
            "gbif_key": ["a", "b", "c", "d", "e"],
            "latitude": [35.0, 35.1, 35.2, 35.3, 35.4],
            "longitude": [139.0, 139.1, 139.2, 139.3, 139.4],
        })
        surface = pd.DataFrame({
            "latitude": [35.0, 35.5, 35.6, 35.7, 35.8],
            "longitude": [139.0, 139.5, 139.6, 139.7, 139.8],
            "survey_area_id": ["x"] * 5,
            "elevation": [1.0] * 5,
            "slope": [1.0] * 5,
            "aspect_sin": [0.0] * 5,
            "aspect_cos": [1.0] * 5,
            "roughness": [1.0] * 5,
            "tpi": [0.0] * 5,
        })
        prototypes = surface.iloc[:5].copy()
        environment = surface.iloc[[1, 2]].copy().reset_index(drop=True)

        class Audit:
            def as_dict(self):
                return {"ok": True}

        with patch.object(d, "_terrain_inputs", return_value=(surface, prototypes, 123)), \
             patch.object(d, "min_distance_to_historical", return_value=pd.Series([0.0, 1.0, 2.0, 3.0, 4.0]).to_numpy()), \
             patch.object(d, "validated_robust_candidate_patches", return_value=(environment, Audit())), \
             patch.object(d, "select_nearest_known", return_value=surface.iloc[[1, 2]].copy()), \
             patch.object(d, "select_spatial_balance", return_value=surface.iloc[[3, 4]].copy()):
            selectors, audit = d.build_training_selectors(
                training,
                bounds=(138.0, 34.0, 141.0, 37.0),
                pair_id=1,
                fold_number=1,
                known_exclusion_km=0.5,
            )
        self.assertEqual(len(selectors["eligible_surface"]), 4)
        self.assertEqual(audit["matched_k"], 2)
        self.assertEqual(len(selectors["environment"]), 2)
        self.assertEqual(len(selectors["nearest_known"]), 2)
        self.assertEqual(len(selectors["spatial_balance"]), 2)

    def test_summary_keeps_all_48_declared_pairs_in_denominator(self):
        cfg = d.load_protocol()
        pair_status = pd.DataFrame({
            "pair_id": list(range(1, 49)),
            "population_clusters": [3] * 48,
            "successful_folds": [1] * 48,
            "status": ["EVALUATED"] * 48,
        })
        folds = pd.DataFrame({
            "status": ["OK", "OK"],
            "environment_recovery_2km": [1.0, 0.0],
            "nearest_known_recovery_2km": [0.0, 0.0],
            "spatial_balance_recovery_2km": [0.0, 1.0],
            "random_recovery_2km": [0.25, 0.25],
            "environment_minus_nearest_2km": [1.0, 0.0],
            "environment_minus_spatial_balance_2km": [1.0, -1.0],
            "environment_minus_random_2km": [0.75, -0.25],
            "environment_recovery_5km": [1.0, 1.0],
            "nearest_known_recovery_5km": [0.0, 1.0],
            "spatial_balance_recovery_5km": [0.0, 1.0],
            "random_recovery_5km": [0.5, 0.5],
            "environment_minus_nearest_5km": [1.0, 0.0],
            "environment_minus_spatial_balance_5km": [1.0, 0.0],
            "environment_minus_random_5km": [0.5, 0.5],
            "environment_recovery_10km": [1.0, 1.0],
            "nearest_known_recovery_10km": [1.0, 1.0],
            "spatial_balance_recovery_10km": [1.0, 1.0],
            "random_recovery_10km": [0.75, 0.75],
            "environment_minus_nearest_10km": [0.0, 0.0],
            "environment_minus_spatial_balance_10km": [0.0, 0.0],
            "environment_minus_random_10km": [0.25, 0.25],
        })
        summary = d.summarize(folds, pair_status, cfg)
        self.assertEqual(summary["declared_plant_pairs"], 48)
        self.assertEqual(summary["successful_population_holdout_folds"], 2)
        self.assertAlmostEqual(summary["primary_environment_minus_nearest_mean"], 0.5)
        self.assertFalse(summary["heldout_used_for_generation_or_ranking"])


if __name__ == "__main__":
    unittest.main()
