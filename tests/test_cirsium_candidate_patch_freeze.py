from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))

from freeze_cirsium_candidate_patch_manifest_v1 import freeze_manifest, freeze_unit


def _write_frame(path: Path, rows: list[dict[str, object]]) -> None:
    pd.DataFrame(rows).to_csv(path, index=False)


class CirsiumCandidatePatchFreezeTests(unittest.TestCase):
    def test_three_method_freeze_is_public_safe_and_count_matched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            local = base / "CIR03.csv"
            sentinel = base / "CIR02.csv"
            baseline = base / "CIR11.csv"

            _write_frame(
                local,
                [
                    {"candidate_cell_id": "a", "latitude": 39.0, "longitude": 140.0, "nearest_anchor_km": 1.0, "relative_relief_score": 0.9, "landform_continuity_score": 0.8, "ridge_valley_continuity_score": 0.7},
                    {"candidate_cell_id": "b", "latitude": 39.1, "longitude": 140.1, "nearest_anchor_km": 0.5, "relative_relief_score": 0.4, "landform_continuity_score": 0.9, "ridge_valley_continuity_score": 0.9},
                    {"candidate_cell_id": "c", "latitude": 39.2, "longitude": 140.2, "nearest_anchor_km": 1.5, "relative_relief_score": 0.8, "landform_continuity_score": 0.8, "ridge_valley_continuity_score": 0.8},
                ],
            )
            _write_frame(
                sentinel,
                [
                    {"candidate_cell_id": "d", "latitude": 40.0, "longitude": 140.0, "broad_robust_support": 0.9, "wetland_water_adjacent_score": 0.8, "topographic_moisture_score": 0.7, "terrain_continuity_score": 0.6},
                    {"candidate_cell_id": "e", "latitude": 40.1, "longitude": 140.1, "broad_robust_support": 0.5, "wetland_water_adjacent_score": 0.9, "topographic_moisture_score": 0.9, "terrain_continuity_score": 0.9},
                    {"candidate_cell_id": "f", "latitude": 40.2, "longitude": 140.2, "broad_robust_support": 0.8, "wetland_water_adjacent_score": 0.4, "topographic_moisture_score": 0.7, "terrain_continuity_score": 0.8},
                ],
            )
            _write_frame(
                baseline,
                [
                    {"candidate_cell_id": "g", "latitude": 35.6, "longitude": 139.2, "nearest_anchor_km": 0.2},
                    {"candidate_cell_id": "h", "latitude": 35.7, "longitude": 139.3, "nearest_anchor_km": 0.8},
                    {"candidate_cell_id": "i", "latitude": 35.8, "longitude": 139.4, "nearest_anchor_km": 1.2},
                ],
            )

            inputs = base / "inputs.csv"
            with inputs.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["cohort_unit_id", "input_csv", "selection_count", "support_provenance_id"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"cohort_unit_id": "CIR03", "input_csv": str(local), "selection_count": 2, "support_provenance_id": "alpine-components-v1"},
                        {"cohort_unit_id": "CIR02", "input_csv": str(sentinel), "selection_count": 2, "support_provenance_id": "wetland-components-v1"},
                        {"cohort_unit_id": "CIR11", "input_csv": str(baseline), "selection_count": 2, "support_provenance_id": ""},
                    ]
                )
            salt = base / "salt.bin"
            salt.write_bytes(b"private-test-salt-1234567890")

            manifest, summary = freeze_manifest(
                cohort_csv=ROOT / "validation" / "cirsium_aza3_prospective_validation_cohort_v1.csv",
                unit_inputs_csv=inputs,
                salt_file=salt,
            )
            self.assertEqual(summary["status"], "FROZEN_PRE_FIELD_OUTCOME")
            self.assertEqual(summary["unit_count"], 3)
            self.assertEqual(len(manifest), 16)
            self.assertFalse(any("latitude" in c.lower() or "longitude" in c.lower() for c in manifest.columns))
            self.assertTrue(manifest["patch_token"].is_unique)
            self.assertTrue((manifest["field_outcomes_opened"] == "false").all())
            counts = manifest.groupby(["cohort_unit_id", "frozen_method"]).size().to_dict()
            self.assertTrue(all(value == 2 for value in counts.values()))
            self.assertEqual(len([key for key in counts if key[0] == "CIR03"]), 3)
            self.assertEqual(len([key for key in counts if key[0] == "CIR02"]), 3)
            self.assertEqual(len([key for key in counts if key[0] == "CIR11"]), 2)

    def test_field_outcome_columns_fail_closed_before_tokenization(self) -> None:
        cohort = list(csv.DictReader((ROOT / "validation" / "cirsium_aza3_prospective_validation_cohort_v1.csv").open(encoding="utf-8")))
        row = next(item for item in cohort if item["cohort_unit_id"] == "CIR03")
        frame = pd.DataFrame(
            [
                {"candidate_cell_id": "a", "latitude": 39.0, "longitude": 140.0, "nearest_anchor_km": 1.0, "relative_relief_score": 0.9, "landform_continuity_score": 0.8, "ridge_valley_continuity_score": 0.7, "field_success": True}
            ]
        )
        with self.assertRaises(ValueError):
            freeze_unit(
                frame,
                cohort_row=row,
                selection_count=1,
                support_provenance_id="alpine-components-v1",
                salt=b"private-test-salt-1234567890",
            )


if __name__ == "__main__":
    unittest.main()
