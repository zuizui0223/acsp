import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from acsp.cli import main


class AcspCliTests(unittest.TestCase):
    def test_zones_command_writes_zone_level_output(self):
        candidates = pd.DataFrame({
            "site_id": [1, 2, 3], "priority_score": [0.9, 0.8, 0.7],
            "latitude": [35.0, 35.002, 35.03], "longitude": [139.0, 139.002, 139.03],
        })
        with tempfile.TemporaryDirectory() as temporary_directory:
            workdir = Path(temporary_directory)
            input_csv = workdir / "candidates.csv"
            output_csv = workdir / "zones.csv"
            summary_json = workdir / "summary.json"
            candidates.to_csv(input_csv, index=False)
            main(["zones", "--input", str(input_csv), "--output", str(output_csv),
                  "--summary-json", str(summary_json), "--merge-distance-m", "1000"])
            zones = pd.read_csv(output_csv)
            summary = json.loads(summary_json.read_text(encoding="utf-8"))
        self.assertEqual(len(zones), 2)
        self.assertEqual(summary["output_unit"], "survey_zone")

    def test_recommend_command_writes_ranked_csv_and_summary(self):
        candidates = pd.DataFrame(
            {
                "site_id": ["n1", "n2", "n3", "n4", "s1", "s2", "s3", "s4"],
                "survey_area_id": ["north"] * 4 + ["south"] * 4,
                "priority_score": [0.90, 0.80, 0.70, 0.60, 0.95, 0.85, 0.75, 0.65],
            }
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            workdir = Path(temporary_directory)
            input_csv = workdir / "candidates.csv"
            output_csv = workdir / "recommended.csv"
            summary_json = workdir / "summary.json"
            candidates.to_csv(input_csv, index=False)

            exit_code = main(
                [
                    "recommend",
                    "--input",
                    str(input_csv),
                    "--output",
                    str(output_csv),
                    "--summary-json",
                    str(summary_json),
                    "--per-area",
                    "3",
                ]
            )

            selected = pd.read_csv(output_csv)
            summary = json.loads(summary_json.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(selected.groupby("survey_area_id").size().to_dict(), {"north": 3, "south": 3})
        self.assertEqual(selected["recommendation_rank"].tolist(), [1, 2, 3, 4, 5, 6])
        self.assertEqual(summary["selected_count"], 6)
        self.assertEqual(summary["selected_count_by_area"], {"north": 3, "south": 3})

    def test_recommend_command_accepts_extent(self):
        candidates = pd.DataFrame({
            "site_id": [1, 2, 3],
            "priority_score": [0.8, 0.9, 1.0],
            "latitude": [35.0, 35.2, 36.0],
            "longitude": [139.0, 139.2, 140.0],
        })
        with tempfile.TemporaryDirectory() as temporary_directory:
            workdir = Path(temporary_directory)
            input_csv = workdir / "candidates.csv"
            output_csv = workdir / "recommended.csv"
            summary_json = workdir / "summary.json"
            candidates.to_csv(input_csv, index=False)
            main([
                "recommend", "--input", str(input_csv), "--output", str(output_csv),
                "--summary-json", str(summary_json), "--extent", "138.9", "34.9", "139.3", "35.3",
            ])
            selected = pd.read_csv(output_csv)
            summary = json.loads(summary_json.read_text(encoding="utf-8"))
        self.assertEqual(selected["site_id"].tolist(), [2, 1])
        self.assertEqual(summary["extent"], [138.9, 34.9, 139.3, 35.3])

    def test_budget_command_outputs_geometry_ordered_feasible_prefix(self):
        candidates = pd.DataFrame({
            "site_id": list(range(1, 9)),
            "survey_area_id": ["island"] * 8,
            "latitude": [35.00, 35.01, 35.02, 35.03, 35.04, 35.05, 35.06, 35.07],
            "longitude": [139.00, 139.01, 139.02, 139.03, 139.04, 139.05, 139.06, 139.07],
        })
        with tempfile.TemporaryDirectory() as temporary_directory:
            workdir = Path(temporary_directory)
            input_csv = workdir / "candidates.csv"
            output_csv = workdir / "budget.csv"
            summary_json = workdir / "budget.json"
            prefix_csv = workdir / "prefix.csv"
            candidates.to_csv(input_csv, index=False)
            exit_code = main([
                "budget",
                "--input", str(input_csv),
                "--output", str(output_csv),
                "--summary-json", str(summary_json),
                "--prefix-audit", str(prefix_csv),
                "--hub-latitude", "35.0",
                "--hub-longitude", "139.0",
                "--days", "1",
                "--taxon-profile", "plant",
                "--coverage-radius-km", "1",
                "--max-sites", "8",
            ])
            selected = pd.read_csv(output_csv)
            prefix = pd.read_csv(prefix_csv)
            summary = json.loads(summary_json.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertGreater(len(selected), 0)
        self.assertLess(len(selected), len(candidates))
        self.assertEqual(selected["coverage_rank"].tolist(), list(range(1, len(selected) + 1)))
        self.assertEqual(summary["selected_count"], len(selected))
        self.assertEqual(summary["target_days"], 1)
        self.assertEqual(summary["taxon_profile"], "plant")
        self.assertIn("routing_claim", summary)
        self.assertEqual(prefix["k"].tolist(), list(range(1, 9)))

    def test_budget_command_rejects_multiple_survey_areas(self):
        candidates = pd.DataFrame({
            "site_id": [1, 2],
            "survey_area_id": ["a", "b"],
            "latitude": [35.0, 35.1],
            "longitude": [139.0, 139.1],
        })
        with tempfile.TemporaryDirectory() as temporary_directory:
            workdir = Path(temporary_directory)
            input_csv = workdir / "candidates.csv"
            candidates.to_csv(input_csv, index=False)
            with self.assertRaisesRegex(ValueError, "one survey area at a time"):
                main([
                    "budget",
                    "--input", str(input_csv),
                    "--output", str(workdir / "out.csv"),
                    "--hub-latitude", "35.0",
                    "--hub-longitude", "139.0",
                    "--days", "1",
                    "--taxon-profile", "plant",
                ])


if __name__ == "__main__":
    unittest.main()
