from __future__ import annotations

import sys
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

import run_japan_plant_broad_frame_confirmation_v4 as r


class JapanPlantBroadFrameConfirmationV4Tests(unittest.TestCase):
    def _protocol(self):
        return {
            "stage2_historical_qualification": {
                "country": "JP",
                "period": [2000, 2020],
                "coordinate_uncertainty_m_max": 1000,
            },
            "candidate_universes": {
                "grid_spacing_m": 1000,
                "known_exclusion_km": 0.5,
                "local_outer_radii_km": [2, 5, 10],
            },
            "outcome": {
                "country": "JP",
                "period": [2021, 2025],
                "coordinate_uncertainty_m_max": 1000,
                "recovery_radii_km": [0.5, 1.0],
                "primary_recovery_radius_km": 1.0,
            },
            "primary_endpoint": {
                "minimum_temporally_evaluable_taxa": 12,
                "minimum_fraction_evaluable_taxa_with_strictly_positive_difference": 0.5,
                "minimum_cluster_weighted_added_recall": 0.1,
            },
        }

    def _selected(self):
        rows = []
        for i in range(24):
            key = 1000 + i
            rows.append({
                "speciesKey": key,
                "scientific_name": f"Species {i}",
                "selected_region": {"region_id": "izu", "region_name": "Izu", "west": 138, "south": 33, "east": 140, "north": 35},
                "historical_evidence_sha256": f"h{i}",
                "population_anchor_sha256": f"a{i}",
                "worldcover_point_audit": {"sample_classification_sha256": f"w{i}"},
                "candidate_universes": {
                    lane: {"candidate_count": 10, "candidate_id_sha256": f"{lane}-{i}"}
                    for lane in ("BROAD_LAND", "LOCAL_2KM_LAND", "LOCAL_5KM_LAND", "LOCAL_10KM_LAND")
                },
            })
        return rows

    def test_aggregate_applies_all_three_frozen_gates(self):
        protocol = self._protocol()
        results = [
            {"speciesKey": 1000 + i, "status": "TEMPORALLY_EVALUABLE"}
            for i in range(12)
        ]
        rows = []
        for i in range(12):
            for lane, recovered in (("BROAD_LAND", 10), ("LOCAL_5KM_LAND", 5)):
                rows.append({
                    "speciesKey": 1000 + i,
                    "lane_id": lane,
                    "recovery_radius_km": 1.0,
                    "novel_population_count": 10,
                    "recovered_novel_populations": recovered,
                    "recall": recovered / 10,
                })
        out = r._aggregate(results, pd.DataFrame(rows), protocol)
        self.assertTrue(out["evaluable_gate_passed"])
        self.assertTrue(out["positive_fraction_gate_passed"])
        self.assertTrue(out["cluster_weighted_added_recall_gate_passed"])
        self.assertTrue(out["all_preregistered_gates_passed"])
        self.assertAlmostEqual(out["cluster_weighted_broad_minus_local5_added_recall"], 0.5)

    def test_all_24_reconstruct_before_first_heldout_score(self):
        protocol = self._protocol()
        preflight = {"selected_taxa": self._selected()}
        events = []

        def fake_reconstructor(unit, **kwargs):
            events.append(("reconstruct", unit["unit_id"]))
            return {"unit_id": unit["unit_id"]}

        def fake_scorer(state, **kwargs):
            events.append(("score", state["unit_id"]))
            key = int(state["unit_id"].split("_")[-1])
            metrics = []
            for lane, recovered in (
                ("BROAD_LAND", 10),
                ("LOCAL_2KM_LAND", 5),
                ("LOCAL_5KM_LAND", 5),
                ("LOCAL_10KM_LAND", 5),
            ):
                metrics.append({
                    "lane_id": lane,
                    "recovery_radius_km": 1.0,
                    "novel_population_count": 10,
                    "recovered_novel_populations": recovered,
                    "recall": recovered / 10,
                })
            return {"status": "TEMPORALLY_EVALUABLE", "recent_provider_audit": {"matched_usage_key": key}}, metrics

        with (
            patch.object(r, "verify_preoutcome_preflight", return_value=(protocol, preflight)),
            patch.object(r, "_sha256", return_value="synthetic"),
        ):
            summary, _ = r.run(Path("unused.json"), reconstructor=fake_reconstructor, scorer=fake_scorer)

        first_score = next(i for i, item in enumerate(events) if item[0] == "score")
        self.assertEqual(first_score, 24)
        self.assertEqual(sum(item[0] == "reconstruct" for item in events), 24)
        self.assertEqual(sum(item[0] == "score" for item in events), 24)
        self.assertTrue(summary["primary"]["all_preregistered_gates_passed"])
        self.assertFalse(summary["selector_evaluated"])
        self.assertFalse(summary["human_access_used"])


if __name__ == "__main__":
    unittest.main()
