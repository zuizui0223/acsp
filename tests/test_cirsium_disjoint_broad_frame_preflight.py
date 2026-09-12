from __future__ import annotations

from dataclasses import dataclass
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

import prepare_cirsium_disjoint_broad_frame_replication_v1 as preflight


class DisjointBroadFramePreflightTests(unittest.TestCase):
    def test_region_choice_uses_population_clusters_not_raw_record_density(self) -> None:
        rows = []
        # Five nearly duplicate records in Shikoku collapse to one population.
        for index in range(5):
            rows.append(
                {
                    "occurrence_id": f"s{index}",
                    "latitude": 33.5 + index * 0.00005,
                    "longitude": 133.5,
                    "event_year": 2015,
                    "coordinate_uncertainty_m": 100.0,
                    "provider_id": "GBIF",
                }
            )
        # Two separated northern-Kyushu records are two populations.
        rows.extend(
            [
                {"occurrence_id": "k1", "latitude": 33.0, "longitude": 130.0, "event_year": 2015, "coordinate_uncertainty_m": 100.0, "provider_id": "GBIF"},
                {"occurrence_id": "k2", "latitude": 33.6, "longitude": 130.8, "event_year": 2015, "coordinate_uncertainty_m": 100.0, "provider_id": "GBIF"},
            ]
        )
        frame = pd.DataFrame(rows)
        region, selected, diagnostics = preflight._choose_training_region(
            frame,
            allowed_region_ids=["shikoku", "northern-kyushu"],
            cluster_radius_km=0.5,
        )
        self.assertEqual(region["region_id"], "northern-kyushu")
        self.assertEqual(len(selected), 2)
        lookup = {row["region_id"]: row for row in diagnostics}
        self.assertEqual(lookup["shikoku"]["historical_population_clusters"], 1)
        self.assertEqual(lookup["northern-kyushu"]["historical_population_clusters"], 2)

    def test_missing_or_coarse_uncertainty_never_becomes_exact_training_evidence(self) -> None:
        frame = pd.DataFrame(
            [
                {"occurrence_id": "exact", "coordinate_uncertainty_m": 999.0},
                {"occurrence_id": "missing", "coordinate_uncertainty_m": None},
                {"occurrence_id": "coarse", "coordinate_uncertainty_m": 1001.0},
            ]
        )
        strict = preflight._strict_exact(frame, 1000.0)
        self.assertEqual(strict["occurrence_id"].tolist(), ["exact"])

    def test_prepare_unit_fetches_historical_period_only(self) -> None:
        historical = pd.DataFrame(
            [
                {"occurrence_id": "h1", "latitude": 33.5, "longitude": 133.5, "event_year": 2010, "coordinate_uncertainty_m": 100.0, "provider_id": "GBIF"}
            ]
        )

        class Audit:
            def as_dict(self):
                return {"provider_id": "GBIF", "year_from": 2000, "year_to": 2020}

        tiny_grid = pd.DataFrame(
            [
                {"candidate_cell_id": "a", "latitude": 33.51, "longitude": 133.51, "grid_row": 0, "grid_col": 0, "nearest_anchor_km": 1.0},
                {"candidate_cell_id": "b", "latitude": 33.60, "longitude": 133.60, "grid_row": 1, "grid_col": 1, "nearest_anchor_km": 15.0},
            ]
        )

        @dataclass(frozen=True)
        class BroadAudit:
            metric_crs: str = "EPSG:32653"
            candidate_count: int = 2
            grid_spacing_m: float = 1000.0
            bounds_wgs84: tuple[float, float, float, float] = (132.5, 32.7, 134.5, 34.5)
            field_outcomes_used: bool = False
            human_access_used: bool = False

        class WcAudit:
            source_tile_ids = ("N30E132", "N33E132")
            def as_dict(self):
                return {"provider_id": "ESA_WORLDCOVER", "release_id": "2021_v200", "field_outcomes_used": False}

        contract = {
            "historical_evidence": {"country": "JP", "period": [2000, 2020], "coordinate_uncertainty_m_max": 1000},
            "candidate_universes": {"grid_spacing_m": 1000, "known_exclusion_km": 0.5, "local_outer_radii_km": [2, 5, 10]},
        }
        unit = {"unit_id": "T", "species": "Cirsium test", "allowed_fixed_regions": ["shikoku"]}

        with patch.object(preflight, "fetch_gbif_occurrence_evidence", return_value=(historical, Audit())) as fetch, \
             patch.object(preflight, "build_rectangular_candidate_frame", return_value=(tiny_grid.drop(columns=["nearest_anchor_km"]), BroadAudit())), \
             patch.object(preflight, "attach_nearest_anchor_distance", return_value=tiny_grid), \
             patch.object(preflight, "retain_worldcover_land_points", return_value=(tiny_grid, WcAudit())):
            result = preflight._prepare_unit(unit, contract)

        self.assertEqual(result["status"], "PREOUTCOME_CANDIDATE_UNIVERSES_FROZEN")
        self.assertFalse(result["recent_outcomes_fetched"])
        fetch.assert_called_once()
        kwargs = fetch.call_args.kwargs
        self.assertEqual(kwargs["year_from"], 2000)
        self.assertEqual(kwargs["year_to"], 2020)
        self.assertNotIn(2021, kwargs.values())


if __name__ == "__main__":
    unittest.main()
