import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from acsp.robust_cli import main as robust_cli_main
from acsp.taxon_patches import (
    VALIDATED_JAPAN_REGIONS,
    _stable_surface_seed,
    _validate_bounds,
    discover_validated_candidate_patches,
    discover_validated_candidate_patches_japan,
)


class _Audit:
    def as_dict(self):
        return {"prototype_count": 5, "leave_one_out_worlds": 5}


class TaxonPatchEntryTests(unittest.TestCase):
    def test_extent_validation_and_surface_seed_are_deterministic(self):
        bounds = (139.0, 34.0, 140.0, 35.0)
        self.assertEqual(_validate_bounds(bounds), bounds)
        self.assertEqual(_stable_surface_seed(bounds), _stable_surface_seed(bounds))
        with self.assertRaisesRegex(ValueError, "west < east"):
            _validate_bounds((140.0, 34.0, 139.0, 35.0))

    def test_japan_regions_are_the_fixed_twelve_region_design(self):
        self.assertEqual(len(VALIDATED_JAPAN_REGIONS), 12)
        ids = [row[0] for row in VALIDATED_JAPAN_REGIONS]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(VALIDATED_JAPAN_REGIONS[0], ("hokkaido-west", "Hokkaido west", "north", 140.0, 42.5, 142.0, 44.5))
        self.assertEqual(VALIDATED_JAPAN_REGIONS[-1], ("ryukyu", "Ryukyu", "south", 126.0, 24.0, 130.0, 28.5))

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
        mock_validated.return_value = (patches, _Audit())

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

    @patch("acsp.taxon_patches.validated_robust_candidate_patches")
    @patch("acsp.taxon_patches._terrain_inputs")
    @patch("acsp.taxon_patches.fetch_region_occurrences")
    @patch("acsp.taxon_patches.match_gbif_species")
    def test_species_only_japan_mode_keeps_regions_independent_and_audited(
        self,
        mock_match,
        mock_fetch,
        mock_terrain,
        mock_validated,
    ):
        mock_match.return_value = {
            "taxon_key": 123,
            "requested_name": "Example species",
            "matched_name": "Example species",
            "match_type": "EXACT",
            "confidence": 100,
            "status": "ACCEPTED",
        }
        occurrences = pd.DataFrame(
            {"latitude": [35.1, 35.2, 35.3, 35.4, 35.5], "longitude": [139.1, 139.2, 139.3, 139.4, 139.5]}
        )
        calls = {"n": 0}

        def fetch_side_effect(taxon_key, bounds):
            calls["n"] += 1
            if calls["n"] == 2:
                raise ValueError("fewer than five usable occurrence rows in the declared extent: 3")
            return occurrences.copy()

        def terrain_side_effect(rows, bounds, *, area_id):
            surface = pd.DataFrame(
                {
                    "latitude": [35.1, 35.2],
                    "longitude": [139.1, 139.2],
                    "survey_area_id": [area_id, area_id],
                    "elevation": [1.0, 2.0],
                    "slope": [1.0, 2.0],
                    "aspect_sin": [0.0, 0.1],
                    "aspect_cos": [1.0, 0.9],
                    "roughness": [1.0, 2.0],
                    "tpi": [0.0, 0.1],
                }
            )
            return surface, surface.iloc[:1].copy(), 99

        def validated_side_effect(surface, prototypes, **kwargs):
            area_id = str(surface["survey_area_id"].iloc[0])
            return pd.DataFrame({"site_id": [f"{area_id}-Z001"], "survey_area_id": [area_id]}), _Audit()

        mock_fetch.side_effect = fetch_side_effect
        mock_terrain.side_effect = terrain_side_effect
        mock_validated.side_effect = validated_side_effect

        patches, manifest = discover_validated_candidate_patches_japan("Example species")

        self.assertEqual(mock_fetch.call_count, 12)
        self.assertEqual(manifest["declared_region_count"], 12)
        self.assertEqual(manifest["evaluated_region_count"], 11)
        self.assertEqual(manifest["skipped_region_count"], 1)
        self.assertEqual(len(patches), 11)
        self.assertEqual(patches["validation_region_id"].nunique(), 11)
        self.assertEqual(manifest["region_status"][1]["status"], "skipped_insufficient_or_unavailable")
        self.assertFalse(manifest["routing_or_budget_optimization"])

    @patch("acsp.taxon_patches.discover_validated_candidate_patches_japan")
    def test_cli_taxon_without_extent_uses_fixed_japan_regions(self, mock_discover):
        mock_discover.return_value = (
            pd.DataFrame({"site_id": ["izu-Z001"], "survey_area_id": ["izu"], "latitude": [34.5], "longitude": [139.5]}),
            {
                "input_mode": "taxon_japan_validated_regions",
                "requested_name": "Example species",
                "matched_name": "Example species",
                "declared_region_count": 12,
                "evaluated_region_count": 4,
                "skipped_region_count": 8,
                "candidate_generation_only": True,
                "routing_or_budget_optimization": False,
            },
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "patches.csv"
            summary = root / "summary.json"
            exit_code = robust_cli_main(
                ["--taxon", "Example species", "--output", str(output), "--summary-json", str(summary)]
            )
            self.assertEqual(exit_code, 0)
            table = pd.read_csv(output)
            manifest = json.loads(summary.read_text())
        self.assertEqual(len(table), 1)
        self.assertEqual(manifest["input_mode"], "taxon_japan_validated_regions")
        self.assertEqual(manifest["validated_support_fraction"], 0.025)
        self.assertEqual(manifest["declared_region_count"], 12)
        self.assertFalse(manifest["routing_or_budget_optimization"])

    @patch("acsp.taxon_patches.discover_validated_candidate_patches")
    def test_cli_custom_extent_remains_available(self, mock_discover):
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
        self.assertEqual(manifest["candidate_patch_count"], 1)


if __name__ == "__main__":
    unittest.main()
