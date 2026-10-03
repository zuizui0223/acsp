from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

import freeze_global_availability_parity_countries_v1 as stage2


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class GlobalAvailabilityCountryFreezeTests(unittest.TestCase):
    def _stage1_files(self, root: Path, *, n: int = 48) -> tuple[Path, Path]:
        rows = []
        for index in range(1, n + 1):
            rows.append(
                {
                    "availability_pair_id": index,
                    "taxon_group": "plant" if index <= 24 else "animal",
                    "speciesKey": 100000 + index,
                    "scientific_name": f"Taxon {index}",
                }
            )
        identities = root / "identities.csv"
        pd.DataFrame(rows).to_csv(identities, index=False)
        audit = root / "audit.json"
        audit.write_text(
            json.dumps(
                {
                    "status": "IDENTITY_FREEZE_COMPLETE_PRE_HISTORICAL_COUNTRY_QUERY",
                    "focal_historical_country_facets_opened": False,
                    "heldout_2021_2025_opened": False,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return identities, audit

    def test_hash_mismatch_stops_before_any_historical_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identities, audit = self._stage1_files(root)
            with self.assertRaises(ValueError):
                stage2.verify_stage1(
                    identities,
                    audit,
                    expected_identity_sha256="0" * 64,
                    expected_audit_sha256=sha256(audit),
                )

    def test_exactly_one_historical_query_per_frozen_taxon(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            identities_path, audit_path = self._stage1_files(Path(tmp))
            identities, _ = stage2.verify_stage1(
                identities_path,
                audit_path,
                expected_identity_sha256=sha256(identities_path),
                expected_audit_sha256=sha256(audit_path),
            )
            calls: list[int] = []

            def provider(species_key: int, years):
                calls.append(int(species_key))
                self.assertEqual(tuple(years), tuple(stage2.HISTORICAL_YEARS))
                return {"JP": 10, "US": 100 + int(species_key) % 7}

            with patch.object(stage2, "supported_alpha2_codes", return_value={"JP", "US"}):
                plans, result_audit = stage2.freeze_country_plans(identities, facet_provider=provider)

            self.assertEqual(len(calls), 48)
            self.assertEqual(len(set(calls)), 48)
            self.assertEqual(calls, identities["speciesKey"].astype(int).tolist())
            self.assertEqual(len(plans), 48)
            self.assertEqual(result_audit["historical_facet_query_count"], 48)
            self.assertFalse(result_audit["heldout_2021_2025_opened"])
            self.assertFalse(result_audit["candidate_generation_run"])
            self.assertFalse(result_audit["robust_support_run"])
            self.assertFalse(result_audit["recall_or_lift_read"])

    def test_country_selection_is_evidence_first_and_provider_supported(self) -> None:
        identities = pd.DataFrame(
            [
                {
                    "availability_pair_id": 1,
                    "taxon_group": "plant",
                    "speciesKey": 1,
                    "scientific_name": "Taxon A",
                }
            ]
        )

        def provider(_species_key: int, _years):
            return {"HK": 9999, "LV": 6, "CN": 7207, "JP": 3445}

        with patch.object(stage2, "supported_alpha2_codes", return_value={"LV", "CN", "JP"}):
            plans, result_audit = stage2.freeze_country_plans(identities, facet_provider=provider)
        self.assertEqual(plans.iloc[0]["selected_country_code"], "CN")
        self.assertEqual(int(plans.iloc[0]["historical_selected_country_count"]), 7207)
        self.assertEqual(result_audit["ready_country_count"], 1)
        self.assertTrue(result_audit["country_selection_uses_historical_evidence_only"])

    def test_technical_provider_failure_aborts_without_taxon_replacement(self) -> None:
        identities = pd.DataFrame(
            [
                {"availability_pair_id": 1, "taxon_group": "plant", "speciesKey": 1, "scientific_name": "A"},
                {"availability_pair_id": 2, "taxon_group": "plant", "speciesKey": 2, "scientific_name": "B"},
            ]
        )
        calls: list[int] = []

        def provider(species_key: int, _years):
            calls.append(int(species_key))
            raise RuntimeError("HTTP 429")

        with patch.object(stage2, "supported_alpha2_codes", return_value={"JP"}), \
             patch.object(stage2.time, "sleep", return_value=None):
            with self.assertRaises(RuntimeError):
                stage2.freeze_country_plans(identities, facet_provider=provider)
        self.assertEqual(calls, [1, 1, 1, 1])
        self.assertNotIn(2, calls)

    def test_sparse_taxon_is_kept_as_nonready_not_replaced(self) -> None:
        identities = pd.DataFrame(
            [
                {"availability_pair_id": 1, "taxon_group": "plant", "speciesKey": 1, "scientific_name": "A"},
                {"availability_pair_id": 2, "taxon_group": "plant", "speciesKey": 2, "scientific_name": "B"},
            ]
        )

        def provider(species_key: int, _years):
            return {"JP": 4} if int(species_key) == 1 else {"JP": 20}

        with patch.object(stage2, "supported_alpha2_codes", return_value={"JP"}):
            plans, result_audit = stage2.freeze_country_plans(identities, facet_provider=provider)
        self.assertEqual(len(plans), 2)
        self.assertEqual(plans.iloc[0]["country_plan_state"], "INSUFFICIENT_HISTORICAL_EVIDENCE")
        self.assertEqual(plans.iloc[1]["country_plan_state"], "READY")
        self.assertEqual(result_audit["ready_country_count"], 1)
        self.assertFalse(result_audit["taxon_replacement_after_identity_freeze"])


if __name__ == "__main__":
    unittest.main()
