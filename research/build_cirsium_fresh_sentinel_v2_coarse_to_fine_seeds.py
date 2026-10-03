#!/usr/bin/env python3
"""Compress fresh-SENTINEL v2 coarse candidates into automatic fine-expansion seeds.

No user budget or Top-k is used. Source-ready candidates are scanned in their
already-frozen ecological order and retained as seeds only when they add new
5-km coverage. Source-indeterminate candidates are compressed independently by
geometry-only greedy set cover. Both lanes continue until every candidate in
that lane is covered by at least one seed.

The 5-km scale is inherited mechanically from the already-frozen coarse coverage
scale. Seeds are fine-frame centers only, not exact field sites or occupancy claims.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from research.build_cirsium_fresh_sentinel_public_broad_frame_v2 import (
    build_fresh_sentinel_v2_outer_frame,
)
from acsp.global_geometry import fetch_geoboundaries_country_geometry

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_v2_coarse_to_fine_seed_v1.json"
UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
READY = "SOURCE_READY_FOR_FAMILY_COARSE_STAGE"
INDETERMINATE = "SOURCE_INDETERMINATE_RETAIN"
EXPECTED_CANDIDATES = 39200
EARTH_RADIUS_KM = 6371.0088


def _contract() -> dict[str, Any]:
    value = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if value.get("status") != "FROZEN_BEFORE_COARSE_TO_FINE_SEED_EXECUTION":
        raise ValueError("coarse-to-fine seed contract is not frozen")
    radius = float(value.get("seed_footprint", {}).get("radius_km", -1))
    if radius != 5.0:
        raise ValueError("frozen seed footprint radius drifted")
    if value["source_ready_lane"].get("top_k_used") is not False:
        raise ValueError("Top-k must remain forbidden")
    if value["source_ready_lane"].get("budget_used") is not False:
        raise ValueError("budget must remain forbidden")
    return value


def _stable_hash(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _unit_vectors(latitude: np.ndarray, longitude: np.ndarray) -> np.ndarray:
    lat = np.radians(np.asarray(latitude, dtype=float))
    lon = np.radians(np.asarray(longitude, dtype=float))
    cos_lat = np.cos(lat)
    return np.column_stack((cos_lat * np.cos(lon), cos_lat * np.sin(lon), np.sin(lat)))


def _chord_radius(radius_km: float) -> float:
    angle = float(radius_km) / EARTH_RADIUS_KM
    return float(2.0 * np.sin(angle / 2.0))


def _neighbors(frame: pd.DataFrame, radius_km: float) -> list[list[int]]:
    xyz = _unit_vectors(
        pd.to_numeric(frame["latitude"], errors="raise").to_numpy(float),
        pd.to_numeric(frame["longitude"], errors="raise").to_numpy(float),
    )
    tree = cKDTree(xyz)
    return tree.query_ball_point(xyz, r=_chord_radius(radius_km))


def _validate_order_with_outer(order: pd.DataFrame, outer: pd.DataFrame, unit: str) -> pd.DataFrame:
    required = {"candidate_cell_id", "source_state", "coarse_evidence_rank"}
    missing = sorted(required.difference(order.columns))
    if missing:
        raise ValueError(f"{unit} coarse order missing columns: {missing}")
    ids = order["candidate_cell_id"].astype(str)
    if ids.duplicated().any():
        raise ValueError(f"{unit} coarse order candidate IDs are not unique")
    outer_ids = outer["candidate_cell_id"].astype(str)
    if set(ids) != set(outer_ids):
        raise ValueError(f"{unit} coarse order candidate set differs from frozen outer frame")
    coords = outer.set_index(outer_ids)[["latitude", "longitude", "regional_tile_id"]]
    merged = order.copy()
    merged.index = ids
    merged = merged.join(coords, how="left", rsuffix="_outer").reset_index(drop=True)
    if merged[["latitude", "longitude"]].isna().any().any():
        raise ValueError(f"{unit} failed to restore frozen outer-frame coordinates")
    states = set(merged["source_state"].astype(str))
    if not states.issubset({READY, INDETERMINATE}):
        raise ValueError(f"{unit} contains unknown source state: {states}")
    ready = merged["source_state"].astype(str).eq(READY)
    ranks = pd.to_numeric(merged.loc[ready, "coarse_evidence_rank"], errors="raise").astype(int)
    if sorted(ranks.tolist()) != list(range(1, len(ranks) + 1)):
        raise ValueError(f"{unit} source-ready coarse rank is not a complete 1..N order")
    if merged.loc[~ready, "coarse_evidence_rank"].notna().any():
        raise ValueError(f"{unit} source-indeterminate candidates must not have ecological rank")
    return merged


def _ordered_incremental_cover(lane: pd.DataFrame, radius_km: float) -> tuple[list[int], np.ndarray]:
    if lane.empty:
        return [], np.zeros(0, dtype=bool)
    neigh = _neighbors(lane, radius_km)
    covered = np.zeros(len(lane), dtype=bool)
    selected: list[int] = []
    for idx in range(len(lane)):
        adds = any(not covered[j] for j in neigh[idx])
        if not adds:
            continue
        selected.append(idx)
        covered[np.asarray(neigh[idx], dtype=int)] = True
        if covered.all():
            break
    if not covered.all():
        raise AssertionError("source-ready ordered coverage did not cover its complete lane")
    return selected, covered


def _geometry_only_greedy_cover(lane: pd.DataFrame, radius_km: float) -> tuple[list[int], np.ndarray]:
    if lane.empty:
        return [], np.zeros(0, dtype=bool)
    neigh = _neighbors(lane, radius_km)
    covered = np.zeros(len(lane), dtype=bool)
    selected_mask = np.zeros(len(lane), dtype=bool)
    stable = np.asarray([_stable_hash(value) for value in lane["candidate_cell_id"].astype(str)], dtype=object)
    selected: list[int] = []

    while not covered.all():
        best_idx: int | None = None
        best_gain = -1
        best_hash = ""
        for idx, indices in enumerate(neigh):
            if selected_mask[idx]:
                continue
            gain = int(np.count_nonzero(~covered[np.asarray(indices, dtype=int)]))
            if gain <= 0:
                continue
            h = str(stable[idx])
            if gain > best_gain or (gain == best_gain and (best_idx is None or h < best_hash)):
                best_idx = idx
                best_gain = gain
                best_hash = h
        if best_idx is None:
            raise AssertionError("geometry-only set cover stalled before complete lane coverage")
        selected.append(best_idx)
        selected_mask[best_idx] = True
        covered[np.asarray(neigh[best_idx], dtype=int)] = True
    return selected, covered


def build_unit_seed_plan(
    order: pd.DataFrame,
    outer: pd.DataFrame,
    unit: str,
    *,
    radius_km: float = 5.0,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    work = _validate_order_with_outer(order, outer, unit)
    ready = work.loc[work["source_state"].astype(str).eq(READY)].copy()
    ready = ready.sort_values("coarse_evidence_rank", kind="mergesort").reset_index(drop=True)
    ind = work.loc[work["source_state"].astype(str).eq(INDETERMINATE)].copy().reset_index(drop=True)

    ready_selected, ready_covered = _ordered_incremental_cover(ready, radius_km)
    ind_selected, ind_covered = _geometry_only_greedy_cover(ind, radius_km)

    rows: list[dict[str, Any]] = []
    for lane_name, lane, selected in (
        ("SOURCE_READY_COARSE_ORDER_COVER", ready, ready_selected),
        ("SOURCE_INDETERMINATE_GEOMETRY_ONLY_COVER", ind, ind_selected),
    ):
        for seed_order, idx in enumerate(selected, start=1):
            row = lane.iloc[int(idx)]
            rows.append({
                "cohort_unit_id": unit,
                "seed_lane": lane_name,
                "seed_order": seed_order,
                "candidate_cell_id": str(row["candidate_cell_id"]),
                "regional_tile_id": str(row["regional_tile_id"]),
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
                "coarse_evidence_rank": (
                    int(row["coarse_evidence_rank"])
                    if pd.notna(row["coarse_evidence_rank"])
                    else pd.NA
                ),
                "fine_expansion_radius_km": float(radius_km),
                "exact_field_site_claim": False,
                "occupancy_claim": False,
            })
    seeds = pd.DataFrame(rows)
    summary = {
        "cohort_unit_id": unit,
        "source_ready_candidate_count": int(len(ready)),
        "source_ready_seed_count": int(len(ready_selected)),
        "source_ready_coverage_complete": bool(ready_covered.all()),
        "source_indeterminate_candidate_count": int(len(ind)),
        "source_indeterminate_seed_count": int(len(ind_selected)),
        "source_indeterminate_coverage_complete": bool(ind_covered.all()),
        "total_seed_count": int(len(seeds)),
        "seed_footprint_radius_km": float(radius_km),
        "top_k_used": False,
        "score_threshold_used": False,
        "budget_used": False,
        "user_site_count_used": False,
        "cross_lane_coverage_used": False,
        "source_indeterminate_ecological_rank_used": False,
        "candidate_rows_dropped": 0,
    }
    return seeds, summary


def build_all_seed_plans(
    orders: dict[str, pd.DataFrame],
    *,
    outer: pd.DataFrame | None = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    contract = _contract()
    if set(orders) != set(UNITS):
        raise ValueError("coarse order unit set drifted")
    for unit in UNITS:
        if len(orders[unit]) != EXPECTED_CANDIDATES:
            raise ValueError(f"{unit} production coarse order must contain exactly 39,200 rows")
    if outer is None:
        geometry = fetch_geoboundaries_country_geometry("JP")
        outer, outer_summary = build_fresh_sentinel_v2_outer_frame(geometry)
        if int(outer_summary["candidate_count"]) != EXPECTED_CANDIDATES:
            raise ValueError("live frozen outer frame candidate count drifted")
    outer = outer.reset_index(drop=True)
    if len(outer) != EXPECTED_CANDIDATES:
        raise ValueError("outer frame must contain exactly 39,200 candidates")

    radius = float(contract["seed_footprint"]["radius_km"])
    plans: dict[str, pd.DataFrame] = {}
    unit_summary: dict[str, Any] = {}
    for unit in UNITS:
        plan, summary = build_unit_seed_plan(orders[unit], outer, unit, radius_km=radius)
        plans[unit] = plan
        unit_summary[unit] = summary

    return plans, {
        "schema_version": "cirsium-fresh-sentinel-v2-coarse-to-fine-seed-result-v1",
        "status": "AUTOMATIC_COARSE_TO_FINE_SEEDS_BUILT_PRE_OUTCOME",
        "outer_frame_identity": "JP_PUBLIC_COUNTRY_BROAD_FRAME_V1",
        "candidate_count": EXPECTED_CANDIDATES,
        "seed_footprint_radius_km": radius,
        "unit_results": unit_summary,
        "top_k_used": False,
        "score_threshold_used": False,
        "budget_used": False,
        "user_site_count_used": False,
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used": False,
        "private_exact_site_geometry_used": False,
        "p02_result_used": False,
        "human_access_used": False,
        "seed_is_exact_field_site": False,
        "seed_is_occupancy_claim": False,
        "regular_100m_graph_built": False,
        "next_gate": "Freeze seed hashes/counts, then define exact 5-km fine-frame materialization around every seed before 100-m structural ordering.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order", action="append", required=True, help="UNIT=path.csv.gz")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    mapping: dict[str, pd.DataFrame] = {}
    for spec in args.order:
        unit, path = spec.split("=", 1)
        mapping[unit] = pd.read_csv(path, low_memory=False)
    plans, summary = build_all_seed_plans(mapping)
    out = args.out_dir
    if out.exists():
        raise ValueError("refusing to overwrite coarse-to-fine seed output directory")
    out.mkdir(parents=True)
    hashes = {}
    for unit, frame in plans.items():
        path = out / f"{unit}_fine_expansion_seeds.csv.gz"
        frame.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0})
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        hashes[unit] = digest
    summary["private_seed_sha256_by_unit"] = hashes
    summary_path = out / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
