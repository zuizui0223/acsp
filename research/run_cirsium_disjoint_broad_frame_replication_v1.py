#!/usr/bin/env python3
"""Run the preregistered disjoint Cirsium broad-frame replication.

The critical boundary is two-phase execution. Phase 1 reconstructs every
pre-outcome candidate universe authorized by the execution gate and verifies all
frozen fingerprints. Phase 2 fetches 2021-2025 outcomes only after *all* Phase 1
checks pass. DBR01 is retained as non-evaluable and never receives a recent fetch.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

from acsp.discovery import (
    attach_nearest_anchor_distance,
    build_rectangular_candidate_frame,
    cluster_medoid_table,
    cluster_min_distance_km,
    complete_link_clusters,
)
from acsp.discovery.providers import fetch_gbif_occurrence_evidence, retain_worldcover_land_points
from prepare_cirsium_disjoint_broad_frame_replication_v1 import (
    _choose_training_region,
    _hash_candidate_ids,
    _hash_rows,
    _inside_region,
    _strict_exact,
)

CONTRACT_PATH = ROOT / "validation" / "cirsium_disjoint_broad_frame_replication_v1.json"
PREFLIGHT_PATH = ROOT / "validation" / "cirsium_disjoint_broad_frame_replication_preflight_result_v1.json"
GATE_PATH = ROOT / "validation" / "cirsium_disjoint_broad_frame_replication_execution_gate_v1.json"


@dataclass
class FrozenUnitState:
    unit_id: str
    species: str
    region: dict[str, Any]
    historical: pd.DataFrame
    historical_clusters: list
    anchors: pd.DataFrame
    candidate_universes: dict[str, pd.DataFrame]
    metric_crs: str


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _unit_lookup(document: dict[str, Any], path: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    value: Any = document
    for key in path:
        value = value[key]
    return {str(row["unit_id"]): row for row in value}


def _assert_equal(actual: Any, expected: Any, message: str) -> None:
    if actual != expected:
        raise RuntimeError(f"PREOUTCOME_FINGERPRINT_DRIFT:{message}: expected={expected!r} actual={actual!r}")


def reconstruct_frozen_unit(
    unit: dict[str, Any],
    *,
    contract: dict[str, Any],
    preflight_unit: dict[str, Any],
    gate_unit: dict[str, Any],
) -> FrozenUnitState:
    """Rebuild and verify one frozen unit without touching recent outcomes."""
    unit_id = str(unit["unit_id"])
    species = str(unit["species"])
    _assert_equal(preflight_unit.get("status"), "PREOUTCOME_CANDIDATE_UNIVERSES_FROZEN", f"{unit_id} preflight status")
    _assert_equal(gate_unit.get("recent_fetch_authorized"), True, f"{unit_id} recent authorization")
    _assert_equal(str(gate_unit.get("species")), species, f"{unit_id} gate species")

    historical_cfg = contract["historical_evidence"]
    historical, _ = fetch_gbif_occurrence_evidence(
        species,
        country=str(historical_cfg["country"]),
        year_from=int(historical_cfg["period"][0]),
        year_to=int(historical_cfg["period"][1]),
        maximum_records=10000,
    )
    strict = _strict_exact(historical, float(historical_cfg["coordinate_uncertainty_m_max"]))
    region, selected_historical, _ = _choose_training_region(
        strict,
        allowed_region_ids=[str(value) for value in unit["allowed_fixed_regions"]],
        cluster_radius_km=0.5,
    )
    if region is None:
        raise RuntimeError(f"PREOUTCOME_FINGERPRINT_DRIFT:{unit_id} lost its historical region")

    expected_region = str(preflight_unit["selected_region"]["region_id"])
    _assert_equal(str(region["region_id"]), expected_region, f"{unit_id} selected region")
    _assert_equal(str(gate_unit.get("selected_region")), expected_region, f"{unit_id} gate region")

    historical_hash = _hash_rows(
        selected_historical,
        ["occurrence_id", "latitude", "longitude", "event_year", "coordinate_uncertainty_m"],
    )
    _assert_equal(historical_hash, str(preflight_unit["historical_evidence_sha256"]), f"{unit_id} historical evidence hash")
    _assert_equal(historical_hash, str(gate_unit["historical_evidence_sha256"]), f"{unit_id} gate historical hash")

    historical_clusters = complete_link_clusters(selected_historical, radius_km=0.5)
    anchors = cluster_medoid_table(historical_clusters, prefix=f"{unit_id}_H")
    anchor_hash = _hash_rows(anchors, ["occurrence_id", "latitude", "longitude", "cluster_size"])
    _assert_equal(anchor_hash, str(preflight_unit["population_anchor_sha256"]), f"{unit_id} anchor hash")
    _assert_equal(anchor_hash, str(gate_unit["population_anchor_sha256"]), f"{unit_id} gate anchor hash")

    universe_cfg = contract["candidate_universes"]
    bounds = (
        float(region["west"]),
        float(region["south"]),
        float(region["east"]),
        float(region["north"]),
    )
    broad_raw, broad_audit = build_rectangular_candidate_frame(
        bounds,
        grid_spacing_m=float(universe_cfg["grid_spacing_m"]),
        candidate_id_prefix=f"{unit_id}_{region['region_id']}_broad",
    )
    broad_raw = attach_nearest_anchor_distance(broad_raw, anchors)
    broad_raw = broad_raw.loc[
        pd.to_numeric(broad_raw["nearest_anchor_km"], errors="coerce").ge(float(universe_cfg["known_exclusion_km"]) - 1e-12)
    ].copy().reset_index(drop=True)
    broad_land, wc_audit = retain_worldcover_land_points(broad_raw)
    _assert_equal(
        str(wc_audit.sample_classification_sha256),
        str(preflight_unit["worldcover_point_audit"]["sample_classification_sha256"]),
        f"{unit_id} WorldCover classification hash",
    )
    _assert_equal(
        str(wc_audit.sample_classification_sha256),
        str(gate_unit["worldcover_sample_sha256"]),
        f"{unit_id} gate WorldCover hash",
    )

    nearest = pd.to_numeric(broad_land["nearest_anchor_km"], errors="coerce")
    lanes: dict[str, pd.DataFrame] = {"BROAD_LAND": broad_land}
    for radius in universe_cfg["local_outer_radii_km"]:
        lanes[f"LOCAL_{int(radius)}KM_LAND"] = broad_land.loc[
            nearest.le(float(radius) + 1e-12)
        ].copy().reset_index(drop=True)

    expected_lanes = preflight_unit["candidate_universes"]
    _assert_equal(set(lanes), set(expected_lanes), f"{unit_id} candidate lane names")
    for lane_id, frame in lanes.items():
        expected = expected_lanes[lane_id]
        _assert_equal(int(len(frame)), int(expected["candidate_count"]), f"{unit_id} {lane_id} candidate count")
        _assert_equal(_hash_candidate_ids(frame), str(expected["candidate_id_sha256"]), f"{unit_id} {lane_id} candidate hash")

    return FrozenUnitState(
        unit_id=unit_id,
        species=species,
        region=region,
        historical=selected_historical,
        historical_clusters=historical_clusters,
        anchors=anchors,
        candidate_universes=lanes,
        metric_crs=str(broad_audit.metric_crs),
    )


def verify_all_preoutcome_states(
    contract: dict[str, Any],
    preflight: dict[str, Any],
    gate: dict[str, Any],
) -> tuple[dict[str, FrozenUnitState], list[dict[str, Any]]]:
    """Verify every authorized frozen unit before any recent fetch is possible."""
    _assert_equal(gate.get("status"), "PREOUTCOME_FRAMES_FROZEN_OUTCOME_EXECUTION_AUTHORIZED", "execution gate status")
    _assert_equal(gate.get("recent_outcomes_fetched_at_gate_creation"), False, "gate recent boundary")
    _assert_equal(preflight.get("recent_outcomes_fetched"), False, "preflight recent boundary")

    contract_units = _unit_lookup(contract, ("cohort_selection", "units"))
    preflight_units = _unit_lookup(preflight, ("units",))
    gate_units = _unit_lookup(gate, ("unit_execution",))
    _assert_equal(set(contract_units), set(preflight_units), "contract/preflight unit IDs")
    _assert_equal(set(contract_units), set(gate_units), "contract/gate unit IDs")

    states: dict[str, FrozenUnitState] = {}
    retained_non_evaluable: list[dict[str, Any]] = []
    for unit_id in contract_units:
        unit = contract_units[unit_id]
        frozen = preflight_units[unit_id]
        gate_unit = gate_units[unit_id]
        if frozen.get("status") == "NO_HISTORICAL_ANCHOR":
            _assert_equal(gate_unit.get("recent_fetch_authorized"), False, f"{unit_id} no-anchor fetch authorization")
            retained_non_evaluable.append(
                {
                    "unit_id": unit_id,
                    "species": str(unit["species"]),
                    "status": "NOT_EVALUABLE_NO_HISTORICAL_ANCHOR",
                    "recent_fetch_performed": False,
                    "historical_population_count": 0,
                }
            )
            continue
        states[unit_id] = reconstruct_frozen_unit(
            unit,
            contract=contract,
            preflight_unit=frozen,
            gate_unit=gate_unit,
        )
    return states, retained_non_evaluable


def _novel_recent_clusters(recent: pd.DataFrame, historical_clusters: list) -> list:
    recent_clusters = complete_link_clusters(recent, radius_km=0.5)
    novel = []
    for cluster in recent_clusters:
        if not historical_clusters or min(
            cluster_min_distance_km(cluster, prior) for prior in historical_clusters
        ) > 0.5 + 1e-12:
            novel.append(cluster)
    return novel


def _nearest_candidate_distances_km(
    candidate_frame: pd.DataFrame,
    clusters: list,
    *,
    metric_crs: str,
) -> list[float]:
    if not clusters:
        return []
    if candidate_frame.empty:
        return [float("inf")] * len(clusters)
    transformer = Transformer.from_crs("EPSG:4326", metric_crs, always_xy=True)
    cx, cy = transformer.transform(
        candidate_frame["longitude"].to_numpy(float),
        candidate_frame["latitude"].to_numpy(float),
    )
    tree = cKDTree(np.column_stack([cx, cy]))
    distances: list[float] = []
    for cluster in clusters:
        lon = np.asarray([member[1] for member in cluster.members], dtype=float)
        lat = np.asarray([member[0] for member in cluster.members], dtype=float)
        x, y = transformer.transform(lon, lat)
        value, _ = tree.query(np.column_stack([x, y]), k=1)
        distances.append(float(np.min(np.asarray(value, dtype=float))) / 1000.0)
    return distances


def _lane_metrics(
    lane_id: str,
    frame: pd.DataFrame,
    clusters: list,
    *,
    metric_crs: str,
    recovery_radii_km: list[float],
) -> list[dict[str, Any]]:
    nearest = _nearest_candidate_distances_km(frame, clusters, metric_crs=metric_crs)
    rows: list[dict[str, Any]] = []
    for radius in recovery_radii_km:
        recovered = int(sum(value <= float(radius) + 1e-12 for value in nearest))
        total = int(len(clusters))
        rows.append(
            {
                "lane_id": lane_id,
                "candidate_count": int(len(frame)),
                "recovery_radius_km": float(radius),
                "novel_population_count": total,
                "recovered_novel_populations": recovered,
                "recall": 0.0 if total == 0 else float(recovered / total),
            }
        )
    return rows


def fetch_and_score_recent_unit(
    state: FrozenUnitState,
    *,
    contract: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Open and score recent outcomes for one already-verified frozen unit."""
    outcome_cfg = contract["outcome"]
    recent_raw, recent_audit = fetch_gbif_occurrence_evidence(
        state.species,
        country=str(outcome_cfg["country"]),
        year_from=int(outcome_cfg["period"][0]),
        year_to=int(outcome_cfg["period"][1]),
        maximum_records=10000,
    )
    recent_strict = _strict_exact(recent_raw, float(outcome_cfg["coordinate_uncertainty_m_max"]))
    recent_region = _inside_region(recent_strict, state.region)
    recent_clusters = complete_link_clusters(recent_region, radius_km=0.5)
    novel = _novel_recent_clusters(recent_region, state.historical_clusters)

    if not recent_clusters:
        return (
            {
                "unit_id": state.unit_id,
                "species": state.species,
                "status": "NOT_EVALUABLE_NO_STRICT_RECENT_POPULATION",
                "recent_fetch_performed": True,
                "recent_raw_records_countrywide": int(len(recent_raw)),
                "recent_strict_records_countrywide": int(len(recent_strict)),
                "recent_strict_records_selected_region": int(len(recent_region)),
                "recent_population_count": 0,
                "novel_population_count": 0,
                "recent_provider_audit": recent_audit.as_dict(),
            },
            [],
        )
    if not novel:
        return (
            {
                "unit_id": state.unit_id,
                "species": state.species,
                "status": "NOT_EVALUABLE_NO_NOVEL_RECENT_POPULATION",
                "recent_fetch_performed": True,
                "recent_raw_records_countrywide": int(len(recent_raw)),
                "recent_strict_records_countrywide": int(len(recent_strict)),
                "recent_strict_records_selected_region": int(len(recent_region)),
                "recent_population_count": int(len(recent_clusters)),
                "novel_population_count": 0,
                "recent_provider_audit": recent_audit.as_dict(),
            },
            [],
        )

    radii = [float(value) for value in outcome_cfg["recovery_radii_km"]]
    metric_rows: list[dict[str, Any]] = []
    for lane_id, frame in state.candidate_universes.items():
        for row in _lane_metrics(
            lane_id,
            frame,
            novel,
            metric_crs=state.metric_crs,
            recovery_radii_km=radii,
        ):
            metric_rows.append({"unit_id": state.unit_id, "species": state.species, **row})

    metric_frame = pd.DataFrame(metric_rows)
    primary_radius = float(outcome_cfg["primary_recovery_radius_km"])
    primary = metric_frame.loc[np.isclose(metric_frame["recovery_radius_km"], primary_radius)].set_index("lane_id")
    broad_recall = float(primary.loc["BROAD_LAND", "recall"])
    local5_recall = float(primary.loc["LOCAL_5KM_LAND", "recall"])
    contrast = float(broad_recall - local5_recall)
    return (
        {
            "unit_id": state.unit_id,
            "species": state.species,
            "status": "TEMPORALLY_EVALUABLE",
            "recent_fetch_performed": True,
            "selected_region": str(state.region["region_id"]),
            "historical_population_count": int(len(state.historical_clusters)),
            "recent_raw_records_countrywide": int(len(recent_raw)),
            "recent_strict_records_countrywide": int(len(recent_strict)),
            "recent_strict_records_selected_region": int(len(recent_region)),
            "recent_population_count": int(len(recent_clusters)),
            "novel_population_count": int(len(novel)),
            "primary_recovery_radius_km": primary_radius,
            "broad_land_recall": broad_recall,
            "local_5km_land_recall": local5_recall,
            "broad_minus_local_5km_recall": contrast,
            "primary_positive": bool(contrast > 0.0),
            "recent_provider_audit": recent_audit.as_dict(),
        },
        metric_rows,
    )


def run_documents(
    contract: dict[str, Any],
    preflight: dict[str, Any],
    gate: dict[str, Any],
) -> tuple[dict[str, Any], pd.DataFrame]:
    # PHASE 1: all fingerprints must pass before PHASE 2 starts.
    states, non_evaluable = verify_all_preoutcome_states(contract, preflight, gate)

    # PHASE 2: opening recent outcomes is now authorized only for verified units.
    unit_results = list(non_evaluable)
    metric_rows: list[dict[str, Any]] = []
    for unit_id in [str(row["unit_id"]) for row in contract["cohort_selection"]["units"]]:
        if unit_id not in states:
            continue
        result, rows = fetch_and_score_recent_unit(states[unit_id], contract=contract)
        unit_results.append(result)
        metric_rows.extend(rows)

    by_id = {str(row["unit_id"]): row for row in unit_results}
    ordered_results = [by_id[str(row["unit_id"])] for row in contract["cohort_selection"]["units"]]
    evaluable = [row for row in ordered_results if row["status"] == "TEMPORALLY_EVALUABLE"]
    positive = [row for row in evaluable if bool(row.get("primary_positive"))]
    required_evaluable = 2
    required_positive = 2
    supported = len(evaluable) >= required_evaluable and len(positive) >= required_positive

    summary = {
        "schema_version": "cirsium-disjoint-broad-frame-replication-result-v1",
        "status": "DISJOINT_BROAD_FRAME_REPLICATION_COMPLETE",
        "source_contract": str(CONTRACT_PATH.relative_to(ROOT)),
        "preflight_result": str(PREFLIGHT_PATH.relative_to(ROOT)),
        "execution_gate": str(GATE_PATH.relative_to(ROOT)),
        "validated_product_changed": False,
        "selector_evaluated": False,
        "human_access_used": False,
        "frozen_unit_count": int(len(contract["cohort_selection"]["units"])),
        "temporally_evaluable_units": int(len(evaluable)),
        "primary_positive_units": int(len(positive)),
        "replication_support_rule": contract["primary_endpoint"]["replication_support_rule"],
        "replication_supported": bool(supported),
        "decision": "REPLICATION_SUPPORTED" if supported else "PREREGISTERED_REPLICATION_GATE_FAILED",
        "units": ordered_results,
        "claim_boundary": "Full-frame reachability diagnoses whether a frozen candidate universe can represent later populations. It is not occupancy probability, field efficiency, route optimization, or selector validation."
    }
    return summary, pd.DataFrame(metric_rows)


def run() -> tuple[dict[str, Any], pd.DataFrame]:
    return run_documents(_load_json(CONTRACT_PATH), _load_json(PREFLIGHT_PATH), _load_json(GATE_PATH))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    summary, metrics = run()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    metrics.to_csv(args.out_dir / "ceiling_metrics.csv", index=False)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
