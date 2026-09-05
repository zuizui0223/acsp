import tempfile
import unittest
from pathlib import Path

import pandas as pd

from research.build_cirsium_private_source_manifest_v1 import build_manifest


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _requirements():
    return pd.DataFrame([
        {"cohort_unit_id": "CIR03", "species_binomial": "Cirsium ugoense", "occurrence_problem_class": "LOCAL_CONTINUATION", "requires_primary_anchor_geometry": True, "requires_gsi_dem": True, "requires_esa_worldcover_2021": False, "requires_gsi_coastline": False, "requires_broad_sentinel_support": False, "requires_target_component_id": False},
        {"cohort_unit_id": "CIR08", "species_binomial": "Cirsium brevicaule", "occurrence_problem_class": "LOCAL_CONTINUATION", "requires_primary_anchor_geometry": True, "requires_gsi_dem": False, "requires_esa_worldcover_2021": True, "requires_gsi_coastline": True, "requires_broad_sentinel_support": False, "requires_target_component_id": True},
        {"cohort_unit_id": "CIR02", "species_binomial": "Cirsium inundatum", "occurrence_problem_class": "SENTINEL", "requires_primary_anchor_geometry": False, "requires_gsi_dem": True, "requires_esa_worldcover_2021": True, "requires_gsi_coastline": False, "requires_broad_sentinel_support": True, "requires_target_component_id": False},
    ])


def _cohort():
    return pd.DataFrame([
        {"cohort_unit_id": "CIR03", "aza3_slot_id": "P1_Cirsium_ugoense_A", "range_sector": "akita", "sentinel_evidence_class": "LOCAL_PRIMARY_ANCHOR_PRESENT", "sentinel_subregime": "NOT_APPLICABLE", "outcome_opened": False},
        {"cohort_unit_id": "CIR08", "aza3_slot_id": "P3_Cirsium_brevicaule_B", "range_sector": "okinawa", "sentinel_evidence_class": "LOCAL_PRIMARY_ANCHOR_PRESENT", "sentinel_subregime": "NOT_APPLICABLE", "outcome_opened": False},
        {"cohort_unit_id": "CIR02", "aza3_slot_id": "P1_Cirsium_inundatum_A", "range_sector": "aomori", "sentinel_evidence_class": "SENTINEL_UNCERTAINTY_KERNEL_ELIGIBLE", "sentinel_subregime": "UNCERTAINTY_FOOTPRINT", "outcome_opened": False},
    ])


class PrivateSourceManifestBuilderTests(unittest.TestCase):
    def test_cir03_manifest_requires_and_hashes_anchor_and_dem(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sector = _write(root / "sector.geojson", "sector")
            grid = _write(root / "grid.csv", "grid")
            anchor = _write(root / "anchors.csv", "anchors")
            dem = _write(root / "dem.tif", "dem")

            with self.assertRaisesRegex(ValueError, "requires at least one GSI DEM"):
                build_manifest(
                    _requirements(), _cohort(), unit_id="CIR03",
                    range_sector_file=sector, raw_grid_file=grid, primary_anchor_file=anchor,
                )

            manifest = build_manifest(
                _requirements(), _cohort(), unit_id="CIR03",
                range_sector_file=sector, raw_grid_file=grid, primary_anchor_file=anchor,
                gsi_dem_files=(dem,),
            )
            self.assertEqual(manifest["cohort_unit_id"], "CIR03")
            self.assertIs(manifest["gsi_dem"]["required"], True)
            self.assertEqual(manifest["gsi_dem"]["files"][0]["file_name"], "dem.tif")
            self.assertTrue(manifest["occurrence_input"]["eligible_primary_anchor_private_table_sha256"])
            self.assertIs(manifest["field_outcomes_opened"], False)

    def test_cir08_fails_closed_without_coastline_and_component(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sector = _write(root / "sector.geojson", "sector")
            grid = _write(root / "grid.csv", "grid")
            anchor = _write(root / "anchors.csv", "anchors")
            wc = _write(root / "worldcover.tif", "wc")

            with self.assertRaisesRegex(ValueError, "GSI coastline"):
                build_manifest(
                    _requirements(), _cohort(), unit_id="CIR08",
                    range_sector_file=sector, raw_grid_file=grid, primary_anchor_file=anchor,
                    worldcover_files=(wc,),
                )

    def test_cir02_preserves_frozen_uncertainty_subregime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sector = _write(root / "sector.geojson", "sector")
            grid = _write(root / "grid.csv", "grid")
            evidence = _write(root / "sentinel.csv", "sentinel")
            dem = _write(root / "dem.tif", "dem")
            wc = _write(root / "worldcover.tif", "wc")
            manifest = build_manifest(
                _requirements(), _cohort(), unit_id="CIR02",
                range_sector_file=sector, raw_grid_file=grid, sentinel_evidence_file=evidence,
                gsi_dem_files=(dem,), worldcover_files=(wc,),
            )
            self.assertEqual(manifest["occurrence_input"]["sentinel_subregime"], "UNCERTAINTY_FOOTPRINT")
            self.assertIs(manifest["broad_sentinel_support"]["required"], True)
            self.assertTrue(manifest["broad_sentinel_support"]["private_support_input_sha256"])


if __name__ == "__main__":
    unittest.main()
