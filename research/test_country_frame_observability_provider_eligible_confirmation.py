from __future__ import annotations

import hashlib
import math
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd

import predeclare_country_frame_observability_provider_eligible_confirmation as mod


class _Geom:
    country_code = "JP"
    source_id = "geoBoundaries-gbOpen-ADM0-simplified"
    source_version = "v6.0.0@test;canonical_geojson_sha256=" + ("a" * 64) + ";license=CC BY 4.0"


class ProviderEligibleObservabilityConfirmationTests(unittest.TestCase):
    def test_protocol_coverage_seed_and_preheldout_boundary_are_frozen(self) -> None:
        cfg = mod.protocol()
        self.assertEqual(
            cfg["protocol_fingerprint"],
            "91b8143f38abb173c3cdabc198bfcc5f113632f33b3c674b99374aac1efdd644",
        )
        self.assertEqual(
            cfg["provider_eligibility"]["coverage_contract_fingerprint"],
            "377f6374e077cc38ea7fc026de6dc289abc2716aca8c83d66ddcd42826139520",
        )
        self.assertEqual(cfg["cohort"]["identity_seed_derivation"]["selection_seed"], 664395665)
        self.assertEqual(cfg["cohort"]["target_frames"], 96)
        self.assertEqual(cfg["cohort"]["discovery_years"], [1900, 2020])
        self.assertFalse(cfg["scientific_position"]["continuation_rescue_or_rerun_of_163"])
        self.assertFalse(cfg["freshness"]["exclude_163_partial_abort_identities"])
        self.assertFalse(cfg["execution"]["freeze_activation_opens_heldout"])
        self.assertFalse(cfg["provider_eligibility"]["alternate_geometry_provider_allowed"])
        self.assertFalse(cfg["provider_eligibility"]["country_substitution_allowed"])
        self.assertEqual(mod.alpha2_to_alpha3_if_supported("JP"), "JPN")
        self.assertIsNone(mod.alpha2_to_alpha3_if_supported("HK"))

    def test_identity_seed_is_derived_only_from_frozen_protocol_token(self) -> None:
        cfg = mod.protocol()["cohort"]["identity_seed_derivation"]
        digest = hashlib.sha256(cfg["token"].encode("utf-8")).hexdigest()
        self.assertEqual(digest, cfg["sha256"])
        self.assertEqual(int(digest[:16], 16) % 2147483647, cfg["selection_seed"])

    @patch.object(mod, "get_json")
    @patch.object(mod, "_species_metadata")
    def test_discovery_species_facet_is_historical_only(self, metadata, get_json) -> None:
        get_json.return_value = {
            "facets": [{"counts": [{"name": "101", "count": 25}]}]
        }
        metadata.return_value = {"rank": "SPECIES", "scientificName": "Synthetic taxon"}
        frame = mod.historical_taxon_frame((140.0, 35.0, 141.0, 36.0), 6, 400, 20)
        self.assertEqual(len(frame), 1)
        params = get_json.call_args.args[1]
        self.assertEqual(params["year"], "1900,2020")
        self.assertEqual(params["facet"], "speciesKey")
        self.assertNotIn("2021", str(params))
        self.assertNotIn("2025", str(params))

    def _synthetic_providers(self):
        facet_counts: dict[int, dict[str, int]] = {}
        calls = {"n": 0}
        seed = int(mod.protocol()["cohort"]["identity_seed_derivation"]["selection_seed"])

        def frame_provider(bounds, kingdom_key, facet_limit, minimum_records):
            del bounds, facet_limit, minimum_records
            call_index = calls["n"]
            calls["n"] += 1
            region = call_index // 2 + 1
            group = "plant" if int(kingdom_key) == int(mod.TAXON_GROUPS["plant"]) else "animal"
            group_offset = 0 if group == "plant" else 50000
            rows = []
            for i in range(8):
                key = region * 100000 + group_offset + i + 1
                rows.append({
                    "speciesKey": key,
                    "scientific_name": f"Synthetic {region} {group} {i + 1}",
                    "coordinate_records": (i + 1) * 10,
                })
            frame = pd.DataFrame(rows)
            frame["record_count_stratum"] = pd.qcut(
                frame["coordinate_records"].rank(method="first"), 4, labels=False
            ).astype(int)
            for stratum in range(4):
                keys = frame.loc[frame["record_count_stratum"].eq(stratum), "speciesKey"].astype(int).tolist()
                ordered = sorted(
                    keys,
                    key=lambda key: (mod.identity_hash(seed, region, group, stratum, key), key),
                )
                if region == 1 and group == "plant" and stratum == 0:
                    facet_counts[ordered[0]] = {"HK": 9}
                    facet_counts[ordered[1]] = {"JP": 17}
                elif region == 1 and group == "plant" and stratum == 1:
                    facet_counts[ordered[0]] = {}
                    facet_counts[ordered[1]] = {"JP": 5}
                else:
                    facet_counts[ordered[0]] = {"JP": 20}
                    facet_counts[ordered[1]] = {"JP": 5000}
            return frame.drop(columns="record_count_stratum")

        def facet_provider(species_key, years):
            self.assertEqual(tuple(years), (1900, 2020))
            return facet_counts[int(species_key)]

        def geometry_provider(country):
            self.assertEqual(country, "JP")
            return _Geom()

        return frame_provider, facet_provider, geometry_provider

    def test_complete_96_passes_unsupported_and_no_country_before_freeze_without_country_substitution(self) -> None:
        frame_provider, facet_provider, geometry_provider = self._synthetic_providers()
        selected, audit = mod.select_frames(
            frame_provider=frame_provider,
            facet_provider=facet_provider,
            geometry_provider=geometry_provider,
            excluded_keys=set(),
            excluded_names=set(),
            explicit_prefixes=(),
        )
        self.assertEqual(len(selected), 96)
        self.assertEqual(selected["speciesKey"].nunique(), 96)
        self.assertEqual(selected["taxon_group"].value_counts().to_dict(), {"plant": 48, "animal": 48})
        self.assertEqual(len(audit), 98)
        self.assertEqual(int(audit["attempt_status"].eq("provider_ineligible_before_freeze").sum()), 1)
        self.assertEqual(int(audit["attempt_status"].eq("no_eligible_historical_country").sum()), 1)
        unsupported = audit[audit["attempt_status"].eq("provider_ineligible_before_freeze")].iloc[0]
        self.assertEqual(unsupported["selected_country_code"], "HK")
        self.assertEqual(unsupported["historical_selected_country_count"], 9)
        self.assertFalse(bool(unsupported["selected"]))
        first_cell = selected[
            selected["region_cell_index"].eq(1)
            & selected["taxon_group"].eq("plant")
            & selected["record_count_stratum"].eq(0)
        ].iloc[0]
        self.assertEqual(first_cell["selected_country_code"], "JP")
        self.assertEqual(first_cell["selected_country_alpha3"], "JPN")
        self.assertEqual(int(first_cell["declaration_attempt_rank"]), 2)
        self.assertTrue(math.isclose(
            float(first_cell["country_frame_observability_score"]),
            math.log1p(int(first_cell["historical_selected_country_count"])),
            rel_tol=0.0,
            abs_tol=1e-12,
        ))

    def test_historical_provider_error_aborts_instead_of_selecting_next_identity(self) -> None:
        frame_provider, _, geometry_provider = self._synthetic_providers()

        def fail(species_key, years):
            del species_key, years
            raise RuntimeError("synthetic historical provider failure")

        with self.assertRaises(mod.FreezeAborted) as caught:
            mod.select_frames(
                frame_provider=frame_provider,
                facet_provider=fail,
                geometry_provider=geometry_provider,
                excluded_keys=set(),
                excluded_names=set(),
                explicit_prefixes=(),
            )
        self.assertEqual(len(caught.exception.audit_rows), 1)
        self.assertEqual(caught.exception.audit_rows[0]["attempt_status"], "historical_provider_error_abort")

    def test_supported_geometry_error_aborts_and_never_falls_back(self) -> None:
        frame_provider, facet_provider, _ = self._synthetic_providers()

        def fail_geometry(country):
            raise RuntimeError(f"synthetic geometry failure {country}")

        with self.assertRaises(mod.FreezeAborted) as caught:
            mod.select_frames(
                frame_provider=frame_provider,
                facet_provider=facet_provider,
                geometry_provider=fail_geometry,
                excluded_keys=set(),
                excluded_names=set(),
                explicit_prefixes=(),
            )
        self.assertEqual(caught.exception.audit_rows[-1]["attempt_status"], "supported_geometry_provider_error_abort")
        self.assertEqual(caught.exception.audit_rows[-1]["selected_country_code"], "JP")

    def test_new_confirmation_does_not_special_case_163_partial_identities(self) -> None:
        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("9775639", source)
        self.assertNotIn("5729409", source)
        self.assertNotIn("RECENT_YEARS", source)
        self.assertNotIn("recent_heldout_occurrence_rows", source)


if __name__ == "__main__":
    unittest.main()
