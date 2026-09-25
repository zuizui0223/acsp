#!/usr/bin/env python3
import unittest
from pathlib import Path

import pandas as pd

import sys
ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

import freeze_japan_plant_broad_frame_identity_candidates_v3 as f


class IdentityCandidateFreezeV3Tests(unittest.TestCase):
    def _frame_provider(self, bounds, kingdom_key, facet_limit, minimum_records):
        self.assertEqual(int(kingdom_key), 6)
        return pd.DataFrame({
            "speciesKey": list(range(9000000, 9000150)),
            "coordinate_records": list(range(20, 170)),
        })

    @staticmethod
    def _metadata_provider(key):
        return {"rank": "SPECIES", "scientificName": f"Freshplantus species{int(key)}"}

    @staticmethod
    def _exclusion_provider(path):
        return {9000149}, {"Freshplantus never"}, {"synthetic": True}

    def test_freeze_is_deterministic_and_upper_supply_only(self):
        a, audit_a = f.freeze_identity_candidates(
            Path("unused.csv"),
            frame_provider=self._frame_provider,
            metadata_provider=self._metadata_provider,
            exclusion_provider=self._exclusion_provider,
        )
        b, audit_b = f.freeze_identity_candidates(
            Path("unused.csv"),
            frame_provider=self._frame_provider,
            metadata_provider=self._metadata_provider,
            exclusion_provider=self._exclusion_provider,
        )
        self.assertEqual(len(a), 48)
        self.assertEqual(a["speciesKey"].nunique(), 48)
        self.assertEqual(a["scientific_name"].nunique(), 48)
        self.assertNotIn(9000149, set(a["speciesKey"]))
        self.assertGreaterEqual(int(a["registry_max_coordinate_records"].min()), 94)
        pd.testing.assert_frame_equal(a, b)
        self.assertEqual(audit_a["candidate_identity_sha256"], audit_b["candidate_identity_sha256"])

    def test_stage1_audit_is_pre_historical_and_pre_heldout(self):
        _, audit = f.freeze_identity_candidates(
            Path("unused.csv"),
            frame_provider=self._frame_provider,
            metadata_provider=self._metadata_provider,
            exclusion_provider=self._exclusion_provider,
        )
        self.assertEqual(audit["status"], "IDENTITY_CANDIDATES_FROZEN_PRE_FOCAL_HISTORICAL_QUERY")
        self.assertFalse(audit["focal_2000_2020_occurrences_opened"])
        self.assertFalse(audit["heldout_2021_2025_opened"])
        self.assertFalse(audit["candidate_frames_built"])
        self.assertFalse(audit["selector_evaluated"])
        self.assertFalse(audit["validated_japan_product_changed"])
        self.assertFalse(audit["automatic_global_adapter_changed"])


if __name__ == "__main__":
    unittest.main()
