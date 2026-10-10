from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

import diagnose_japan_plant_v4_shifted_region_historical_support as d


class JapanPlantV4ShiftedRegionHistoricalSupportTests(unittest.TestCase):
    def test_frozen_shifted_cohort_is_exactly_10_unique_identities(self):
        cohort = d.load_cohort()
        self.assertEqual(len(cohort), 10)
        self.assertEqual(cohort["speciesKey"].nunique(), 10)

    def test_historical_support_classification_uses_frozen_threshold(self):
        self.assertEqual(
            d.classify_later_region_historical_count(5),
            "later_region_already_historically_qualified",
        )
        self.assertEqual(
            d.classify_later_region_historical_count(4),
            "later_region_historically_supported_below_threshold",
        )
        self.assertEqual(
            d.classify_later_region_historical_count(0),
            "later_region_no_historical_support",
        )


if __name__ == "__main__":
    unittest.main()
