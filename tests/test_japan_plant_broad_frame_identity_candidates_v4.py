#!/usr/bin/env python3
import unittest
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

import freeze_japan_plant_broad_frame_identity_candidates_v4 as f


class IdentityCandidateFreezeV4Tests(unittest.TestCase):
    def _frame_provider(self, bounds, kingdom_key, facet_limit, minimum_records):
        self.assertEqual(int(kingdom_key), 6)
        return pd.DataFrame({
            "speciesKey": list(range(9000000, 9000300)),
            "coordinate_records": list(range(20, 320)),
        })

    @staticmethod
    def _metadata_provider(key):
        return {"rank": "SPECIES", "scientificName": f"Freshplantus species{int(key)}"}

    @staticmethod
    def _exclusion_provider(path):
        return {9000299}, {"Freshplantus never"}, {"synthetic": True}

    @staticmethod
    def _global_exclusion_provider():
        return {9000298}, {"Freshplantus species9000298"}

    @staticmethod
    def _issue_202_exclusion_provider():
        return {9000297}, {"Freshplantus species9000297"}, {"synthetic_issue_202": True, "count": 1}

    def test_freeze_is_deterministic_96_and_excludes_consumed(self):
        kwargs = dict(
            frame_provider=self._frame_provider,
            metadata_provider=self._metadata_provider,
            exclusion_provider=self._exclusion_provider,
            global_exclusion_provider=self._global_exclusion_provider,
            issue_202_exclusion_provider=self._issue_202_exclusion_provider,
        )
        a, audit_a = f.freeze_identity_candidates(Path("unused.csv"), **kwargs)
        b, audit_b = f.freeze_identity_candidates(Path("unused.csv"), **kwargs)
        self.assertEqual(len(a), 96)
        self.assertEqual(a["speciesKey"].nunique(), 96)
        self.assertEqual(a["scientific_name"].nunique(), 96)
        self.assertTrue({9000297, 9000298, 9000299}.isdisjoint(set(a["speciesKey"])))
        pd.testing.assert_frame_equal(a, b)
        self.assertEqual(audit_a["candidate_identity_sha256"], audit_b["candidate_identity_sha256"])
        self.assertEqual(audit_a["candidate_count"], 96)

    def test_stage1_audit_is_pre_historical_and_pre_heldout(self):
        _, audit = f.freeze_identity_candidates(
            Path("unused.csv"),
            frame_provider=self._frame_provider,
            metadata_provider=self._metadata_provider,
            exclusion_provider=self._exclusion_provider,
            global_exclusion_provider=self._global_exclusion_provider,
            issue_202_exclusion_provider=self._issue_202_exclusion_provider,
        )
        self.assertEqual(audit["status"], "IDENTITY_CANDIDATES_FROZEN_PRE_FOCAL_HISTORICAL_QUERY")
        self.assertFalse(audit["focal_2000_2020_occurrences_opened"])
        self.assertFalse(audit["heldout_2021_2025_opened"])
        self.assertFalse(audit["candidate_frames_built"])
        self.assertFalse(audit["selector_evaluated"])
        self.assertFalse(audit["validated_japan_product_changed"])
        self.assertFalse(audit["automatic_global_adapter_changed"])

    def test_issue_202_exclusion_file_is_exactly_frozen_48(self):
        keys, names, audit = f._read_issue_202_exclusions()
        self.assertEqual(len(keys), 48)
        self.assertEqual(len(names), 48)
        self.assertEqual(audit["count"], 48)
        self.assertEqual(
            audit["sha256"],
            "6cde4966374c049c3ed55c4a1aa836a668fd52795ea60f8572a9aa8ac4963b1d",
        )


if __name__ == "__main__":
    unittest.main()
