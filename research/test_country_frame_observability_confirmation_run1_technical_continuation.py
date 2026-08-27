from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

import predeclare_country_frame_observability_confirmation_run1_technical_continuation as mod


class Run1TechnicalContinuationTests(unittest.TestCase):
    def test_frozen_binding_and_geometry_recovery_fingerprints(self) -> None:
        binding = mod.prefix_binding()
        recovery = mod.geometry_recovery()
        self.assertEqual(
            binding["binding_fingerprint"],
            "ca89763bca9b62abd77c39592a39160112ab32f76419fb9f5da12e6b276491ff",
        )
        self.assertEqual(
            recovery["recovery_fingerprint"],
            "f16ba90f1282ba2ed6fa8dd010ffda1f6a82b4bf8c2247efd35a640d5d9b6f4f",
        )
        self.assertEqual(binding["source_workflow_run"]["run_number"], 1)
        self.assertFalse(binding["source_workflow_run"]["freeze_completed"])
        self.assertFalse(binding["source_workflow_run"]["heldout_outcomes_opened"])
        self.assertFalse(recovery["failure_frame"]["identity_or_country_may_change"])
        self.assertEqual(recovery["geometry_recovery"]["result_country_code"], "HK")
        self.assertEqual(recovery["geometry_recovery"]["recovery_container"], "gbOpen/CHN/ADM1 simplified")
        self.assertFalse(recovery["geometry_recovery"]["alternate_provider_allowed"])

    def test_selection_core_digest_uses_bound_canonicalization(self) -> None:
        columns = [
            "region_cell_index",
            "taxon_group",
            "record_count_stratum",
            "attempt_rank",
            "identity_selection_hash",
            "speciesKey",
            "scientific_name",
            "coordinate_records",
            "selected_country_code",
            "country_selection_basis",
            "historical_selected_country_count",
            "country_frame_observability_score",
            "historical_country_counts_json",
        ]
        frame = pd.DataFrame(
            [
                {
                    "region_cell_index": 1,
                    "taxon_group": "plant",
                    "record_count_stratum": 0,
                    "attempt_rank": 1,
                    "identity_selection_hash": "abc",
                    "speciesKey": 101,
                    "scientific_name": "Synthetic one",
                    "coordinate_records": 20,
                    "selected_country_code": "JP",
                    "country_selection_basis": "synthetic",
                    "historical_selected_country_count": 5,
                    "country_frame_observability_score": 1.791759469228055,
                    "historical_country_counts_json": '{"JP":5}',
                },
                {
                    "region_cell_index": 1,
                    "taxon_group": "plant",
                    "record_count_stratum": 1,
                    "attempt_rank": 1,
                    "identity_selection_hash": "def",
                    "speciesKey": 102,
                    "scientific_name": "Synthetic two",
                    "coordinate_records": 30,
                    "selected_country_code": "HK",
                    "country_selection_basis": "synthetic",
                    "historical_selected_country_count": 9,
                    "country_frame_observability_score": 2.302585092994046,
                    "historical_country_counts_json": '{"HK":9,"JP":1}',
                },
            ]
        )
        first = mod.selection_core_sha256(frame, columns)
        reordered = frame.copy()
        reordered["historical_country_counts_json"] = ['{"JP": 5}', '{"JP":1,"HK":9}']
        second = mod.selection_core_sha256(reordered, columns)
        self.assertEqual(first, second)

    def test_verify_prefix_accepts_same_selection_core_when_failure_becomes_selected(self) -> None:
        columns = [
            "region_cell_index",
            "taxon_group",
            "record_count_stratum",
            "attempt_rank",
            "identity_selection_hash",
            "speciesKey",
            "scientific_name",
            "coordinate_records",
            "selected_country_code",
            "country_selection_basis",
            "historical_selected_country_count",
            "country_frame_observability_score",
            "historical_country_counts_json",
        ]
        audit = pd.DataFrame(
            [
                {
                    "region_cell_index": 1,
                    "taxon_group": "plant",
                    "record_count_stratum": 0,
                    "attempt_rank": 1,
                    "identity_selection_hash": "a",
                    "speciesKey": 11,
                    "scientific_name": "A",
                    "coordinate_records": 20,
                    "selected_country_code": "JP",
                    "country_selection_basis": "x",
                    "historical_selected_country_count": 5,
                    "country_frame_observability_score": 1.0,
                    "historical_country_counts_json": '{"JP":5}',
                    "attempt_status": "selected_declared_frame",
                    "selected": True,
                },
                {
                    "region_cell_index": 2,
                    "taxon_group": "animal",
                    "record_count_stratum": 0,
                    "attempt_rank": 1,
                    "identity_selection_hash": "b",
                    "speciesKey": 22,
                    "scientific_name": "B",
                    "coordinate_records": 30,
                    "selected_country_code": "HK",
                    "country_selection_basis": "x",
                    "historical_selected_country_count": 9,
                    "country_frame_observability_score": 2.0,
                    "historical_country_counts_json": '{"HK":9}',
                    "attempt_status": "selected_declared_frame",
                    "selected": True,
                },
            ]
        )
        digest = mod.selection_core_sha256(audit, columns)
        fake_binding = {
            "prefix_contract": {
                "selection_core_columns": columns,
                "selection_core_sha256": digest,
            }
        }
        with patch.object(mod, "SOURCE_PREFIX_ROWS", 2), patch.object(
            mod, "SOURCE_FAILURE_SPECIES_KEY", 22
        ), patch.object(mod, "SOURCE_FAILURE_COUNTRY", "HK"), patch.object(
            mod, "prefix_binding", return_value=fake_binding
        ):
            self.assertEqual(mod.verify_source_prefix(audit), digest)

    def test_prefix_mismatch_stops_before_continuation_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            mod, "prefix_binding", return_value={"binding_fingerprint": mod.EXPECTED_PREFIX_BINDING_FINGERPRINT}
        ), patch.object(
            mod, "geometry_recovery", return_value={"recovery_fingerprint": mod.EXPECTED_GEOMETRY_RECOVERY_FINGERPRINT}
        ), patch.object(mod.corrected.base, "protocol", return_value={}), patch.object(
            mod.corrected, "correction", return_value={}
        ), patch.object(mod.corrected, "exposure_binding", return_value=({}, set())), patch.object(
            mod, "reproduce_source_prefix", side_effect=mod.PrefixMismatch("synthetic prefix drift")
        ), patch.object(mod.corrected.base, "select_observability_frames") as select, patch.object(
            mod, "_continuation_manifest_fields", return_value={
                "source_prefix_reproduced_before_continuation": False,
                "technical_continuation_of_run1": True,
            }
        ):
            with self.assertRaises(mod.PrefixMismatch):
                mod.freeze(Path(tmp))
            select.assert_not_called()
            manifest = json.loads((Path(tmp) / "cohort_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(
                manifest["status"],
                "observability_confirmation_run1_technical_continuation_prefix_mismatch",
            )
            self.assertFalse(manifest["recent_outcomes_opened"])

    def test_source_preflight_uses_bound_abort_sentinel_before_continuation(self) -> None:
        cache = MagicMock()
        source_audit = pd.DataFrame(
            [{
                "speciesKey": mod.SOURCE_FAILURE_SPECIES_KEY,
                "selected_country_code": mod.SOURCE_FAILURE_COUNTRY,
                "attempt_status": "geometry_provider_error_abort",
            }]
        )
        aborted = mod.corrected.base.FreezeAborted("synthetic", source_audit.to_dict("records"))
        with patch.object(
            mod.corrected, "corrected_exclusion_sets", return_value=(set(), set())
        ), patch.object(
            mod.corrected.base, "select_observability_frames", side_effect=aborted
        ) as select, patch.object(
            mod, "verify_source_prefix", return_value="bound-digest"
        ), patch.object(
            mod, "prefix_binding", return_value={"prefix_contract": {"selection_core_sha256": "bound-digest"}}
        ), patch.object(mod, "SOURCE_PREFIX_ROWS", 1):
            result = mod.reproduce_source_prefix(cache)
        self.assertEqual(len(result), 1)
        kwargs = select.call_args.kwargs
        self.assertIs(kwargs["frame_provider"], cache.frame)
        self.assertIs(kwargs["facet_provider"], cache.facet)
        self.assertIs(kwargs["geometry_provider"], cache.source_prefix_geometry)


if __name__ == "__main__":
    unittest.main()
