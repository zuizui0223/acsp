import unittest

import pandas as pd

from acsp import (
    aggregate_candidates_to_zones,
    compare_zone_rankings,
    recommend_survey_zones,
    zone_agreement_summary,
)


class SurveyZoneTests(unittest.TestCase):
    def test_nearby_points_merge_into_one_zone(self):
        candidates = pd.DataFrame({
            "site_id": [1, 2], "survey_area_id": [1, 1],
            "priority_score": [0.8, 0.9],
            "latitude": [35.0, 35.004], "longitude": [139.0, 139.004],
            "candidate_type": ["Occurrence-supported", "Habitat-match"],
        })
        zones = aggregate_candidates_to_zones(candidates, merge_distance_m=1000)
        self.assertEqual(len(zones), 1)
        self.assertEqual(zones.iloc[0]["zone_member_count"], 2)
        self.assertEqual(zones.iloc[0]["representative_site_id"], 2)
        self.assertEqual(zones.iloc[0]["zone_merge_threshold_m"], 1000.0)

    def test_complete_link_prevents_chain_merging(self):
        candidates = pd.DataFrame({
            "site_id": [1, 2, 3], "priority_score": [0.9, 0.8, 0.7],
            "latitude": [35.0, 35.007, 35.014], "longitude": [139.0] * 3,
        })
        zones = aggregate_candidates_to_zones(candidates, merge_distance_m=1000)
        self.assertEqual(len(zones), 2)
        self.assertEqual(sorted(zones["zone_member_count"].tolist()), [1, 2])

    def test_representative_uses_evidence_and_access_not_centroid(self):
        candidates = pd.DataFrame({
            "site_id": [1, 2], "priority_score": [0.7, 0.7],
            "access_score": [0.2, 1.0], "occurrence_support_score": [0.2, 0.9],
            "latitude": [35.0, 35.002], "longitude": [139.0, 139.002],
        })
        zone = aggregate_candidates_to_zones(candidates, merge_distance_m=1000).iloc[0]
        self.assertEqual(zone["representative_site_id"], 2)

    def test_rank_change_and_agreement_classes(self):
        initial_candidates = pd.DataFrame({
            "site_id": [1, 2], "priority_score": [0.9, 0.8],
            "occurrence_support_score": [0.9, 0.1], "habitat_score": [0.8, 0.1],
            "latitude": [35.0, 35.03], "longitude": [139.0, 139.03],
        })
        model_candidates = initial_candidates.copy()
        model_candidates["model_support_score"] = [0.8, 1.0]
        model_candidates["priority_score"] = [0.2, 1.0]
        initial = aggregate_candidates_to_zones(initial_candidates, merge_distance_m=500)
        compared = compare_zone_rankings(initial, aggregate_candidates_to_zones(model_candidates, merge_distance_m=500))
        self.assertEqual(compared.iloc[0]["rank_change"], 1)
        self.assertEqual(set(compared["agreement_class"]), {"Concordant — highest priority", "Model-led exploration"})
        summary = zone_agreement_summary(compared)
        self.assertEqual(summary["concordant_top_zones"], 1)
        self.assertEqual(summary["model_led_top_zones"], 1)

    def test_recommendation_returns_zones_not_duplicate_points(self):
        candidates = pd.DataFrame({
            "site_id": [1, 2, 3], "priority_score": [0.9, 0.8, 0.7],
            "latitude": [35.0, 35.002, 35.03], "longitude": [139.0, 139.002, 139.03],
        })
        zones = recommend_survey_zones(candidates, merge_distance_m=1000)
        self.assertEqual(len(zones), 2)
        self.assertIn("recommended_zone_rank", zones.columns)

    def test_zone_reports_when_evidence_maxima_come_from_different_points(self):
        candidates = pd.DataFrame({
            "site_id": [1, 2], "priority_score": [0.9, 0.7],
            "occurrence_support_score": [1.0, 0.1],
            "habitat_score": [0.1, 1.0],
            "model_support_score": [0.2, 0.9],
            "latitude": [35.0, 35.002], "longitude": [139.0, 139.002],
        })
        zone = aggregate_candidates_to_zones(candidates, merge_distance_m=1000).iloc[0]
        self.assertIn("not independently summed", zone["zone_evidence_scope"])
        self.assertEqual(zone["observed_source_site_id"], 1)
        self.assertEqual(zone["local_source_site_id"], 2)
        self.assertEqual(zone["model_source_site_id"], 2)

    def test_zone_score_uses_integrated_candidate_and_agreement_not_component_sum(self):
        candidates = pd.DataFrame({
            "site_id": [1, 2], "priority_score": [0.8, 0.7],
            "evidence_agreement_score": [0.4, 0.9],
            "occurrence_support_score": [1.0, 0.0], "habitat_score": [0.0, 1.0],
            "latitude": [35.0, 35.002], "longitude": [139.0, 139.002],
        })
        zone = aggregate_candidates_to_zones(candidates, merge_distance_m=1000).iloc[0]
        self.assertAlmostEqual(zone["zone_score"], 0.81, places=6)
        self.assertIn("not added", zone["zone_score_method"])


if __name__ == "__main__":
    unittest.main()
