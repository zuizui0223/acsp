#!/usr/bin/env python3
import unittest
from pathlib import Path

import sys
ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

import prepare_japan_plant_broad_frame_preflight_v3 as f


class JapanPlantBroadFramePreflightV3Tests(unittest.TestCase):
    def test_final_qualifier_selection_is_deterministic(self):
        rows = [
            {"candidate_id": i, "speciesKey": 7000000 + i, "scientific_name": f"Plantus {i}", "selected_region": "kanto", "historical_population_count": 5 + i}
            for i in range(1, 31)
        ]
        a = f.select_final_qualifiers(rows, final_count=24, seed=2026091102)
        b = f.select_final_qualifiers(list(reversed(rows)), final_count=24, seed=2026091102)
        self.assertEqual([x["speciesKey"] for x in a], [x["speciesKey"] for x in b])
        self.assertEqual(len(a), 24)
        self.assertEqual(len({x["speciesKey"] for x in a}), 24)

    def test_insufficient_qualifiers_fail_closed(self):
        rows = [{"speciesKey": 1, "scientific_name": "Plantus one"}] * 23
        self.assertEqual(f.select_final_qualifiers(rows, final_count=24, seed=1), [])

    def test_protocol_forbids_heldout_selection(self):
        cfg = f._protocol()
        self.assertFalse(cfg["stage2_historical_qualification"]["selection_uses_2021_2025"])
        self.assertTrue(cfg["outcome"]["open_only_after_24_taxa_and_candidate_hashes_frozen"])
        self.assertFalse(cfg["claim_boundary"]["same_cohort_rescue_allowed"])


if __name__ == "__main__":
    unittest.main()
