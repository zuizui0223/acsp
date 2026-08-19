#!/usr/bin/env python3
"""Development-only equal-fragment support set policy for Campanula.

The 5% occurrence-conditioned support envelope is already partitioned into
bounded complete-link survey patches.  This experiment treats those patches as
*structural units*, rather than weighting support by patch area.  Every support
fragment receives equal weight within its disconnected island, and every island
receives equal total weight.

A selected patch represents same-island support fragments lying within the
already-declared 1-km operational recovery radius.  The order is therefore a
set-cover / graph-domination order over outcome-blind support structure.  One
representative is seeded per island, then each next patch maximizes newly
represented fragment weight.  The stopping point is the deterministic knee of
fragment coverage versus selected patch fraction.  Field outcomes are opened
only after the complete order and stopping point are frozen.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

import campanula_patch_policy as base
from campanula_patch_policy_fast import cached_prefix
from campanula_worldcover_discovery import evaluate, haversine_km

SUPPORT_FRACTION = 0.05
COVERAGE_RADIUS_KM = 1.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--microterrain-universe", type=Path, required=True)
    parser.add_argument("--gbif-prototypes", type=Path, required=True)
    parser.add_argument("--ndvi", type=Path, required=True)
    parser.add_argument("--detections", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def _fragment_weights(zones: pd.DataFrame) -> np.ndarray:
    components = zones["survey_area_id"].astype(str).to_numpy()
    weights = np.zeros(len(zones), dtype=float)
    unique = sorted(set(components))
    for component in unique:
        local = components == component
        weights[local] = 1.0 / float(local.sum()) / float(len(unique))
    weights /= float(weights.sum())
    return weights


def _member_coords(universe: pd.DataFrame, zone: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    members = base.patch.member_indices(zone)
    rows = universe.iloc[members]
    return rows["lat"].to_numpy(float), rows["lon"].to_numpy(float)


def _minimum_patch_distance_km(
    lat_a: np.ndarray,
    lon_a: np.ndarray,
    lat_b: np.ndarray,
    lon_b: np.ndarray,
) -> float:
    best = np.inf
    # Bounded complete-link patches keep member counts small enough that the
    # pairwise minimum can be computed directly without spatial approximations.
    for lat, lon in zip(lat_a, lon_a):
        d = haversine_km(
            np.full(len(lat_b), float(lat)),
            np.full(len(lat_b), float(lon)),
            lat_b,
            lon_b,
        )
        best = min(best, float(np.min(d)))
        if best <= 0.0:
            return 0.0
    return float(best)


def _fragment_coverage_matrix(universe: pd.DataFrame, zones: pd.DataFrame) -> np.ndarray:
    n = len(zones)
    matrix = np.zeros((n, n), dtype=bool)
    components = zones["survey_area_id"].astype(str).to_numpy()
    coords = [_member_coords(universe, row) for _, row in zones.iterrows()]
    for i in range(n):
        matrix[i, i] = True
        for j in range(i + 1, n):
            if components[i] != components[j]:
                continue
            d = _minimum_patch_distance_km(*coords[i], *coords[j])
            if d <= COVERAGE_RADIUS_KM:
                matrix[i, j] = True
                matrix[j, i] = True
    return matrix


def _marginal_order(
    zones: pd.DataFrame,
    coverage: np.ndarray,
    weights: np.ndarray,
) -> tuple[list[int], pd.DataFrame]:
    n = len(zones)
    selected = np.zeros(n, dtype=bool)
    represented = np.zeros(n, dtype=bool)
    components = zones["survey_area_id"].astype(str).to_numpy()
    order: list[int] = []
    rows: list[dict[str, object]] = []

    def choose(candidates: np.ndarray) -> int:
        best_key = None
        best = -1
        for pos in candidates:
            gain = float(weights[np.logical_and(coverage[pos], ~represented)].sum())
            member_count = float(zones.iloc[int(pos)].get("zone_member_count", 1.0))
            key = (gain, -member_count, -int(pos))
            if best_key is None or key > best_key:
                best_key = key
                best = int(pos)
        if best < 0:
            raise RuntimeError("no support-fragment candidate available")
        return best

    for component in sorted(set(components)):
        candidates = np.flatnonzero(np.logical_and(~selected, components == component))
        pos = choose(candidates)
        previous = float(weights[represented].sum())
        selected[pos] = True
        represented |= coverage[pos]
        cumulative = float(weights[represented].sum())
        order.append(pos)
        rows.append({
            "rank": len(order),
            "zone_id": str(zones.iloc[pos]["zone_id"]),
            "survey_area_id": component,
            "selection_phase": "component_seed",
            "marginal_fragment_weight": cumulative - previous,
            "cumulative_fragment_weight": cumulative,
            "represented_fragments": int(represented.sum()),
        })

    while (~selected).any():
        pos = choose(np.flatnonzero(~selected))
        previous = float(weights[represented].sum())
        selected[pos] = True
        represented |= coverage[pos]
        cumulative = float(weights[represented].sum())
        order.append(pos)
        rows.append({
            "rank": len(order),
            "zone_id": str(zones.iloc[pos]["zone_id"]),
            "survey_area_id": str(zones.iloc[pos]["survey_area_id"]),
            "selection_phase": "global_marginal",
            "marginal_fragment_weight": cumulative - previous,
            "cumulative_fragment_weight": cumulative,
            "represented_fragments": int(represented.sum()),
        })

    curve = pd.DataFrame(rows)
    curve["selected_patch_fraction"] = curve["rank"] / float(n)
    curve["knee_score"] = curve["cumulative_fragment_weight"] - curve["selected_patch_fraction"]
    minimum_rank = len(set(components))
    eligible = curve["rank"] >= minimum_rank
    best_score = float(curve.loc[eligible, "knee_score"].max())
    chosen_rank = int(
        curve.loc[eligible & np.isclose(curve["knee_score"], best_score), "rank"].min()
    )
    curve["recommended"] = curve["rank"].eq(chosen_rank)
    return order, curve


def _ranked_zones(zones: pd.DataFrame, order: list[int]) -> pd.DataFrame:
    ranked = zones.iloc[order].copy().reset_index(drop=True)
    ranked["zone_score"] = np.arange(len(ranked), 0, -1, dtype=float)
    ranked["policy_rank"] = np.arange(1, len(ranked) + 1)
    return ranked


def _selected_cells(universe: pd.DataFrame, selected_zones: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    indices: set[int] = set()
    for _, zone in selected_zones.iterrows():
        indices.update(base.patch.member_indices(zone))
    return universe.loc[sorted(indices)].copy(), len(indices)


def main() -> None:
    args = parse_args()
    universe = pd.read_csv(args.microterrain_universe)
    prototypes = pd.read_csv(args.gbif_prototypes)
    universe, prototypes = base.attach_ndvi(universe, prototypes, args.ndvi)
    _, support_rank, _, kernel_scale = base.environmental_geometry(universe, prototypes)
    _, zones = base.make_zones(universe, support_rank, SUPPORT_FRACTION)

    weights = _fragment_weights(zones)
    coverage = _fragment_coverage_matrix(universe, zones)
    order, curve = _marginal_order(zones, coverage, weights)
    ranked = _ranked_zones(zones, order)
    recommended_rank = int(curve.loc[curve["recommended"], "rank"].iloc[0])
    selected_zones = ranked.iloc[:recommended_rank].copy()
    selected_cells, selected_cell_count = _selected_cells(universe, selected_zones)

    # Field outcomes are first opened here, after the order and knee are fixed.
    detections = pd.read_csv(args.detections)
    recommended_field = evaluate(selected_cells, detections, COVERAGE_RADIUS_KM)
    complete_prefix = cached_prefix(universe, ranked, detections, COVERAGE_RADIUS_KM)

    report = {
        "status": "development_only_support_fragment_set_policy",
        "species": "Campanula microdonta",
        "field_coordinates_used_to_define_fragments": False,
        "field_coordinates_used_to_order_patches": False,
        "field_coordinates_used_to_choose_stopping_point": False,
        "support_fraction": SUPPORT_FRACTION,
        "coverage_radius_km": COVERAGE_RADIUS_KM,
        "patch_universe": int(len(zones)),
        "support_fragment_count": int(len(zones)),
        "support_fragment_components": int(zones["survey_area_id"].astype(str).nunique()),
        "fragment_weighting": "equal fragment weight within island, equal total weight across islands",
        "ordering": "one best patch per island, then maximum marginal newly represented support-fragment weight",
        "stopping_rule": "maximize cumulative fragment weight minus selected patch fraction",
        "selected_patches": recommended_rank,
        "selected_cells": int(selected_cell_count),
        "selected_fragment_weight": float(curve.loc[curve["recommended"], "cumulative_fragment_weight"].iloc[0]),
        "represented_fragments": int(curve.loc[curve["recommended"], "represented_fragments"].iloc[0]),
        "field_development_result": recommended_field,
        "first_complete_recovery_prefix": complete_prefix,
        "historical_complete_recovery_reference_patches": 32,
        "historical_minimum_set_cover_reference_patches": 11,
        "kernel_scale": float(kernel_scale),
        "interpretation": (
            "Small isolated support fragments are not discounted by their area. The selector values state-dependent "
            "structural representation, with field outcomes opened only after the order and knee are frozen."
        ),
    }

    args.out.mkdir(parents=True, exist_ok=True)
    selected_zones.to_csv(args.out / "support_fragment_selected_patches.csv", index=False)
    ranked.to_csv(args.out / "support_fragment_patch_order.csv", index=False)
    curve.to_csv(args.out / "support_fragment_frontier.csv", index=False)
    (args.out / "support_fragment_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
