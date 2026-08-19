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

    def test_auto_effort_cli_accepts_frozen_support_patch_schema(self):
        candidates = pd.DataFrame(
            {
                "site_id": ["patch-a", "patch-b", "blocked"],
                "survey_area_id": ["island", "island", "island"],
                "latitude": [34.7000, 34.7060, 34.7120],
                "longitude": [139.3000, 139.3000, 139.3000],
                "ecological_status": ["frozen_robust_support_patch"] * 3,
                "consensus_support_rank_best": [0.01, 0.02, 0.03],
            }
        )
        edges = pd.DataFrame(
            {
                "from_id": ["hub", "patch-a", "hub", "patch-b"],
                "to_id": ["patch-a", "hub", "patch-b", "hub"],
                "travel_minutes": [10, 10, 20, 20],
                "mode": ["walk", "walk", "walk", "walk"],
            }
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            workdir = Path(temporary_directory)
            input_csv = workdir / "robust_support_patches.csv"
            movement_csv = workdir / "movement_edges.csv"
            output_csv = workdir / "automatic_plan.csv"
            summary_json = workdir / "automatic_plan.json"
            frontier_csv = workdir / "frontier.csv"
            reachability_csv = workdir / "reachability.csv"
            candidates.to_csv(input_csv, index=False)
            edges.to_csv(movement_csv, index=False)

            exit_code = main(
                [
                    "auto-effort",
                    "--input", str(input_csv),
                    "--movement-edges", str(movement_csv),
                    "--hub-id", "hub",
                    "--allowed-mode", "walk",
                    "--taxon-profile", "plant",
                    "--output", str(output_csv),
                    "--summary-json", str(summary_json),
                    "--frontier-audit", str(frontier_csv),
                    "--reachability-audit", str(reachability_csv),
                ]
            )
            selected = pd.read_csv(output_csv)
            summary = json.loads(summary_json.read_text(encoding="utf-8"))
            reachability = pd.read_csv(reachability_csv)

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["input_candidate_count"], 3)
        self.assertEqual(summary["reachable_candidate_count"], 2)
        self.assertEqual(summary["unreachable_candidate_count"], 1)
        self.assertFalse(summary["target_days_user_supplied"])
        self.assertFalse(summary["target_site_count_user_supplied"])
        self.assertFalse(summary["survey_budget_user_supplied"])
        self.assertFalse(summary["straight_line_fallback"])
        self.assertTrue(summary["reachability_applied_before_coverage"])
        self.assertNotIn("blocked", selected["site_id"].tolist())
        self.assertTrue(selected["ecological_status"].eq("frozen_robust_support_patch").all())
        blocked = reachability.loc[reachability["site_id"].eq("blocked")].iloc[0]
        self.assertFalse(bool(blocked["roundtrip_reachable"]))


if __name__ == "__main__":
    unittest.main()
