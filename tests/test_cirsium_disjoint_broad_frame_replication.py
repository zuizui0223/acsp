from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

from acsp.discovery import complete_link_clusters
import run_cirsium_disjoint_broad_frame_replication_v1 as outcome


class Audit:
    def as_dict(self):
        return {"provider_id": "GBIF", "year_from": 2021, "year_to": 2025, "field_outcomes_used": False}


class DisjointBroadFrameOutcomeTests(unittest.TestCase):
    def _base_docs(self):
        contract = {
            "cohort_selection": {"units": [{"unit_id": "U1", "species": "Cirsium test", "allowed_fixed_regions": ["shikoku"]}]},
            "primary_endpoint": {"replication_support_rule": "test rule"},
            "outcome": {
                "country": "JP",
                "period": [2021, 2025],
                "coordinate_uncertainty_m_max": 1000,
                "recovery_radii_km": [0.5, 1.0],
                "primary_recovery_radius_km": 1.0,
            },
        }
        preflight = {
            "recent_outcomes_fetched": False,
            "units": [{"unit_id": "U1", "species": "Cirsium test", "status": "PREOUTCOME_CANDIDATE_UNIVERSES_FROZEN"}],
        }
        gate = {
            "status": "PREOUTCOME_FRAMES_FROZEN_OUTCOME_EXECUTION_AUTHORIZED",
            "recent_outcomes_fetched_at_gate_creation": False,
            "unit_execution": [{"unit_id": "U1", "species": "Cirsium test", "recent_fetch_authorized": True}],
        }
        return contract, preflight, gate

    def test_fingerprint_drift_aborts_before_any_recent_fetch(self) -> None:
        contract, preflight, gate = self._base_docs()
        with patch.object(outcome, "reconstruct_frozen_unit", side_effect=RuntimeError("PREOUTCOME_FINGERPRINT_DRIFT:test")), \
             patch.object(outcome, "fetch_and_score_recent_unit") as recent:
            with self.assertRaisesRegex(RuntimeError, "PREOUTCOME_FINGERPRINT_DRIFT"):
                outcome.run_documents(contract, preflight, gate)
            recent.assert_not_called()

    def test_no_historical_anchor_unit_never_receives_recent_fetch(self) -> None:
        contract = {
            "cohort_selection": {"units": [{"unit_id": "U0", "species": "Cirsium zero", "allowed_fixed_regions": ["shikoku"]}]},
            "primary_endpoint": {"replication_support_rule": "test rule"},
            "outcome": {},
        }
        preflight = {
            "recent_outcomes_fetched": False,
            "units": [{"unit_id": "U0", "species": "Cirsium zero", "status": "NO_HISTORICAL_ANCHOR"}],
        }
        gate = {
            "status": "PREOUTCOME_FRAMES_FROZEN_OUTCOME_EXECUTION_AUTHORIZED",
            "recent_outcomes_fetched_at_gate_creation": False,
            "unit_execution": [{"unit_id": "U0", "species": "Cirsium zero", "recent_fetch_authorized": False}],
        }
        with patch.object(outcome, "fetch_and_score_recent_unit") as recent:
            summary, metrics = outcome.run_documents(contract, preflight, gate)
        recent.assert_not_called()
        self.assertTrue(metrics.empty)
        self.assertEqual(summary["units"][0]["status"], "NOT_EVALUABLE_NO_HISTORICAL_ANCHOR")
        self.assertFalse(summary["units"][0]["recent_fetch_performed"])
        self.assertFalse(summary["replication_supported"])

    def test_recent_precision_filter_novelty_and_ceiling_scoring(self) -> None:
        historical = pd.DataFrame(
            [{"occurrence_id": "h", "latitude": 33.50, "longitude": 133.50}]
        )
        historical_clusters = complete_link_clusters(historical, radius_km=0.5)
        state = outcome.FrozenUnitState(
            unit_id="U1",
            species="Cirsium test",
            region={"region_id": "shikoku", "west": 132.5, "south": 32.7, "east": 134.5, "north": 34.5},
            historical=historical,
            historical_clusters=historical_clusters,
            anchors=pd.DataFrame(),
            candidate_universes={
                "BROAD_LAND": pd.DataFrame([
                    {"candidate_cell_id": "broad-hit", "latitude": 33.80, "longitude": 133.80},
                ]),
                "LOCAL_5KM_LAND": pd.DataFrame([
                    {"candidate_cell_id": "local-old", "latitude": 33.50, "longitude": 133.50},
                ]),
            },
            metric_crs="EPSG:32653",
        )
        recent = pd.DataFrame(
            [
                # exact-enough old population; not novel
                {"occurrence_id": "r-old", "latitude": 33.50, "longitude": 133.50, "event_year": 2023, "coordinate_uncertainty_m": 100.0, "provider_id": "GBIF"},
                # exact-enough novel population; broad candidate hits it
                {"occurrence_id": "r-new", "latitude": 33.80, "longitude": 133.80, "event_year": 2023, "coordinate_uncertainty_m": 100.0, "provider_id": "GBIF"},
                # missing uncertainty: must not enter evaluation
                {"occurrence_id": "r-missing", "latitude": 33.90, "longitude": 133.90, "event_year": 2023, "coordinate_uncertainty_m": None, "provider_id": "GBIF"},
                # too coarse: must not enter evaluation
                {"occurrence_id": "r-coarse", "latitude": 34.00, "longitude": 134.00, "event_year": 2023, "coordinate_uncertainty_m": 1001.0, "provider_id": "GBIF"},
            ]
        )
        contract = {
            "outcome": {
                "country": "JP",
                "period": [2021, 2025],
                "coordinate_uncertainty_m_max": 1000,
                "recovery_radii_km": [0.5, 1.0],
                "primary_recovery_radius_km": 1.0,
            }
        }
        with patch.object(outcome, "fetch_gbif_occurrence_evidence", return_value=(recent, Audit())):
            result, rows = outcome.fetch_and_score_recent_unit(state, contract=contract)
        self.assertEqual(result["status"], "TEMPORALLY_EVALUABLE")
        self.assertEqual(result["recent_raw_records_countrywide"], 4)
        self.assertEqual(result["recent_strict_records_countrywide"], 2)
        self.assertEqual(result["recent_population_count"], 2)
        self.assertEqual(result["novel_population_count"], 1)
        self.assertEqual(result["broad_land_recall"], 1.0)
        self.assertEqual(result["local_5km_land_recall"], 0.0)
        self.assertEqual(result["broad_minus_local_5km_recall"], 1.0)
        self.assertTrue(result["primary_positive"])
        self.assertEqual(len(rows), 4)

    def test_two_positive_evaluable_units_are_required_for_support(self) -> None:
        contract = {
            "cohort_selection": {"units": [
                {"unit_id": "U1", "species": "A"},
                {"unit_id": "U2", "species": "B"},
                {"unit_id": "U0", "species": "C"},
            ]},
            "primary_endpoint": {"replication_support_rule": "two positive"},
        }
        preflight = {
            "recent_outcomes_fetched": False,
            "units": [
                {"unit_id": "U1", "status": "PREOUTCOME_CANDIDATE_UNIVERSES_FROZEN"},
                {"unit_id": "U2", "status": "PREOUTCOME_CANDIDATE_UNIVERSES_FROZEN"},
                {"unit_id": "U0", "status": "NO_HISTORICAL_ANCHOR"},
            ],
        }
        gate = {
            "status": "PREOUTCOME_FRAMES_FROZEN_OUTCOME_EXECUTION_AUTHORIZED",
            "recent_outcomes_fetched_at_gate_creation": False,
            "unit_execution": [
                {"unit_id": "U1", "recent_fetch_authorized": True},
                {"unit_id": "U2", "recent_fetch_authorized": True},
                {"unit_id": "U0", "recent_fetch_authorized": False},
            ],
        }
        dummy = outcome.FrozenUnitState("x", "x", {}, pd.DataFrame(), [], pd.DataFrame(), {}, "EPSG:4326")
        states = {"U1": dummy, "U2": dummy}
        retained = [{"unit_id": "U0", "species": "C", "status": "NOT_EVALUABLE_NO_HISTORICAL_ANCHOR", "recent_fetch_performed": False, "historical_population_count": 0}]
        scored = {
            "U1": {"unit_id": "U1", "species": "A", "status": "TEMPORALLY_EVALUABLE", "primary_positive": True},
            "U2": {"unit_id": "U2", "species": "B", "status": "TEMPORALLY_EVALUABLE", "primary_positive": True},
        }
        with patch.object(outcome, "verify_all_preoutcome_states", return_value=(states, retained)), \
             patch.object(outcome, "fetch_and_score_recent_unit", side_effect=lambda state, contract: (scored[state.unit_id], [])):
            # use per-ID states so side effect can resolve keys
            states["U1"] = outcome.FrozenUnitState("U1", "A", {}, pd.DataFrame(), [], pd.DataFrame(), {}, "EPSG:4326")
            states["U2"] = outcome.FrozenUnitState("U2", "B", {}, pd.DataFrame(), [], pd.DataFrame(), {}, "EPSG:4326")
            summary, _ = outcome.run_documents(contract, preflight, gate)
        self.assertTrue(summary["replication_supported"])
        self.assertEqual(summary["decision"], "REPLICATION_SUPPORTED")
        self.assertEqual(summary["temporally_evaluable_units"], 2)
        self.assertEqual(summary["primary_positive_units"], 2)


if __name__ == "__main__":
    unittest.main()
