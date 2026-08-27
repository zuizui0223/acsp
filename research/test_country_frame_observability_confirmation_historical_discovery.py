from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import predeclare_country_frame_observability_confirmation_historical_discovery as mod


class HistoricalDiscoveryBoundaryTests(unittest.TestCase):
    def test_boundary_correction_is_frozen_and_bound_to_parent_protocol(self) -> None:
        corrected = mod.correction()
        self.assertEqual(
            corrected["parent_protocol_fingerprint"],
            "f90f5f614bc370dd2fed40973ac11a3edcb3d88dfd6afebae8ce5de5a4bec547",
        )
        self.assertEqual(
            corrected["correction_fingerprint"],
            "f218782451f7a3a3b248ce8a886a0ccab838eedafd752d8475a9b6682e4fdb1e",
        )
        self.assertEqual(corrected["corrected_boundary"]["discovery_species_facet_years"], [1900, 2020])
        self.assertFalse(
            corrected["corrected_boundary"]["heldout_rows_or_country_facets_allowed_during_freeze"]
        )
        self.assertFalse(corrected["reason"]["frozen_country_heldout_endpoint_opened_before_correction"])

    def test_preheldout_exposure_binding_is_identity_only_and_frozen(self) -> None:
        bound, keys = mod.exposure_binding()
        self.assertEqual(keys, {9775639})
        self.assertEqual(bound["source_run_id"], 32991791263)
        self.assertFalse(bound["source_run_authoritative"])
        self.assertFalse(bound["source_run_freeze_completed"])
        self.assertFalse(bound["source_run_artifact_created"])
        self.assertFalse(bound["frozen_country_heldout_endpoint_opened"])
        self.assertEqual(
            bound["binding_fingerprint"],
            "76e708dfbc45daa55c3a6d383c47e1b35074df5b206a1bc27e584ce7cf7ae638",
        )
        self.assertEqual(
            bound["identity_file_sha256"],
            "057485e27d7da9eccf08ac81cebe1fa996a4a58402299eaa5c70a2e853731602",
        )

    def test_discovery_species_facet_is_explicitly_historical_only(self) -> None:
        payload = {
            "facets": [
                {
                    "field": "SPECIES_KEY",
                    "counts": [
                        {"name": "101", "count": 25},
                        {"name": "102", "count": 31},
                    ],
                }
            ]
        }

        def metadata(key: int):
            if int(key) == 101:
                return {"rank": "SPECIES", "scientificName": "Synthetic species one"}
            return {"rank": "GENUS", "scientificName": "Synthetic genus"}

        with patch.object(mod, "get_json", return_value=payload) as get_json, patch.object(
            mod, "_species_metadata", side_effect=metadata
        ):
            frame = mod.historical_taxon_frame((140.0, 35.0, 141.0, 36.0), 6, 400, 20)

        self.assertEqual(mod.DISCOVERY_YEARS, (1900, 2020))
        self.assertEqual(len(frame), 1)
        self.assertEqual(int(frame.iloc[0]["speciesKey"]), 101)
        self.assertEqual(int(frame.iloc[0]["coordinate_records"]), 25)

        args, kwargs = get_json.call_args
        self.assertFalse(kwargs)
        self.assertEqual(args[0], mod.GBIF_SEARCH)
        params = args[1]
        self.assertEqual(params["year"], "1900,2020")
        self.assertEqual(params["kingdomKey"], 6)
        self.assertEqual(params["limit"], 0)
        self.assertEqual(params["facet"], "speciesKey")
        self.assertEqual(params["facetLimit"], 400)
        self.assertEqual(params["facetMincount"], 20)
        self.assertEqual(params["hasCoordinate"], "true")
        self.assertEqual(params["hasGeospatialIssue"], "false")
        self.assertEqual(params["occurrenceStatus"], "PRESENT")

    def test_corrected_exclusions_union_original_and_visible_quarantine(self) -> None:
        with patch.object(mod.base, "consumed_exclusion_sets", return_value=({101}, {"Consumed one"})):
            keys, names = mod.corrected_exclusion_sets()
        self.assertEqual(keys, {101, 9775639})
        self.assertEqual(names, {"Consumed one"})

    def test_freeze_injects_historical_provider_and_corrected_exclusions(self) -> None:
        aborted = mod.base.FreezeAborted("synthetic preidentity stop", [])
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            mod.base, "consumed_exclusion_sets", return_value=({101}, {"Consumed one"})
        ), patch.object(
            mod.base, "select_observability_frames", side_effect=aborted
        ) as select:
            output = Path(tmp)
            with self.assertRaises(mod.base.FreezeAborted):
                mod.freeze(output)

            select.assert_called_once()
            kwargs = select.call_args.kwargs
            self.assertIs(kwargs["frame_provider"], mod.historical_taxon_frame)
            self.assertEqual(kwargs["excluded_keys"], {101, 9775639})
            self.assertEqual(kwargs["excluded_names"], {"Consumed one"})
            manifest = json.loads((output / "cohort_manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(
            manifest["protocol_fingerprint"],
            "f90f5f614bc370dd2fed40973ac11a3edcb3d88dfd6afebae8ce5de5a4bec547",
        )
        self.assertEqual(manifest["parent_protocol_fingerprint"], manifest["protocol_fingerprint"])
        self.assertEqual(
            manifest["boundary_correction_id"],
            "acsp_country_frame_observability_confirmation_boundary_correction_v1",
        )
        self.assertEqual(
            manifest["boundary_correction_fingerprint"],
            "f218782451f7a3a3b248ce8a886a0ccab838eedafd752d8475a9b6682e4fdb1e",
        )
        self.assertEqual(
            manifest["preheldout_exposure_binding_fingerprint"],
            "76e708dfbc45daa55c3a6d383c47e1b35074df5b206a1bc27e584ce7cf7ae638",
        )
        self.assertEqual(manifest["discovery_species_facet_years"], [1900, 2020])
        self.assertFalse(manifest["discovery_species_facets_include_heldout_years"])
        self.assertEqual(manifest["preheldout_exposed_species_keys"], 1)
        self.assertFalse(manifest["recent_outcomes_opened"])


if __name__ == "__main__":
    unittest.main()
