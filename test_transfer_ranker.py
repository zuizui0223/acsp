import unittest

import pandas as pd

from acsp.transfer_ranker import (
    GBIF_BIAS_FEATURES,
    RankConfiguration,
    TransferObjective,
    calibrate_transfer_ranker,
    mean_pairwise_concordance,
)


class TransferRankerTests(unittest.TestCase):
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

    def test_pairwise_concordance_uses_complete_ordering(self):
        result = calibrate_transfer_ranker(self.candidates, self.detections)
        ranked = result["annotated_candidates"]
        configuration = RankConfiguration(("elevation_low",), (1.0,))
        value = mean_pairwise_concordance(ranked, configuration, ("a", "b", "c"))
        self.assertGreater(value, 0.99)

    def test_leave_one_area_out_and_objective_are_recorded(self):
        result = calibrate_transfer_ranker(
            self.candidates,
            self.detections,
            objective=TransferObjective(0.5, 0.5),
        )
        self.assertEqual(set(result["outer_selections"]["held_out_area"]), {"a", "b", "c"})
        self.assertIn("mean_area_pairwise_concordance", result["configuration_search"].columns)
        self.assertGreaterEqual(result["outer_cv_metrics"]["recall_2km"], 0.99)

    def test_ecology_only_excludes_direct_gbif_bias_features(self):
        result = calibrate_transfer_ranker(
            self.candidates,
            self.detections,
            excluded_features=sorted(GBIF_BIAS_FEATURES),
        )
        used = set(result["final_configuration"].feature_names)
        self.assertFalse(used.intersection(GBIF_BIAS_FEATURES))
        self.assertEqual(set(result["excluded_features"]), set(GBIF_BIAS_FEATURES))


if __name__ == "__main__":
    unittest.main()
