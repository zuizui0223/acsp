#!/usr/bin/env python3
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

import prepare_japan_plant_broad_frame_preflight_v4 as f


class JapanPlantBroadFramePreflightV4Tests(unittest.TestCase):
    def test_final_qualifier_selection_is_deterministic(self):
        rows = [
            {
                "candidate_id": i,
                "speciesKey": 7100000 + i,
                "scientific_name": f"Plantus {i}",
                "selected_region": "kanto",
                "historical_population_count": 5 + i,
            }
            for i in range(1, 51)
        ]
        a = f.select_final_qualifiers(rows, final_count=24, seed=2026091104)
        b = f.select_final_qualifiers(list(reversed(rows)), final_count=24, seed=2026091104)
        self.assertEqual([x["speciesKey"] for x in a], [x["speciesKey"] for x in b])
        self.assertEqual(len(a), 24)
        self.assertEqual(len({x["speciesKey"] for x in a}), 24)

    def test_insufficient_qualifiers_fail_closed(self):
        rows = [
            {"speciesKey": 1 + i, "scientific_name": f"Plantus {i}"}
            for i in range(23)
        ]
        self.assertEqual(f.select_final_qualifiers(rows, final_count=24, seed=1), [])

    def test_protocol_keeps_issue_203_thresholds_and_information_barrier(self):
        cfg = f._protocol()
        stage = cfg["stage2_historical_qualification"]
        self.assertEqual(stage["candidate_identity_count"], 96)
        self.assertEqual(stage["final_taxa"], 24)
        self.assertEqual(stage["minimum_historical_population_clusters_in_selected_region"], 5)
        self.assertFalse(stage["selection_uses_2021_2025"])
        self.assertTrue(cfg["outcome"]["open_only_after_24_taxa_and_candidate_hashes_frozen"])
        self.assertEqual(cfg["primary_endpoint"]["minimum_temporally_evaluable_taxa"], 12)
        self.assertEqual(
            cfg["primary_endpoint"]["minimum_fraction_evaluable_taxa_with_strictly_positive_difference"],
            0.5,
        )
        self.assertEqual(cfg["primary_endpoint"]["minimum_cluster_weighted_added_recall"], 0.1)
        self.assertFalse(cfg["claim_boundary"]["same_cohort_rescue_allowed"])


if __name__ == "__main__":
    unittest.main()
