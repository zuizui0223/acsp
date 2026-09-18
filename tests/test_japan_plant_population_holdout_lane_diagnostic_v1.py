from __future__ import annotations

import sys
from pathlib import Path
import unittest

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

import diagnose_japan_plant_population_holdout_lanes_v1 as d


class JapanPlantPopulationHoldoutLaneDiagnosticTests(unittest.TestCase):
    def _cfg(self):
        return {
            "lane_definition": {"boundary_km": 5.0},
            "recovery_radii_km": [2.0, 5.0, 10.0],
            "primary_diagnostic_radius_km": 5.0,
            "claim_boundary": "test boundary",
        }

    def _row(self, pair_id: int, lane: str, nearest_km: float, env5: float, near5: float):
        row = {
            "pair_id": pair_id,
            "fold_number": 1,
            "discovery_lane": lane,
            "nearest_training_population_km": nearest_km,
        }
        for radius in (2, 5, 10):
            env = env5 if radius == 5 else 0.0
            near = near5 if radius == 5 else 0.0
            spatial = 0.0
            random = 0.0
            row[f"environment_recovery_{radius}km"] = env
            row[f"nearest_known_recovery_{radius}km"] = near
            row[f"spatial_balance_recovery_{radius}km"] = spatial
            row[f"random_recovery_{radius}km"] = random
            row[f"environment_minus_nearest_{radius}km"] = env - near
            row[f"environment_minus_spatial_balance_{radius}km"] = env - spatial
            row[f"environment_minus_random_{radius}km"] = env - random
        return row

    def test_frozen_five_km_boundary(self):
        self.assertEqual(d.classify_lane(0.5), "LOCAL")
        self.assertEqual(d.classify_lane(5.0), "LOCAL")
        self.assertEqual(d.classify_lane(5.000001), "DETACHED")
        with self.assertRaises(ValueError):
            d.classify_lane(float("inf"))

    def test_summary_detects_directional_lane_separation_without_rescoring(self):
        table = pd.DataFrame([
            self._row(1, "LOCAL", 2.0, env5=0.0, near5=1.0),
            self._row(2, "DETACHED", 8.0, env5=1.0, near5=0.0),
        ])
        summary = d.summarize_lanes(table, self._cfg())
        self.assertEqual(summary["successful_source_folds"], 2)
        self.assertFalse(summary["selector_rebuilt"])
        self.assertFalse(summary["selector_rescored"])
        self.assertFalse(summary["lane_boundary_tuned"])
        self.assertEqual(summary["lanes"]["LOCAL"]["5km"]["mean_environment_minus_nearest"], -1.0)
        self.assertEqual(summary["lanes"]["DETACHED"]["5km"]["mean_environment_minus_nearest"], 1.0)
        self.assertTrue(summary["primary_5km_pattern"]["directional_lane_separation"])


if __name__ == "__main__":
    unittest.main()
