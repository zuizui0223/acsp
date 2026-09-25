import ast
import contextlib
from dataclasses import asdict
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

from acsp import global_cli, global_geometry, global_inputs, global_lattice, global_patches as product
from acsp.validated_robust import validated_robust_candidate_patches

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
import country_framed_robust_integration as old_inputs
import geoboundaries_v6_provider as old_geometry
import regional_country_lattice as old_lattice
import run_country_framed_integration_development_v2 as old_terrain


def geometry(code="JP"):
    return global_inputs.CountryLandGeometry(code, "POLYGON((0.1 0.1,1.8 0.1,1.8 1.8,0.1 1.8,0.1 0.1))", "fixture", "v1")


def plan(status="READY", code="JP"):
    return {"status": status, "country_plan": {"selected_country_code": code if status == "READY" else None}, "matched_usage_key": 123, "matched_scientific_name": "Synthetic species"}


def occurrences():
    return pd.DataFrame({"latitude": [0.2, 0.4, 0.6, 0.8, 1.0], "longitude": [0.2, 1.1, 0.7, 1.5, 1.2]})


def terrain(points, features, lat_col, lon_col, resolution):
    assert resolution == "2.5m"
    result = points.copy()
    x, y = result[lat_col].to_numpy(), result[lon_col].to_numpy()
    for name, values in zip(product.RAW_TERRAIN_FEATURES, (x * 100 + y, np.sin(y) * 10 + x, (x + y) * 30, np.cos(x) * 2 + y, x * y)):
        result[name] = values
    return result


class GlobalProductTests(unittest.TestCase):
    def test_malformed_occurrence_transport_is_not_empty_evidence(self):
        for payload in ({}, {"results": None}, {"results": [None]}):
            with self.subTest(payload=payload), patch.object(global_inputs, "_get_json", return_value=payload):
                with self.assertRaisesRegex(ValueError, "malformed GBIF occurrence response"):
                    global_inputs.fetch_country_occurrences(123, "JP")
        with patch.object(global_inputs, "_get_json", return_value={"results": []}):
            with self.assertRaisesRegex(ValueError, "GBIF returned no usable historical"):
                global_inputs.fetch_country_occurrences(123, "JP")

    def test_ported_scientific_function_bodies_are_unchanged(self):
        for old, new, names in (
            ("research/regional_country_lattice.py", "acsp/global_lattice.py", None),
            ("research/country_framed_robust_integration.py", "acsp/global_inputs.py", {"CountryLandGeometry", "_parse_land_geometry", "fetch_country_occurrences"}),
            ("research/run_country_framed_integration_development_v2.py", "acsp/global_patches.py", {"regional_terrain_inputs"}),
        ):
            trees = [ast.parse((ROOT / path).read_text(encoding="utf-8")) for path in (old, new)]
            definitions = [{node.name: ast.dump(node, include_attributes=False) for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))} for tree in trees]
            for name in names or definitions[0]:
                self.assertEqual(definitions[0][name], definitions[1][name], f"{new}:{name}")

    def test_lattice_points_and_order_equal_research_for_fragmented_land(self):
        spec = geometry()
        for polygon in (spec.land_geometry_wkt, "POLYGON((0.5 0.5,2.5 0.5,2.5 2.5,0.5 2.5,0.5 0.5))", "MULTIPOLYGON(((0.1 0.1,0.2 0.1,0.2 0.2,0.1 0.2,0.1 0.1)),((1.8 1.8,1.9 1.8,1.9 1.9,1.8 1.9,1.8 1.8)))"):
            with self.subTest(polygon=polygon):
                current = global_inputs.CountryLandGeometry("JP", polygon, "fixture", "v1")
                a, audit_a = global_lattice.build_regional_country_surface(current)
                b, audit_b = old_lattice.build_regional_country_surface(current)
                pd.testing.assert_frame_equal(a, b, check_exact=True)
                self.assertEqual(audit_a.as_dict(), audit_b.as_dict())

    def test_geometry_provider_matches_pinned_research_provider(self):
        payload = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}}]}
        with patch.object(global_geometry, "get_json", return_value=payload) as fetch_a, patch.object(old_geometry, "get_json", return_value=payload) as fetch_b:
            a = global_geometry.fetch_geoboundaries_country_geometry("JP")
            b = old_geometry.fetch_geoboundaries_country_geometry("JP")
        self.assertEqual(asdict(a), asdict(b))
        self.assertEqual(fetch_a.call_args, fetch_b.call_args)

    def test_full_candidate_composition_matches_research_inputs_and_core(self):
        with patch("gbif_fieldmap_builder_app.extract_environment", side_effect=terrain):
            surface, protos, lattice = old_terrain.regional_terrain_inputs(occurrences(), geometry())
            expected, _ = validated_robust_candidate_patches(surface, protos, feature_columns=product.ROBUST_TERRAIN_FEATURES)
            with patch.object(product, "plan_country_for_species", return_value=plan()), patch.object(product, "fetch_geoboundaries_country_geometry", return_value=geometry()), patch.object(product, "fetch_country_occurrences", return_value=occurrences()):
                actual, audit = product.discover_global_candidate_patches("Synthetic species")
        columns = [c for c in expected.columns if c != "validation_status"]
        self.assertGreater(len(expected), 0, "parity fixture must exercise nonempty patch output")
        pd.testing.assert_frame_equal(actual[columns], expected[columns], check_exact=True)
        self.assertTrue(actual["validation_status"].eq("automatic_global_adapter_application").all())
        self.assertEqual(audit["lattice_audit"], lattice.as_dict())
        self.assertEqual(audit["candidate_patch_count"], len(expected))
        self.assertTrue(audit["candidate_generation_run"])
        self.assertFalse(audit["new_scientific_confirmation"])
        self.assertFalse(audit["heldout_2021_2025_opened"])

    def test_explicit_country_metadata_does_not_claim_japanese_validation(self):
        with patch("gbif_fieldmap_builder_app.extract_environment", side_effect=terrain), patch.object(product, "plan_country_for_species", return_value=plan()) as planner, patch.object(product, "fetch_geoboundaries_country_geometry", return_value=geometry()), patch.object(product, "fetch_country_occurrences", return_value=occurrences()):
            patches, audit = product.discover_global_candidate_patches("Synthetic species", country="JP")
        planner.assert_called_once_with("Synthetic species", country="JP")
        self.assertGreater(len(patches), 0)
        self.assertTrue(patches["validation_status"].eq("explicit_country_application_not_independently_confirmed").all())
        self.assertFalse(audit["new_scientific_confirmation"])

    def test_no_ready_country_stops_before_geometry(self):
        with patch.object(product, "plan_country_for_species", return_value=plan("INSUFFICIENT_HISTORICAL_EVIDENCE")), patch.object(product, "fetch_geoboundaries_country_geometry") as fetch:
            patches, audit = product.discover_global_candidate_patches("Synthetic species", country="JP")
        fetch.assert_not_called()
        self.assertTrue(patches.empty)
        self.assertIn("candidate_patch_id", patches)
        self.assertFalse(audit["candidate_generation_run"])

    def test_wrong_geometry_is_rejected_without_replacement(self):
        with patch.object(product, "plan_country_for_species", return_value=plan()), patch.object(product, "fetch_geoboundaries_country_geometry", return_value=geometry("TW")), patch.object(product, "fetch_country_occurrences") as fetch:
            with self.assertRaisesRegex(ValueError, "differs from selected"):
                product.discover_global_candidate_patches("Synthetic species")
        fetch.assert_not_called()

    def test_provider_failure_is_not_evidence_abstention(self):
        for error, should_abstain in ((ValueError("fewer than five usable historical occurrence rows in JP: 2"), True), (RuntimeError("provider unavailable"), False), (ValueError("corrupt payload"), False)):
            with self.subTest(error=error), patch.object(product, "plan_country_for_species", return_value=plan()), patch.object(product, "fetch_geoboundaries_country_geometry", return_value=geometry()), patch.object(product, "fetch_country_occurrences", side_effect=error):
                if should_abstain:
                    patches, audit = product.discover_global_candidate_patches("Synthetic species")
                    self.assertTrue(patches.empty)
                    self.assertEqual(audit["status"], "SENTINEL_OR_ABSTAIN")
                else:
                    with self.assertRaises(type(error)):
                        product.discover_global_candidate_patches("Synthetic species")

    def test_cli_retains_failure_receipt_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "result"
            def fail(*args, **kwargs):
                kwargs["progress"]("COUNTRY_PLANNED", {"country_plan": plan()})
                raise RuntimeError("provider unavailable")
            with patch.object(global_cli, "discover_global_candidate_patches", side_effect=fail), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(global_cli.main(["--taxon", "Synthetic species", "--out-dir", str(out)]), 1)
            self.assertEqual(json.loads((out / "summary.json").read_text())["status"], "TECHNICAL_FAILURE")
            self.assertTrue((out / "country_plan.json").exists())
            self.assertFalse((out / "candidate_patches.csv").exists())
            with self.assertRaises(FileExistsError):
                global_cli.main(["--taxon", "Synthetic species", "--out-dir", str(out)])

    def test_cli_valid_empty_output_and_abstention_are_distinct(self):
        for status, code in (("ROBUST_EMPTY", 0), ("SENTINEL_OR_ABSTAIN", 2)):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "result"
                with patch.object(global_cli, "discover_global_candidate_patches", return_value=(product._empty_patches(), {"status": status})), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(global_cli.main(["--taxon", "Synthetic species", "--out-dir", str(out)]), code)
                self.assertIn("candidate_patch_id", pd.read_csv(out / "candidate_patches.csv"))
                self.assertEqual(json.loads((out / "summary.json").read_text())["status"], status)


if __name__ == "__main__":
    unittest.main()
