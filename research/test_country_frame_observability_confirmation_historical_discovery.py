from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import predeclare_country_frame_observability_confirmation_historical_discovery as mod


class HistoricalDiscoveryBoundaryTests(unittest.TestCase):
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

    def test_freeze_injects_historical_provider_and_records_boundary_on_abort(self) -> None:
        aborted = mod.base.FreezeAborted("synthetic preidentity stop", [])
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            mod.base, "select_observability_frames", side_effect=aborted
        ) as select:
            output = Path(tmp)
            with self.assertRaises(mod.base.FreezeAborted):
                mod.freeze(output)

            select.assert_called_once_with(frame_provider=mod.historical_taxon_frame)
            manifest = json.loads((output / "cohort_manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(
            manifest["protocol_fingerprint"],
            "f90f5f614bc370dd2fed40973ac11a3edcb3d88dfd6afebae8ce5de5a4bec547",
        )
        self.assertEqual(
            manifest["boundary_correction_id"],
            "historical_discovery_species_facets_1900_2020_v1",
        )
        self.assertEqual(manifest["discovery_species_facet_years"], [1900, 2020])
        self.assertFalse(manifest["discovery_species_facets_include_heldout_years"])
        self.assertFalse(manifest["recent_outcomes_opened"])


if __name__ == "__main__":
    unittest.main()
