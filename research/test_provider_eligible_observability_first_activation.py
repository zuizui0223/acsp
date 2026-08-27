from __future__ import annotations

import math
from pathlib import Path
import unittest

import pandas as pd

import provider_eligible_observability_first_activation as mod


class _Geom:
    def __init__(self, country: str) -> None:
        self.country_code = country
        self.source_id = "geoBoundaries-gbOpen-ADM0-simplified"
        self.source_version = (
            "v6.0.0@1289e40e366c7b320550be1ee0614a9472d572d4;"
            f"iso3=JPN;canonical_geojson_sha256={'a' * 64};license=CC BY 4.0"
        )


class ProviderEligibleFirstActivationTests(unittest.TestCase):
    def test_static_bindings_are_exact_before_runner_use(self) -> None:
        observed = mod.validate_static_preregistration()
        self.assertEqual(
            observed,
            {
                "protocol_fingerprint": mod.EXPECTED_PROTOCOL_FINGERPRINT,
                "execution_contract_fingerprint": mod.EXPECTED_EXECUTION_FINGERPRINT,
                "coverage_contract_fingerprint": mod.EXPECTED_COVERAGE_FINGERPRINT,
                "exclusion_provenance_fingerprint": mod.EXPECTED_EXCLUSION_FINGERPRINT,
            },
        )
        self.assertEqual(
            mod.PREREGISTRATION_MERGE_COMMIT,
            "91ff432e3da7cf3b26efa16a5c60219715feff89",
        )

    def test_historical_discovery_species_facet_is_bounded_to_1900_2020(self) -> None:
        captured = {}

        def search_fetcher(params):
            captured.update(params)
            return {
                "facets": [
                    {
                        "field": "SPECIES_KEY",
                        "counts": [
                            {"name": "1", "count": 20},
                            {"name": "2", "count": 30},
                            {"name": "3", "count": 40},
                            {"name": "4", "count": 50},
                        ],
                    }
                ]
            }

        def metadata_provider(key):
            return {"rank": "SPECIES", "scientificName": f"Synthetic species {key}"}

        frame = mod.historical_taxon_frame(
            (130.0, 30.0, 131.0, 31.0),
            6,
            400,
            20,
            search_fetcher=search_fetcher,
            metadata_provider=metadata_provider,
            metadata_workers=1,
        )
        self.assertEqual(captured["year"], "1900,2020")
        self.assertEqual(captured["facet"], "speciesKey")
        self.assertEqual(len(frame), 4)
        self.assertNotIn("2021", str(captured))
        self.assertNotIn("2025", str(captured))

    def _synthetic_frame_provider(self):
        calls = {"n": 0}

        def provider(bounds, kingdom_key, facet_limit, minimum_records):
            del bounds, kingdom_key, facet_limit, minimum_records
            calls["n"] += 1
            base = calls["n"] * 10000
            return pd.DataFrame(
                {
                    "speciesKey": [base + i for i in range(1, 9)],
                    "scientific_name": [f"Synthetic {base + i}" for i in range(1, 9)],
                    "coordinate_records": [20, 21, 30, 31, 40, 41, 50, 51],
                }
            )

        return provider

    def test_stage1_freezes_complete_balanced_candidate_snapshot_without_live_facets(self) -> None:
        snapshot, audit = mod.build_candidate_snapshot(
            frame_provider=self._synthetic_frame_provider(),
            excluded_keys=set(),
            excluded_names=set(),
        )
        self.assertEqual(len(audit), 24)
        self.assertEqual(len(snapshot), 24 * 8)
        self.assertEqual(set(snapshot["record_count_stratum"].astype(int)), {0, 1, 2, 3})
        self.assertTrue(snapshot["discovery_year_start"].eq(1900).all())
        self.assertTrue(snapshot["discovery_year_end"].eq(2020).all())
        per_cell = snapshot.groupby(
            ["region_cell_index", "taxon_group", "record_count_stratum"]
        ).size()
        self.assertEqual(len(per_cell), 96)
        self.assertTrue((per_cell == 2).all())

    def test_stage2_queries_historical_window_and_does_not_substitute_supported_country(self) -> None:
        cfg = mod.protocol()
        key = 900001
        candidate = pd.DataFrame(
            [
                {
                    "candidate_id": 1,
                    "region_cell_index": 1,
                    "taxon_group": "plant",
                    "record_count_stratum": 0,
                    "speciesKey": key,
                    "scientific_name": "Synthetic unsupported HK",
                    "identity_selection_hash": mod.identity_hash(
                        int(cfg["cohort"]["selection_seed"]), 1, "plant", 0, key
                    ),
                }
            ]
        )
        observed_years = []

        def facet_provider(species_key, years):
            self.assertEqual(species_key, key)
            observed_years.append(tuple(years))
            return {"HK": 25, "JP": 999}

        result, audit = mod.build_historical_eligibility_snapshot(
            candidate, facet_provider=facet_provider, workers=1
        )
        self.assertEqual(observed_years, [(1900, 2020)])
        row = result.iloc[0]
        self.assertEqual(row["selected_country_code"], "HK")
        self.assertFalse(bool(row["provider_eligible"]))
        self.assertEqual(
            row["eligibility_status"],
            "preselection_ineligible_provider_coverage",
        )
        self.assertEqual(int(row["historical_selected_country_count"]), 25)
        self.assertTrue(
            math.isclose(
                float(row["country_frame_observability_score"]),
                math.log1p(25),
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        )
        self.assertEqual(audit.iloc[0]["status"], "historical_country_facets_complete")

    def _full_eligibility_snapshot(self, candidates_per_cell=2):
        cfg = mod.protocol()
        seed = int(cfg["cohort"]["selection_seed"])
        rows = []
        candidate_id = 0
        for region in range(1, 13):
            for group_index, group in enumerate(("plant", "animal")):
                for stratum in range(4):
                    for rank in range(candidates_per_cell):
                        candidate_id += 1
                        key = (
                            region * 1_000_000
                            + group_index * 100_000
                            + stratum * 1_000
                            + rank
                            + 1
                        )
                        rows.append(
                            {
                                "candidate_id": candidate_id,
                                "region_cell_index": region,
                                "taxon_group": group,
                                "record_count_stratum": stratum,
                                "speciesKey": key,
                                "scientific_name": f"Synthetic final {key}",
                                "identity_selection_hash": mod.identity_hash(
                                    seed, region, group, stratum, key
                                ),
                                "provider_eligible": True,
                                "eligibility_status": "provider_eligible_before_final_selection",
                                "selected_country_code": "JP",
                                "selected_country_alpha3": "JPN",
                                "historical_selected_country_count": 5 if rank == 0 else 5000,
                                "country_frame_observability_score": math.log1p(
                                    5 if rank == 0 else 5000
                                ),
                            }
                        )
        return pd.DataFrame(rows)

    def test_stage3_selection_is_hash_only_not_score_magnitude(self) -> None:
        snapshot = self._full_eligibility_snapshot()
        selected, audit = mod.select_final_96_offline(snapshot)
        self.assertEqual(len(selected), 96)
        self.assertEqual(selected["speciesKey"].nunique(), 96)
        for keys, cell in snapshot.groupby(
            ["region_cell_index", "taxon_group", "record_count_stratum"]
        ):
            region, group, stratum = keys
            expected = min(
                cell.to_dict(orient="records"),
                key=lambda row: (
                    row["identity_selection_hash"],
                    int(row["speciesKey"]),
                    row["scientific_name"],
                ),
            )
            actual = selected[
                selected["region_cell_index"].astype(int).eq(int(region))
                & selected["taxon_group"].eq(group)
                & selected["record_count_stratum"].astype(int).eq(int(stratum))
            ].iloc[0]
            self.assertEqual(int(actual["speciesKey"]), int(expected["speciesKey"]))
        self.assertEqual(
            int(
                audit["selection_status"]
                .eq("selected_identity_hash_min_eligible_unused")
                .sum()
            ),
            96,
        )

    def test_stage3_aborts_when_required_stratum_has_no_provider_eligible_candidate(self) -> None:
        snapshot = self._full_eligibility_snapshot()
        mask = (
            snapshot["region_cell_index"].eq(3)
            & snapshot["taxon_group"].eq("animal")
            & snapshot["record_count_stratum"].eq(2)
        )
        snapshot.loc[mask, "provider_eligible"] = False
        snapshot.loc[mask, "eligibility_status"] = (
            "preselection_ineligible_provider_coverage"
        )
        with self.assertRaises(mod.FirstActivationAborted) as caught:
            mod.select_final_96_offline(snapshot)
        self.assertEqual(caught.exception.stage, 3)
        self.assertIn("no provider-eligible candidate", str(caught.exception))

    def test_stage4_freezes_exact_pinned_geometry_without_substitution(self) -> None:
        selected, _ = mod.select_final_96_offline(self._full_eligibility_snapshot())
        final, audit = mod.freeze_pinned_geometry(
            selected,
            geometry_provider=lambda country: _Geom(country),
        )
        self.assertEqual(len(final), 96)
        self.assertTrue(
            final["geometry_source_id"]
            .eq("geoBoundaries-gbOpen-ADM0-simplified")
            .all()
        )
        self.assertTrue(final["geometry_canonical_sha256"].eq("a" * 64).all())
        self.assertTrue(audit["status"].eq("pinned_geometry_frozen").all())

    def test_stage4_aborts_on_geometry_error_and_never_reselects(self) -> None:
        selected, _ = mod.select_final_96_offline(self._full_eligibility_snapshot())
        calls = {"n": 0}

        def provider(country):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("synthetic pinned geometry failure")
            return _Geom(country)

        with self.assertRaises(mod.FirstActivationAborted) as caught:
            mod.freeze_pinned_geometry(selected, geometry_provider=provider)
        self.assertEqual(caught.exception.stage, 4)
        self.assertEqual(len(caught.exception.partial_frame), 1)

    def test_workflow_is_dormant_marker_only_and_forbids_rerun_attempt(self) -> None:
        path = (
            mod.ROOT
            / ".github"
            / "workflows"
            / "provider-eligible-observability-first-activation.yml"
        )
        text = path.read_text(encoding="utf-8")
        self.assertIn(
            "validation/activate_provider_eligible_observability_confirmation_first.marker",
            text,
        )
        self.assertNotIn("pull_request:", text)
        self.assertNotIn("schedule:", text)
        self.assertNotIn("workflow_dispatch:", text)
        self.assertIn("RUN_ATTEMPT", text)
        self.assertIn("== 1", text)
        self.assertFalse(mod.FIRST_ACTIVATION_MARKER.is_file())

    def test_runner_has_no_recent_year_provider_import_or_heldout_fetcher(self) -> None:
        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("RECENT_YEARS", source)
        self.assertNotIn("fetch_occurrences", source)
        self.assertNotIn("evaluate_country_registry_taxon", source)


if __name__ == "__main__":
    unittest.main()
