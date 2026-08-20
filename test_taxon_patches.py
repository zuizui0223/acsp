import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from acsp.robust_cli import main as robust_cli_main
from acsp.taxon_patches import _stable_surface_seed, _validate_bounds, discover_validated_candidate_patches


class TaxonPatchEntryTests(unittest.TestCase):
    def test_extent_validation_and_surface_seed_are_deterministic(self):
        bounds = (139.0, 34.0, 140.0, 35.0)
        self.assertEqual(_validate_bounds(bounds), bounds)
        self.assertEqual(_stable_surface_seed(bounds), _stable_surface_seed(bounds))
        with self.assertRaisesRegex(ValueError, "west < east"):
            _validate_bounds((140.0, 34.0, 139.0, 35.0))

    @patch("acsp.taxon_patches.validated_robust_candidate_patches")
    @patch("acsp.taxon_patches._terrain_inputs")
    @patch("acsp.taxon_patches.fetch_region_occurrences")
    @patch("acsp.taxon_patches.match_gbif_species")
    def test_discovery_adapter_only_wires_confirmed_inputs(
        self,
        mock_match,
        mock_fetch,
        mock_terrain,
        mock_validated,
    ):
        bounds = (139.0, 34.0, 140.0, 35.0)
        mock_match.return_value = {
            "taxon_key": 123,
            "requested_name": "Example species",
            "matched_name": "Example species",
            "match_type": "EXACT",
            "confidence": 100,
            "status": "ACCEPTED",
        }
        mock_fetch.return_value = pd.DataFrame(
            {"latitude": [34.1, 34.2, 34.3, 34.4, 34.5], "longitude": [139.1, 139.2, 139.3, 139.4, 139.5]}
        )
        surface = pd.DataFrame(
            {
                "latitude": [34.2, 34.3],
                "longitude": [139.2, 139.3],
                "survey_area_id": ["field", "field"],
                "elevation": [1.0, 2.0],
                "slope": [1.0, 2.0],
                "aspect_sin": [0.0, 0.1],
                "aspect_cos": [1.0, 0.9],
                "roughness": [1.0, 2.0],
                "tpi": [0.0, 0.1],
            }
        )
        prototypes = surface.iloc[:1].copy()
        mock_terrain.return_value = (surface, prototypes, 99)
        patches = pd.DataFrame({"site_id": ["field-Z001"], "survey_area_id": ["field"]})
        audit = type("Audit", (), {"as_dict": lambda self: {"prototype_count": 5}})()
        mock_validated.return_value = (patches, audit)

        result, manifest = discover_validated_candidate_patches("Example species", bounds, area_id="field")

        self.assertEqual(len(result), 1)
        mock_fetch.assert_called_once_with(123, bounds)
        mock_terrain.assert_called_once()
        kwargs = mock_validated.call_args.kwargs
        self.assertEqual(kwargs["area_col"], "survey_area_id")
        self.assertEqual(
            tuple(kwargs["feature_columns"]),
            ("elevation", "slope", "aspect_sin", "aspect_cos", "roughness", "tpi"),
        )
        self.assertEqual(manifest["input_mode"], "taxon_extent")
        self.assertEqual(manifest["candidate_patch_count"], 1)
        self.assertTrue(manifest["candidate_generation_only"])
        self.assertFalse(manifest["routing_or_budget_optimization"])

    def test_cli_taxon_mode_requires_extent(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "patches.csv"
            with self.assertRaisesRegex(ValueError, "requires --extent"):
                robust_cli_main(["--taxon", "Example species", "--output", str(output)])

    @patch("acsp.taxon_patches.discover_validated_candidate_patches")
    def test_cli_taxon_mode_exports_only_candidate_patches(self, mock_discover):
        mock_discover.return_value = (
            pd.DataFrame(
                {
                    "site_id": ["survey-Z001"],
                    "survey_area_id": ["survey"],
                    "latitude": [34.5],
                    "longitude": [139.5],
                }
            ),
            {
                "input_mode": "taxon_extent",
                "requested_name": "Example species",
                "matched_name": "Example species",
                "occurrence_rows": 20,
                "surface_points": 800,
                "prototype_rows": 12,
                "candidate_generation_only": True,
                "routing_or_budget_optimization": False,
            },
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "patches.csv"
            summary = root / "summary.json"
            exit_code = robust_cli_main(
                [
                    "--taxon", "Example species",
                    "--extent", "139", "34", "140", "35",
                    "--output", str(output),
                    "--summary-json", str(summary),
                ]
            )
            self.assertEqual(exit_code, 0)
            table = pd.read_csv(output)
            manifest = json.loads(summary.read_text())
        self.assertEqual(len(table), 1)
        self.assertEqual(manifest["input_mode"], "taxon_extent")
        self.assertEqual(manifest["validated_support_fraction"], 0.025)
        self.assertEqual(manifest["candidate_patch_count"], 1)
        self.assertFalse(manifest["routing_or_budget_optimization"])


if __name__ == "__main__":
    unittest.main()
