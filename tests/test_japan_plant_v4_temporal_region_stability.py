from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

import diagnose_japan_plant_v4_temporal_region_stability as d


class JapanPlantV4TemporalRegionStabilityTests(unittest.TestCase):
    def test_frozen_consumed_cohort_is_exactly_24_unique_identities(self):
        cohort = d.load_consumed_cohort()
        self.assertEqual(len(cohort), 24)
        self.assertEqual(cohort["speciesKey"].nunique(), 24)
        self.assertTrue(set(cohort["historical_selected_region"]).issubset({r[0] for r in d.VALIDATED_JAPAN_REGIONS}))

    def test_best_region_tie_uses_frozen_registry_order(self):
        counts = {r[0]: 0 for r in d.VALIDATED_JAPAN_REGIONS}
        counts["kanto"] = 2
        counts["izu"] = 2
        classification, best, count = d.classify_region_counts(counts, "shikoku")
        self.assertEqual(classification, "other_fixed_region_recent_support")
        self.assertEqual(best, "kanto")
        self.assertEqual(count, 2)

    def test_diagnose_taxon_detects_support_outside_historical_region(self):
        recent = pd.DataFrame(
            {
                "occurrence_id": ["r1", "r2"],
                "latitude": [35.5, 35.6],
                "longitude": [139.3, 139.4],
                "event_year": [2024, 2025],
                "coordinate_uncertainty_m": [100.0, 100.0],
            }
        )
        row = pd.Series(
            {
                "speciesKey": 123,
                "scientific_name": "Synthetic plant",
                "historical_selected_region": "shikoku",
                "historical_population_count": 8,
            }
        )
        audit = SimpleNamespace(matched_usage_key=123)
        with patch.object(d, "fetch_gbif_occurrence_evidence", return_value=(recent, audit)):
            result = d.diagnose_taxon(row)
        self.assertEqual(result["recent_population_clusters_historical_region"], 0)
        self.assertGreater(result["best_recent_fixed_region_population_clusters"], 0)
        self.assertEqual(result["best_recent_fixed_region"], "kanto")
        self.assertEqual(result["region_support_class"], "other_fixed_region_recent_support")


if __name__ == "__main__":
    unittest.main()
