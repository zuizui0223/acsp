from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "research"
if str(RESEARCH) not in sys.path:
    sys.path.insert(0, str(RESEARCH))

import freeze_global_availability_parity_identities_v2 as mod


class GlobalAvailabilityIdentityFreezeV2Tests(unittest.TestCase):
    @staticmethod
    def fake_frame(bounds, kingdom_key, facet_limit, minimum_records):
        group_offset = 0 if int(kingdom_key) == 6 else 100000
        region_index = next(
            i
            for i, cell in enumerate(mod.REGION_CELLS, start=1)
            if tuple(map(float, cell[2:6])) == tuple(map(float, bounds))
        )
        rows = []
        for i in range(40):
            rows.append({
                "speciesKey": group_offset + i + 1,
                "scientific_name": f"Taxon {group_offset + i + 1}",
                "coordinate_records": 20 + i + region_index,
            })
        return pd.DataFrame(rows)

    def test_registry_pools_regions_and_uses_max_record_count(self):
        registry, audit = mod.build_identity_registry(frame_provider=self.fake_frame)
        self.assertEqual(len(audit), 24)
        self.assertEqual(len(registry), 80)
        plant1 = registry[(registry["taxon_group"] == "plant") & (registry["speciesKey"] == 1)].iloc[0]
        self.assertEqual(int(plant1.registry_source_region_count), 12)
        self.assertEqual(int(plant1.registry_max_coordinate_records), 33)

    def test_freeze_selects_six_per_group_per_stratum_without_outcome_inputs(self):
        with patch.object(mod, "combined_exclusions", return_value=(set(), set(), {"mock": True})):
            identities, audit = mod.freeze_identities(Path("unused.csv"), frame_provider=self.fake_frame)
        self.assertEqual(len(identities), 48)
        self.assertEqual(identities["taxon_group"].value_counts().to_dict(), {"animal": 24, "plant": 24})
        for group in ("plant", "animal"):
            counts = identities.loc[identities["taxon_group"].eq(group), "record_count_stratum"].value_counts().sort_index().to_dict()
            self.assertEqual(counts, {0: 6, 1: 6, 2: 6, 3: 6})
        self.assertFalse(audit["focal_historical_country_facets_opened"])
        self.assertFalse(audit["candidate_generation_run"])
        self.assertFalse(audit["heldout_2021_2025_opened"])
        self.assertFalse(audit["recall_or_lift_read"])

    def test_freeze_fails_before_selection_if_exclusions_leave_too_few(self):
        excluded_plant = set(range(1, 22))
        with patch.object(mod, "combined_exclusions", return_value=(excluded_plant, set(), {"mock": True})):
            with self.assertRaisesRegex(RuntimeError, "fewer than 24 unconsumed pooled identities remain for group=plant"):
                mod.freeze_identities(Path("unused.csv"), frame_provider=self.fake_frame)


if __name__ == "__main__":
    unittest.main()
