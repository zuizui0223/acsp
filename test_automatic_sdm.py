import unittest

import numpy as np
import pandas as pd

from acsp.automatic_sdm import (
    AUTO_SDM_VARIABLES,
    NASA_POWER_MONTHS,
    AutomaticSdmCoreConfig,
    derive_power_bioclim,
    fit_automatic_sdm_core,
    interpolate_power_bioclim,
    score_automatic_sdm_candidates,
    select_sdm_top_k,
)


class AutomaticSdmCoreTests(unittest.TestCase):
    def _monthly(self, latitude, longitude, values):
        row = {"latitude": latitude, "longitude": longitude}
        row.update(dict(zip(NASA_POWER_MONTHS, values)))
        return row

    def test_power_bioclim_matches_production_formula(self):
        temperatures = np.arange(1.0, 13.0)
        precip_daily = np.full(12, 2.0)
        temp = pd.DataFrame([self._monthly(35.0, 140.0, temperatures)])
        precip = pd.DataFrame([self._monthly(35.0, 140.0, precip_daily)])
        climate = derive_power_bioclim(temp, precip)
        self.assertEqual(tuple(climate[AUTO_SDM_VARIABLES].columns), AUTO_SDM_VARIABLES)
        self.assertAlmostEqual(climate.loc[0, "bio1"], float(temperatures.mean()))
        self.assertAlmostEqual(climate.loc[0, "bio4"], float(temperatures.std(ddof=0) * 100.0))
        monthly = precip_daily * np.array([31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
        self.assertAlmostEqual(climate.loc[0, "bio12"], float(monthly.sum()))
        self.assertAlmostEqual(climate.loc[0, "bio14"], float(monthly.min()))
        self.assertAlmostEqual(
            climate.loc[0, "bio15"],
            float(monthly.std(ddof=0) * 100.0 / monthly.mean()),
        )

    def test_power_missing_sentinel_is_treated_as_nan(self):
        temperatures = np.full(12, 10.0)
        temperatures[0] = -999.0
        precip_daily = np.ones(12)
        temp = pd.DataFrame([self._monthly(35.0, 140.0, temperatures)])
        precip = pd.DataFrame([self._monthly(35.0, 140.0, precip_daily)])
        climate = derive_power_bioclim(temp, precip)
        self.assertAlmostEqual(climate.loc[0, "bio1"], 10.0)

    def test_interpolation_returns_exact_cell_at_exact_coordinate(self):
        climate = pd.DataFrame({
            "latitude": [35.0, 36.0],
            "longitude": [140.0, 141.0],
            "bio1": [10.0, 20.0],
            "bio4": [100.0, 200.0],
            "bio12": [1000.0, 2000.0],
            "bio14": [10.0, 20.0],
            "bio15": [30.0, 40.0],
        })
        points = pd.DataFrame({"latitude": [35.0], "longitude": [140.0]})
        result = interpolate_power_bioclim(points, climate)
        for variable in AUTO_SDM_VARIABLES:
            self.assertAlmostEqual(result.loc[0, variable], climate.loc[0, variable], places=8)

    def test_fit_score_and_topk_are_deterministic(self):
        rows = []
        for index in range(20):
            presence = 1 if index < 10 else 0
            center = 1.0 if presence else -1.0
            rows.append({
                "presence": presence,
                "bio1": center + index * 0.01,
                "bio4": center * 2 + index * 0.02,
                "bio12": center * 3 + index * 0.03,
                "bio14": center * 4 + index * 0.04,
                "bio15": center * 5 + index * 0.05,
            })
        training = pd.DataFrame(rows)
        config = AutomaticSdmCoreConfig(random_state=23)
        fit_one = fit_automatic_sdm_core(training, config=config)
        fit_two = fit_automatic_sdm_core(training, config=config)
        candidates = pd.DataFrame({
            "candidate_id": ["b", "a", "c"],
            "bio1": [1.2, -1.2, 0.8],
            "bio4": [2.2, -2.2, 1.8],
            "bio12": [3.2, -3.2, 2.8],
            "bio14": [4.2, -4.2, 3.8],
            "bio15": [5.2, -5.2, 4.8],
        })
        scored_one = score_automatic_sdm_candidates(candidates, fit_one)
        scored_two = score_automatic_sdm_candidates(candidates, fit_two)
        np.testing.assert_allclose(scored_one["sdm_suitability"], scored_two["sdm_suitability"])
        self.assertGreater(scored_one.loc[0, "sdm_suitability"], scored_one.loc[1, "sdm_suitability"])
        selected = select_sdm_top_k(scored_one, 2)
        self.assertEqual(len(selected), 2)
        self.assertEqual(selected["decision_method"].unique().tolist(), ["fitted_sdm_top_k"])

    def test_topk_ties_use_candidate_id(self):
        candidates = pd.DataFrame({
            "candidate_id": ["z", "a", "m"],
            "sdm_suitability": [0.5, 0.5, 0.5],
        })
        selected = select_sdm_top_k(candidates, 2)
        self.assertEqual(selected["candidate_id"].tolist(), ["a", "m"])

    def test_manifest_is_stable_and_bounded(self):
        config = AutomaticSdmCoreConfig()
        first = config.manifest()
        second = config.manifest()
        self.assertEqual(first["fingerprint"], second["fingerprint"])
        self.assertEqual(first["variables"], list(AUTO_SDM_VARIABLES))
        self.assertIn("not calibrated occupancy probability", first["score_interpretation"])


if __name__ == "__main__":
    unittest.main()
