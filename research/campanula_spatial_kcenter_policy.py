#!/usr/bin/env python3
"""Development-only automatic spatial k-center policy for Campanula.

The retained 32-patch development policy is dominated by within-island
geographic complementarity.  This experiment asks whether that successful term
can be isolated into a simpler, outcome-blind geometry-only compression rule.

The 5% occurrence-conditioned support patches are fixed before field outcomes
are opened.  Within each island, the first patch is the support-patch medoid
(minimum maximum centroid distance).  Additional patches are chosen by
farthest-first traversal, normalized by each island's own patch diameter so no
large island wins merely by scale.  Survey size is selected automatically at
the knee between equal-island spatial representation and selected patch
fraction.  No field coordinate, field recovery label, fixed patch count, or user
budget participates in ordering or stopping.
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
RECOVERY_RADIUS_KM = 1.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--microterrain-universe", type=Path, required=True)
    parser.add_argument("--gbif-prototypes", type=Path, required=True)
    parser.add_argument("--ndvi", type=Path, required=True)
    parser.add_argument("--detections", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def _distance_matrix(zones: pd.DataFrame) -> np.ndarray:
    lat = pd.to_numeric(zones["latitude"], errors="coerce").to_numpy(float)
    lon = pd.to_numeric(zones["longitude"], errors="coerce").to_numpy(float)
    n = len(zones)
    matrix = np.full((n, n), np.inf, dtype=float)
    np.fill_diagonal(matrix, 0.0)
    components = zones["survey_area_id"].astype(str).to_numpy()
    for component in sorted(set(components)):
        idx = np.flatnonzero(components == component)
        for offset, i in enumerate(idx):
            if offset + 1 >= len(idx):
                continue
            j = idx[offset + 1 :]
            d = np.asarray(haversine_km(lat[i], lon[i], lat[j], lon[j]), dtype=float)
            matrix[i, j] = d
            matrix[j, i] = d
    return matrix


def _component_scales(distance: np.ndarray, components: np.ndarray) -> dict[str, float]:
    scales: dict[str, float] = {}
    for component in sorted(set(components)):
        idx = np.flatnonzero(components == component)
        if len(idx) <= 1:
            scales[component] = 1.0
            continue
        block = distance[np.ix_(idx, idx)]
        finite = block[np.isfinite(block)]
        scales[component] = max(float(np.max(finite)), 1e-6)
    return scales


def _medoid(distance: np.ndarray, idx: np.ndarray) -> int:
    if len(idx) == 1:
        return int(idx[0])
    block = distance[np.ix_(idx, idx)]
    eccentricity = np.max(block, axis=1)
    return int(idx[int(np.argmin(eccentricity))])


def _equal_island_representation(
    distance: np.ndarray,
    selected: np.ndarray,
    components: np.ndarray,
    scales: dict[str, float],
) -> tuple[float, float, dict[str, float]]:
    component_scores: dict[str, float] = {}
    component_max_residual: dict[str, float] = {}
    for component in sorted(set(components)):
        idx = np.flatnonzero(components == component)
        chosen = np.flatnonzero(np.logical_and(selected, components == component))
        if not len(chosen):
            component_scores[component] = 0.0
            component_max_residual[component] = 1.0
            continue
        nearest = np.min(distance[np.ix_(idx, chosen)], axis=1)
        normalized = np.clip(nearest / float(scales[component]), 0.0, 1.0)
        component_scores[component] = float(1.0 - np.mean(normalized))
        component_max_residual[component] = float(np.max(normalized))
    representation = float(np.mean(list(component_scores.values())))
    max_residual = float(max(component_max_residual.values()))
    return representation, max_residual, component_scores


def _farthest_order(zones: pd.DataFrame, distance: np.ndarray) -> tuple[list[int], pd.DataFrame]:
    components = zones["survey_area_id"].astype(str).to_numpy()
    scales = _component_scales(distance, components)
    selected = np.zeros(len(zones), dtype=bool)
    order: list[int] = []
    rows: list[dict[str, object]] = []

    # Deterministic center seed per disconnected island.
    for component in sorted(set(components)):
        idx = np.flatnonzero(components == component)
        pos = _medoid(distance, idx)
        selected[pos] = True
        order.append(pos)
        representation, max_residual, _ = _equal_island_representation(
            distance, selected, components, scales
        )
        rows.append({
            "rank": len(order),
            "zone_id": str(zones.iloc[pos]["zone_id"]),
            "survey_area_id": component,
            "selection_phase": "component_medoid_seed",
            "normalized_farthest_distance": 0.0,
            "spatial_representation": representation,
            "maximum_normalized_residual": max_residual,
        })

    while (~selected).any():
        best_key = None
        best = -1
        best_norm = -1.0
        for pos in np.flatnonzero(~selected):
            component = str(components[pos])
            chosen = np.flatnonzero(np.logical_and(selected, components == component))
            nearest = float(np.min(distance[pos, chosen])) if len(chosen) else float(scales[component])
            normalized = nearest / float(scales[component])
            member_count = float(zones.iloc[int(pos)].get("zone_member_count", 1.0))
            key = (normalized, -member_count, -int(pos))
            if best_key is None or key > best_key:
                best_key = key
                best = int(pos)
                best_norm = float(normalized)
        if best < 0:
            raise RuntimeError("failed to choose next k-center patch")
        selected[best] = True
        order.append(best)
        representation, max_residual, _ = _equal_island_representation(
            distance, selected, components, scales
        )
        rows.append({
            "rank": len(order),
            "zone_id": str(zones.iloc[best]["zone_id"]),
            "survey_area_id": str(components[best]),
            "selection_phase": "normalized_farthest_first",
            "normalized_farthest_distance": best_norm,
            "spatial_representation": representation,
            "maximum_normalized_residual": max_residual,
        })

    curve = pd.DataFrame(rows)
    curve["selected_patch_fraction"] = curve["rank"] / float(len(zones))
    curve["knee_score"] = curve["spatial_representation"] - curve["selected_patch_fraction"]
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

    distance = _distance_matrix(zones)
    order, curve = _farthest_order(zones, distance)
    ranked = _ranked_zones(zones, order)
    recommended_rank = int(curve.loc[curve["recommended"], "rank"].iloc[0])
    selected_zones = ranked.iloc[:recommended_rank].copy()
    selected_cells, selected_cell_count = _selected_cells(universe, selected_zones)

    # Field outcomes are first opened here.
    detections = pd.read_csv(args.detections)
    recommended_field = evaluate(selected_cells, detections, RECOVERY_RADIUS_KM)
    complete_prefix = cached_prefix(universe, ranked, detections, RECOVERY_RADIUS_KM)

    recommended_row = curve.loc[curve["recommended"]].iloc[0]
    report = {
        "status": "development_only_spatial_kcenter_policy",
        "species": "Campanula microdonta",
        "field_coordinates_used_to_order_patches": False,
        "field_coordinates_used_to_choose_stopping_point": False,
        "support_fraction": SUPPORT_FRACTION,
        "recovery_radius_km": RECOVERY_RADIUS_KM,
        "patch_universe": int(len(zones)),
        "support_components": int(zones["survey_area_id"].astype(str).nunique()),
        "ordering": "one within-island medoid seed, then island-diameter-normalized farthest-first",
        "stopping_rule": "maximize equal-island spatial representation minus selected patch fraction",
        "selected_patches": recommended_rank,
        "selected_cells": int(selected_cell_count),
        "spatial_representation": float(recommended_row["spatial_representation"]),
        "maximum_normalized_residual": float(recommended_row["maximum_normalized_residual"]),
        "field_development_result": recommended_field,
        "first_complete_recovery_prefix": complete_prefix,
        "historical_complete_recovery_reference_patches": 32,
        "historical_minimum_set_cover_reference_patches": 11,
        "kernel_scale": float(kernel_scale),
        "interpretation": (
            "This isolates within-island geographic complementarity from the retained 32-patch policy. "
            "No occurrence-prototype count, field label, fixed patch budget, or support-area mass controls stopping."
        ),
    }

    args.out.mkdir(parents=True, exist_ok=True)
    selected_zones.to_csv(args.out / "spatial_kcenter_selected_patches.csv", index=False)
    ranked.to_csv(args.out / "spatial_kcenter_patch_order.csv", index=False)
    curve.to_csv(args.out / "spatial_kcenter_frontier.csv", index=False)
    (args.out / "spatial_kcenter_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
