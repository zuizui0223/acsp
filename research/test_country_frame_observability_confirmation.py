from __future__ import annotations

import math
from pathlib import Path
import unittest

import pandas as pd

import predeclare_country_frame_observability_confirmation as mod


class _Geom:
    source_id = "test-geometry"
    source_version = "test;canonical_geojson_sha256=" + ("a" * 64)


class ObservabilityConfirmationFreezeTests(unittest.TestCase):
    def test_protocol_fingerprint_and_freeze_boundary(self) -> None:
        cfg = mod.protocol()
        self.assertEqual(
            cfg["protocol_fingerprint"],
            "f90f5f614bc370dd2fed40973ac11a3edcb3d88dfd6afebae8ce5de5a4bec547",
        )
        self.assertEqual(cfg["cohort"]["target_frames"], 96)
        self.assertFalse(cfg["execution"]["freeze_workflow_may_open_heldout"])
        self.assertFalse(cfg["decision"]["score_cutoff_creation_allowed"])
        self.assertEqual(
            cfg["country_declaration"]["score_formula"],
            "log1p(historical_selected_country_count)",
        )
        self.assertIn("2021-2025 occurrence rows", cfg["freeze_boundary"]["forbidden"])
        self.assertIn("2021-2025 country facets", cfg["freeze_boundary"]["forbidden"])

    def test_terminal_fresh_exclusion_is_identity_only_and_pinned(self) -> None:
        frame = pd.read_csv(mod.TERMINAL_FRESH_IDENTITY_PATH)
        self.assertEqual(
            list(frame.columns),
            ["fresh_pair_id", "taxon_group", "speciesKey", "scientific_name"],
        )
        keys, names = mod._terminal_fresh_identity_exclusions()
        self.assertEqual(len(keys), 48)
        self.assertEqual(len(names), 48)
        self.assertNotIn("temporal_status", frame.columns)
        self.assertNotIn("robust_minus_random_recall", frame.columns)

    def test_score_is_threshold_free_log1p(self) -> None:
        self.assertTrue(math.isclose(mod.observability_score(5), math.log1p(5)))
        self.assertTrue(math.isclose(mod.observability_score(5726), math.log1p(5726)))
        with self.assertRaises(ValueError):
            mod.observability_score(-1)

    def _synthetic_providers(self):
        facet_counts: dict[int, dict[str, int]] = {}
        selected_expected: dict[tuple[int, str, int], tuple[int, int]] = {}
        calls = {"n": 0}
        seed = int(mod.protocol()["cohort"]["selection_seed"])

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
                rows.append(
                    {
                        "speciesKey": key,
                        "scientific_name": f"Synthetic {region} {group} {i + 1}",
                        "coordinate_records": (i + 1) * 10,
                    }
                )
            frame = pd.DataFrame(rows)
            frame["record_count_stratum"] = pd.qcut(
                frame["coordinate_records"].rank(method="first"), 4, labels=False
            ).astype(int)
            for stratum in range(4):
                pair = frame.loc[
                    frame["record_count_stratum"].eq(stratum), "speciesKey"
                ].astype(int).tolist()
                ordered = sorted(
                    pair,
                    key=lambda key: mod.identity_hash(seed, region, group, stratum, key),
                )
                if region == 1 and group == "plant" and stratum == 0:
                    facet_counts[ordered[0]] = {}
                    facet_counts[ordered[1]] = {"JP": 17}
                    selected_expected[(region, group, stratum)] = (ordered[1], 17)
                elif region == 1 and group == "plant" and stratum == 1:
                    facet_counts[ordered[0]] = {"JP": 5}
                    facet_counts[ordered[1]] = {"JP": 5000}
                    selected_expected[(region, group, stratum)] = (ordered[0], 5)
                else:
                    facet_counts[ordered[0]] = {"JP": 20}
                    facet_counts[ordered[1]] = {"JP": 5000}
                    selected_expected[(region, group, stratum)] = (ordered[0], 20)
            return frame.drop(columns="record_count_stratum")

        def facet_provider(species_key, years):
            self.assertEqual(tuple(years), tuple(mod.HISTORICAL_YEARS))
            return facet_counts[int(species_key)]

        def geometry_provider(country):
            self.assertEqual(country, "JP")
            return _Geom()

        return frame_provider, facet_provider, geometry_provider, selected_expected

    def test_complete_synthetic_freeze_skips_no_country_but_never_ranks_by_count(self) -> None:
        frame_provider, facet_provider, geometry_provider, expected = self._synthetic_providers()
        selected, audit = mod.select_observability_frames(
            frame_provider=frame_provider,
            facet_provider=facet_provider,
            geometry_provider=geometry_provider,
            excluded_keys=set(),
            excluded_names=set(),
            explicit_prefixes=(),
        )
        self.assertEqual(len(selected), 96)
        self.assertEqual(selected["speciesKey"].nunique(), 96)
        self.assertEqual(len(audit), 97)

        first = selected[
            selected["region_cell_index"].eq(1)
            & selected["taxon_group"].eq("plant")
            & selected["record_count_stratum"].eq(0)
        ].iloc[0]
        self.assertEqual(
            (int(first["speciesKey"]), int(first["historical_selected_country_count"])),
            expected[(1, "plant", 0)],
        )
        self.assertEqual(int(first["declaration_attempt_rank"]), 2)

        second = selected[
            selected["region_cell_index"].eq(1)
            & selected["taxon_group"].eq("plant")
            & selected["record_count_stratum"].eq(1)
        ].iloc[0]
        self.assertEqual(
            (int(second["speciesKey"]), int(second["historical_selected_country_count"])),
            expected[(1, "plant", 1)],
        )
        self.assertEqual(int(second["historical_selected_country_count"]), 5)
        self.assertEqual(int(second["declaration_attempt_rank"]), 1)

    def test_provider_error_aborts_instead_of_selecting_next_identity(self) -> None:
        frame_provider, _, geometry_provider, _ = self._synthetic_providers()

        def failing_facet_provider(species_key, years):
            del species_key, years
            raise RuntimeError("synthetic provider failure")

        with self.assertRaises(mod.FreezeAborted) as caught:
            mod.select_observability_frames(
                frame_provider=frame_provider,
                facet_provider=failing_facet_provider,
                geometry_provider=geometry_provider,
                excluded_keys=set(),
                excluded_names=set(),
                explicit_prefixes=(),
            )
        self.assertEqual(len(caught.exception.audit_rows), 1)
        self.assertEqual(
            caught.exception.audit_rows[0]["attempt_status"],
            "historical_provider_error_abort",
        )

    def test_freeze_module_does_not_import_recent_year_constant(self) -> None:
        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("RECENT_YEARS", source)
        self.assertNotIn("recent_heldout_occurrence_rows", source)


if __name__ == "__main__":
    unittest.main()
