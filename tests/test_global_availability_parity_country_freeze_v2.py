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

import freeze_global_availability_parity_countries_v2 as stage2


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class GlobalAvailabilityCountryFreezeV2Tests(unittest.TestCase):
    def _stage1_files(self, root: Path, *, n: int = 48) -> tuple[Path, Path]:
        rows = []
        for index in range(1, n + 1):
            rows.append(
                {
                    "availability_pair_id": index,
                    "status": "IDENTITY_FROZEN_PRE_HISTORICAL_COUNTRY_QUERY_V2",
                    "taxon_group": "plant" if index <= 24 else "animal",
                    "kingdomKey": 6 if index <= 24 else 1,
                    "speciesKey": 100000 + index,
                    "scientific_name": f"Taxon {index}",
                    "record_count_stratum": (index - 1) // 6 if index <= 24 else (index - 25) // 6,
                    "identity_selection_hash": f"{index:064x}",
                }
            )
        identities = root / "identities.csv"
        frame = pd.DataFrame(rows)
        frame.to_csv(identities, index=False)
        records = frame.sort_values("availability_pair_id")[[
            "availability_pair_id", "taxon_group", "record_count_stratum", "speciesKey",
            "scientific_name", "identity_selection_hash",
        ]].to_dict(orient="records")
        receipt = root / "receipt.json"
        receipt.write_text(
            json.dumps(
                {
                    "schema_version": "acsp-global-availability-parity-identity-freeze-v2-result",
                    "status": "IDENTITY_FREEZE_COMPLETE_PRE_HISTORICAL_COUNTRY_QUERY_V2",
                    "committed_identity_file": "validation/acsp_global_availability_parity_identities_v2.csv",
                    "artifact": {"identities_csv_sha256": sha256(identities)},
                    "identity_canonical_sha256": stage2._canonical_sha256(records),
                    "information_boundary": {
                        "focal_historical_country_facets_opened": False,
                        "country_geometry_opened": False,
                        "candidate_generation_run": False,
                        "heldout_2021_2025_opened": False,
                        "robust_support_run": False,
                        "random_baseline_run": False,
                        "recall_or_lift_read": False,
                        "outcome_driven_tuning": False,
                        "validated_japan_core_changed": False,
                    },
                }
            ) + "\n",
            encoding="utf-8",
        )
        return identities, receipt

    def test_receipt_hash_mismatch_stops_before_any_historical_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            identities, receipt = self._stage1_files(Path(tmp))
            data = json.loads(receipt.read_text())
            data["artifact"]["identities_csv_sha256"] = "0" * 64
            receipt.write_text(json.dumps(data) + "\n")
            with self.assertRaisesRegex(ValueError, "committed identity SHA256 mismatch"):
                stage2.verify_stage1(identities, receipt)

    def test_receipt_verifies_exact_48_and_information_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            identities_path, receipt_path = self._stage1_files(Path(tmp))
            identities, receipt = stage2.verify_stage1(identities_path, receipt_path)
            self.assertEqual(len(identities), 48)
            self.assertEqual(receipt["status"], "IDENTITY_FREEZE_COMPLETE_PRE_HISTORICAL_COUNTRY_QUERY_V2")

    def test_exactly_one_historical_query_per_frozen_taxon(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            identities_path, receipt_path = self._stage1_files(Path(tmp))
            identities, _ = stage2.verify_stage1(identities_path, receipt_path)
            calls: list[int] = []

            def provider(species_key: int, years):
                calls.append(int(species_key))
                self.assertEqual(tuple(years), tuple(stage2.HISTORICAL_YEARS))
                return {"JP": 10, "US": 100 + int(species_key) % 7}

            with patch.object(stage2, "supported_alpha2_codes", return_value={"JP", "US"}):
                plans, audit = stage2.freeze_country_plans(identities, facet_provider=provider)
            self.assertEqual(len(calls), 48)
            self.assertEqual(len(set(calls)), 48)
            self.assertEqual(calls, identities["speciesKey"].astype(int).tolist())
            self.assertEqual(len(plans), 48)
            self.assertEqual(audit["historical_facet_query_count"], 48)
            self.assertFalse(audit["heldout_2021_2025_opened"])
            self.assertFalse(audit["candidate_generation_run"])
            self.assertFalse(audit["robust_support_run"])

    def test_country_selection_is_evidence_first_and_provider_supported(self) -> None:
        identities = pd.DataFrame([
            {"availability_pair_id": 1, "taxon_group": "plant", "speciesKey": 1, "scientific_name": "A"}
        ])

        def provider(_species_key: int, _years):
            return {"HK": 9999, "LV": 6, "CN": 7207, "JP": 3445}

        with patch.object(stage2, "supported_alpha2_codes", return_value={"LV", "CN", "JP"}):
            plans, audit = stage2.freeze_country_plans(identities, facet_provider=provider)
        self.assertEqual(plans.iloc[0]["selected_country_code"], "CN")
        self.assertEqual(int(plans.iloc[0]["historical_selected_country_count"]), 7207)
        self.assertEqual(audit["ready_country_count"], 1)

    def test_technical_provider_failure_aborts_without_taxon_replacement(self) -> None:
        identities = pd.DataFrame([
            {"availability_pair_id": 1, "taxon_group": "plant", "speciesKey": 1, "scientific_name": "A"},
            {"availability_pair_id": 2, "taxon_group": "plant", "speciesKey": 2, "scientific_name": "B"},
        ])
        calls: list[int] = []

        def provider(species_key: int, _years):
            calls.append(int(species_key))
            raise RuntimeError("HTTP 429")

        with patch.object(stage2, "supported_alpha2_codes", return_value={"JP"}), patch.object(stage2.time, "sleep", return_value=None):
            with self.assertRaises(RuntimeError):
                stage2.freeze_country_plans(identities, facet_provider=provider)
        self.assertEqual(calls, [1, 1, 1, 1])
        self.assertNotIn(2, calls)

    def test_sparse_taxon_remains_nonready_and_is_not_replaced(self) -> None:
        identities = pd.DataFrame([
            {"availability_pair_id": 1, "taxon_group": "plant", "speciesKey": 1, "scientific_name": "A"},
            {"availability_pair_id": 2, "taxon_group": "plant", "speciesKey": 2, "scientific_name": "B"},
        ])

        def provider(species_key: int, _years):
            return {"JP": 4} if int(species_key) == 1 else {"JP": 20}

        with patch.object(stage2, "supported_alpha2_codes", return_value={"JP"}):
            plans, audit = stage2.freeze_country_plans(identities, facet_provider=provider)
        self.assertEqual(len(plans), 2)
        self.assertEqual(plans.iloc[0]["country_plan_state"], "INSUFFICIENT_HISTORICAL_EVIDENCE")
        self.assertEqual(plans.iloc[1]["country_plan_state"], "READY")
        self.assertEqual(audit["ready_country_count"], 1)
        self.assertFalse(audit["taxon_replacement_after_identity_freeze"])


if __name__ == "__main__":
    unittest.main()
