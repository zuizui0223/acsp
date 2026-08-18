import json
from functools import partial
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from acsp.cli import main
from acsp.operational_budget import select_largest_feasible_prefix
from acsp.travel_matrix import (
    estimate_matrix_trip,
    normalize_travel_time_matrix,
)


TEST_PROTOCOL = {
    "daily_field_hours": 8.0,
    "search_minutes_per_cell": 60,
    "access_buffer_minutes_per_cell": 0,
    "protocol_id": "travel-matrix-test",
    "taxon_group": "plant",
    "minimum_repeat_visits": 1,
}


class TravelMatrixTests(unittest.TestCase):
    def test_undirected_matrix_is_mirrored_and_conflicts_are_rejected(self):
        matrix = pd.DataFrame([
            {
                "from_id": "hub",
                "to_id": 1,
                "travel_minutes": 12,
                "distance_km": 3.5,
                "mode": "road",
            }
        ])
        normalized = normalize_travel_time_matrix(matrix, undirected=True)
        self.assertEqual(
            set(map(tuple, normalized[["from_id", "to_id"]].to_numpy())),
            {("hub", "1"), ("1", "hub")},
        )
        self.assertTrue((normalized["travel_minutes"] == 12).all())

        conflicting = pd.DataFrame([
            {"from_id": "hub", "to_id": "1", "travel_minutes": 12},
            {"from_id": "1", "to_id": "hub", "travel_minutes": 13},
        ])
        with self.assertRaisesRegex(ValueError, "conflicting reverse travel times"):
            normalize_travel_time_matrix(conflicting, undirected=True)

    def test_matrix_trip_uses_supplied_minutes_and_returns_to_hub(self):
        plan = pd.DataFrame({
            "site_id": [1, 2],
            "survey_area_id": ["north", "south"],
            "latitude": [35.0, 35.1],
            "longitude": [139.0, 139.1],
        })
        matrix = pd.DataFrame([
            {"from_id": "hub", "to_id": 1, "travel_minutes": 30, "mode": "road"},
            {"from_id": 1, "to_id": 2, "travel_minutes": 20, "mode": "trail"},
            {"from_id": 2, "to_id": "hub", "travel_minutes": 40, "mode": "ferry"},
            {"from_id": 1, "to_id": "hub", "travel_minutes": 30, "mode": "road"},
            {"from_id": "hub", "to_id": 2, "travel_minutes": 40, "mode": "ferry"},
            {"from_id": 2, "to_id": 1, "travel_minutes": 20, "mode": "trail"},
        ])
        result = estimate_matrix_trip(
            plan,
            35.0,
            139.0,
            survey_protocol=TEST_PROTOCOL,
            target_days=1,
            travel_matrix=matrix,
            hub_id="hub",
        )
        self.assertTrue(result["fits_target_days"])
        self.assertEqual(result["route_order_site_ids"], ["1", "2"])
        self.assertEqual(result["total_travel_minutes"], 90.0)
        self.assertEqual(result["estimated_days"], 1)
        self.assertEqual(result["day_schedules"][0]["survey_area_ids"], ["north", "south"])
        self.assertEqual(result["day_schedules"][0]["modes"], ["road", "trail", "ferry"])
        self.assertFalse(result["hub_coordinates_used_for_routing"])

    def test_largest_feasible_prefix_stops_before_unreachable_site(self):
        ordered = pd.DataFrame({
            "site_id": [1, 2],
            "latitude": [35.0, 35.1],
            "longitude": [139.0, 139.1],
        })
        matrix = pd.DataFrame([
            {"from_id": "hub", "to_id": 1, "travel_minutes": 10},
            {"from_id": 1, "to_id": "hub", "travel_minutes": 10},
            {"from_id": "hub", "to_id": 2, "travel_minutes": 10},
        ])
        estimator = partial(
            estimate_matrix_trip,
            travel_matrix=matrix,
            hub_id="hub",
        )
        selected, audit, prefix = select_largest_feasible_prefix(
            ordered,
            hub_latitude=35.0,
            hub_longitude=139.0,
            target_days=1,
            trip_estimator=estimator,
            survey_protocol=TEST_PROTOCOL,
        )
        self.assertEqual(selected["site_id"].tolist(), [1])
        self.assertEqual(audit.selected_count, 1)
        self.assertEqual(prefix["fits_target_days"].tolist(), [True, False])
        self.assertEqual(prefix.iloc[1]["unreachable_site_ids"], ["2"])

    def test_budget_cli_accepts_multi_area_only_with_explicit_matrix(self):
        candidates = pd.DataFrame({
            "site_id": ["001", "002"],
            "survey_area_id": ["island-a", "island-b"],
            "latitude": [35.0, 34.0],
            "longitude": [139.0, 138.0],
        })
        matrix = pd.DataFrame([
            {"from_id": "port", "to_id": "001", "travel_minutes": 10, "mode": "road"},
            {"from_id": "port", "to_id": "002", "travel_minutes": 20, "mode": "ferry"},
        ])
        with tempfile.TemporaryDirectory() as temporary_directory:
            workdir = Path(temporary_directory)
            input_csv = workdir / "candidates.csv"
            matrix_csv = workdir / "travel.csv"
            output_csv = workdir / "selected.csv"
            summary_json = workdir / "summary.json"
            prefix_csv = workdir / "prefix.csv"
            candidates.to_csv(input_csv, index=False)
            matrix.to_csv(matrix_csv, index=False)

            exit_code = main([
                "budget",
                "--input", str(input_csv),
                "--output", str(output_csv),
                "--summary-json", str(summary_json),
                "--prefix-audit", str(prefix_csv),
                "--hub-latitude", "35.0",
                "--hub-longitude", "139.0",
                "--hub-id", "port",
                "--days", "2",
                "--taxon-profile", "plant",
                "--coverage-radius-km", "1",
                "--max-sites", "2",
                "--travel-matrix", str(matrix_csv),
                "--undirected-travel-matrix",
            ])
            selected = pd.read_csv(output_csv, dtype={"site_id": "string"})
            summary = json.loads(summary_json.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(selected), 2)
        self.assertEqual(selected["site_id"].tolist(), ["001", "002"])
        self.assertEqual(selected["coverage_rank"].tolist(), [1, 2])
        self.assertEqual(summary["routing_mode"], "external_travel_time_matrix")
        self.assertEqual(summary["survey_area_count"], 2)
        self.assertEqual(summary["coverage_selection"]["group_column"], "survey_area_id")
        self.assertTrue(summary["travel_matrix_undirected"])
        self.assertEqual(summary["operational_budget"]["selected_count"], 2)


if __name__ == "__main__":
    unittest.main()
