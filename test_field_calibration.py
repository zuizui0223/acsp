import unittest

import pandas as pd

from acsp.field_calibration import (
    RankConfiguration,
    add_within_area_rank_features,
    apply_rank_configuration,
    attach_field_utility,
    calibrate_field_ranker,
    select_one_per_area,
)


class FieldCalibrationTests(unittest.TestCase):
    def setUp(self):
        rows = []
        detections = []
        site_id = 1
        for area_index, area in enumerate(("a", "b", "c")):
            base_lat = 34.0 + area_index
            detections.append({"island": area, "latitude": base_lat, "longitude": 139.0})
            for offset, elevation in ((0.0, 10.0), (0.02, 100.0), (0.04, 200.0)):
                rows.append(
                    {
                        "site_id": site_id,
                        "survey_area_id": area,
                        "latitude": base_lat + offset,
                        "longitude": 139.0,
                        "analogue_score": 1.0 - offset,
                        "elevation": elevation,
                        "slope": elevation / 20.0,
                        "roughness": elevation / 50.0,
                        "distance_to_coast_m": elevation,
                        "nearest_known_population_km": offset * 100.0,
                        "target_record_density": 1.0 if offset == 0.0 else 0.0,
                        "tpi": offset,
                    }
                )
                site_id += 1
        self.candidates = pd.DataFrame(rows)
        self.detections = pd.DataFrame(detections)

    def test_field_utility_is_highest_near_detection(self):
        annotated = attach_field_utility(self.candidates, self.detections)
        for _, group in annotated.groupby("survey_area_id"):
            self.assertEqual(int(group.loc[group["field_multiscale_utility"].idxmax(), "site_id"]), int(group.iloc[0]["site_id"]))

    def test_rank_configuration_selects_one_per_area(self):
        annotated = attach_field_utility(self.candidates, self.detections)
        ranked, _ = add_within_area_rank_features(annotated)
        scored = apply_rank_configuration(
            ranked,
            RankConfiguration(("elevation_low", "gbif_density_high"), (0.5, 0.5)),
        )
        selected = select_one_per_area(scored)
        self.assertEqual(len(selected), 3)
        self.assertEqual(selected.groupby("survey_area_id").size().to_dict(), {"a": 1, "b": 1, "c": 1})

    def test_calibration_keeps_held_area_out_of_rule_selection(self):
        result = calibrate_field_ranker(self.candidates, self.detections)
        outer = result["outer_selections"]
        folds = result["outer_configurations"]
        self.assertEqual(set(outer["held_out_area"]), {"a", "b", "c"})
        self.assertEqual(set(folds["held_out_area"]), {"a", "b", "c"})
        self.assertEqual(len(result["final_selections"]), 3)
        self.assertGreaterEqual(result["development_metrics"]["recall_2km"], 0.99)


if __name__ == "__main__":
    unittest.main()
