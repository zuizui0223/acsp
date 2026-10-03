from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

import freeze_global_availability_parity_identities_v1 as freeze


class GlobalAvailabilityIdentityFreezeTests(unittest.TestCase):
    def test_stage1_freezes_balanced_48_without_historical_country_or_heldout_inputs(self) -> None:
        regions = tuple(
            ("g", f"R{i}", float(i), 30.0, float(i) + 0.5, 30.5)
            for i in range(1, 13)
        )
        taxon_groups = {"plant": 6, "animal": 1}

        def provider(bounds, kingdom_key, _limit, _minimum):
            region = int(round(bounds[0]))
            group_offset = 100000 if int(kingdom_key) == 1 else 0
            rows = []
            for index in range(24):
                rows.append(
                    {
                        "speciesKey": region * 1000 + group_offset + index,
                        "scientific_name": f"Taxon {region} {kingdom_key} {index}",
                        "coordinate_records": 20 + index,
                    }
                )
            return pd.DataFrame(rows)

        with patch.object(freeze, "REGION_CELLS", regions), \
             patch.object(freeze, "TAXON_GROUPS", taxon_groups), \
             patch.object(freeze, "combined_exclusions", return_value=(set(), set(), {"combined_excluded_species_keys": 0})):
            identities, audit = freeze.freeze_identities(Path("unused.csv"), frame_provider=provider)

        self.assertEqual(len(identities), 48)
        self.assertEqual(identities["speciesKey"].nunique(), 48)
        self.assertEqual(identities["taxon_group"].value_counts().to_dict(), {"plant": 24, "animal": 24})
        self.assertFalse(audit["focal_historical_country_facets_opened"])
        self.assertFalse(audit["country_geometry_opened"])
        self.assertFalse(audit["candidate_generation_run"])
        self.assertFalse(audit["heldout_2021_2025_opened"])
        self.assertFalse(audit["robust_support_run"])
        self.assertFalse(audit["recall_or_lift_read"])

    def test_stage1_does_not_silently_replace_an_empty_target_stratum(self) -> None:
        regions = tuple(("g", f"R{i}", float(i), 30.0, float(i) + 0.5, 30.5) for i in range(1, 13))
        taxon_groups = {"plant": 6, "animal": 1}

        def provider(bounds, kingdom_key, _limit, _minimum):
            region = int(round(bounds[0]))
            group_offset = 100000 if int(kingdom_key) == 1 else 0
            rows = [
                {
                    "speciesKey": region * 1000 + group_offset + index,
                    "scientific_name": f"Taxon {region} {kingdom_key} {index}",
                    "coordinate_records": 20 + index,
                }
                for index in range(8)
            ]
            return pd.DataFrame(rows)

        # Remove all plant taxa from one target stratum after qcut by excluding
        # the full frame for R1/plant. The freeze must abort rather than borrow
        # another stratum or region.
        def exclusions(_path):
            keys = {1000 + index for index in range(8)}
            names = {f"Taxon 1 6 {index}" for index in range(8)}
            return keys, names, {"combined_excluded_species_keys": len(keys)}

        with patch.object(freeze, "REGION_CELLS", regions), \
             patch.object(freeze, "TAXON_GROUPS", taxon_groups), \
             patch.object(freeze, "combined_exclusions", side_effect=exclusions):
            with self.assertRaises(RuntimeError):
                freeze.freeze_identities(Path("unused.csv"), frame_provider=provider)


if __name__ == "__main__":
    unittest.main()
