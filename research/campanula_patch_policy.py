#!/usr/bin/env python3
"""Development-only occurrence-prototype patch policy for Campanula.

Patch universes and every outcome-blind patch order are constructed from
pre-2026 GBIF occurrence prototypes and the pinned ESA NDVI composite before the
2026 field clusters are opened. The field outcomes are then used only to measure
prefix recovery and, separately, an explicitly outcome-only integer set-cover
oracle that diagnoses the theoretical patch-count ceiling.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from scipy.optimize import Bounds, LinearConstraint, milp

import campanula_persistent_patch as patch
from campanula_persistent_patch_hash import (
    _zone_coverage_masks,
    fast_complete_link_zones,
    fast_prefix_patch_frontier,
    fast_random_patch_audit,
)
from campanula_ndvi_transition_discovery import ndvi_surfaces, sample_surfaces
from campanula_worldcover_discovery import robust_fit, transform

FULL_NDVI = [
    "ndvi_p50",
    "ndvi_amp",
    "ndvi_mean100",
    "ndvi_mean250",
    "ndvi_amp_mean100",
]
SUPPORT_FRACTIONS = (0.0381, 0.05, 0.075, 0.10)
MERGE_DISTANCE_M = 1000.0


def attach_ndvi(universe, prototypes, ndvi_path):
    all_lon = pd.concat([universe["lon"], prototypes["lon"]], ignore_index=True)
    all_lat = pd.concat([universe["lat"], prototypes["lat"]], ignore_index=True)
    with rasterio.open(ndvi_path) as src:
        transform_, crs, surfaces = ndvi_surfaces(src, all_lon, all_lat)
        grid = sample_surfaces(transform_, crs, surfaces, universe["lon"], universe["lat"])
        proto = sample_surfaces(transform_, crs, surfaces, prototypes["lon"], prototypes["lat"])
    return (
        pd.concat([universe.reset_index(drop=True), grid], axis=1),
        pd.concat([prototypes.reset_index(drop=True), proto], axis=1),
    )


def environmental_geometry(universe, prototypes):
    proto_ok = prototypes[FULL_NDVI].notna().all(axis=1)
    grid_ok = universe[FULL_NDVI].notna().all(axis=1)
    median, scale = robust_fit(prototypes.loc[proto_ok, FULL_NDVI].to_numpy(float))
    proto_z = transform(prototypes.loc[proto_ok, FULL_NDVI].to_numpy(float), median, scale)
    grid_z = np.full((len(universe), len(FULL_NDVI)), np.nan)
    grid_z[grid_ok.to_numpy()] = transform(
        universe.loc[grid_ok, FULL_NDVI].to_numpy(float), median, scale
    )
    proto_rows = prototypes.loc[proto_ok].reset_index(drop=True)

    if len(proto_z) > 1:
        d = np.sqrt(np.square(proto_z[:, None, :] - proto_z[None, :, :]).sum(axis=2))
        np.fill_diagonal(d, np.inf)
        kernel_scale = float(np.median(np.min(d, axis=1)))
    else:
        kernel_scale = 1.0
    kernel_scale = max(kernel_scale, 0.25)

    valid_indices = np.flatnonzero(grid_ok.to_numpy())
    dist = np.full((len(universe), len(proto_z)), np.inf)
    block = grid_z[valid_indices]
    for start in range(0, len(block), 3000):
        values = block[start : start + 3000]
        d2 = np.square(values[:, None, :] - proto_z[None, :, :]).sum(axis=2)
        dist[valid_indices[start : start + len(values)]] = np.sqrt(d2)
    responsibility = np.exp(-0.5 * np.square(dist / kernel_scale))
    responsibility[~np.isfinite(responsibility)] = 0.0
    nearest = np.min(dist, axis=1)
    support_rank = pd.Series(nearest).rank(method="average", pct=True).to_numpy(float)
    return responsibility, support_rank, proto_rows, kernel_scale


def make_zones(universe, support_rank, fraction):
    patch.aggregate_candidates_to_zones = fast_complete_link_zones
    cells, zones = patch.make_patch_universe(
        universe, support_rank, float(fraction), MERGE_DISTANCE_M
    )
    return cells, zones


def patch_responsibilities(zones, responsibility, support_rank):
    matrix = np.zeros((len(zones), responsibility.shape[1]), dtype=float)
    support = np.zeros(len(zones), dtype=float)
    area_cost = np.zeros(len(zones), dtype=float)
    islands = []
    for zone_index, zone in zones.iterrows():
        member_ids = patch.member_indices(zone)
        matrix[zone_index] = responsibility[member_ids].max(axis=0)
        support[zone_index] = float(1.0 - np.min(support_rank[member_ids]))
        area_cost[zone_index] = float(len(member_ids))
        islands.append(str(zone["survey_area_id"]))
    if len(area_cost) and area_cost.max() > 0:
        area_cost = area_cost / area_cost.max()
    return matrix, support, area_cost, np.asarray(islands, dtype=object)


def greedy_order(
    matrix,
    support,
    area_cost,
    islands,
    support_weight,
    new_component_weight,
    area_cost_weight,
):
    n_patches, n_prototypes = matrix.shape
    current = np.zeros(n_prototypes, dtype=float)
    selected = np.zeros(n_patches, dtype=bool)
    seen_islands = set()
    order = []
    for _ in range(n_patches):
        best_key = None
        best_index = None
        for index in np.flatnonzero(~selected):
            updated = np.maximum(current, matrix[index])
            coverage_gain = float(np.mean(updated - current)) if n_prototypes else 0.0
            component_bonus = float(islands[index] not in seen_islands)
            value = (
                coverage_gain
                + float(support_weight) * support[index]
                + float(new_component_weight) * component_bonus
                - float(area_cost_weight) * area_cost[index]
            )
            key = (value, coverage_gain, support[index], -area_cost[index], -index)
            if best_key is None or key > best_key:
                best_key = key
                best_index = int(index)
        if best_index is None:
            break
        selected[best_index] = True
        current = np.maximum(current, matrix[best_index])
        seen_islands.add(str(islands[best_index]))
        order.append(best_index)
    return order


def ranked_zones_for_order(zones, order):
    ranked = zones.iloc[order].copy().reset_index(drop=True)
    ranked["zone_score"] = np.arange(len(ranked), 0, -1, dtype=float)
    ranked["policy_rank"] = np.arange(1, len(ranked) + 1)
    return ranked


def exact_oracle_set_cover(universe, zones, detections, radius_km):
    detection_rows, masks, sizes = _zone_coverage_masks(
        universe, zones.reset_index(drop=True), detections, radius_km
    )
    n_zones = len(zones)
    n_detections = len(detection_rows)
    coverage = np.zeros((n_detections, n_zones), dtype=float)
    for zone_index, mask in enumerate(masks):
        mask_int = int(mask)
        for detection_index in range(n_detections):
            coverage[detection_index, zone_index] = float(
                bool(mask_int & (1 << detection_index))
            )
    if np.any(coverage.sum(axis=1) == 0):
        return None
    result = milp(
        c=np.ones(n_zones, dtype=float),
        integrality=np.ones(n_zones, dtype=int),
        bounds=Bounds(np.zeros(n_zones), np.ones(n_zones)),
        constraints=LinearConstraint(
            coverage,
            lb=np.ones(n_detections),
            ub=np.full(n_detections, np.inf),
        ),
        options={"time_limit": 30.0},
    )
    if not result.success or result.x is None:
        return None
    chosen = np.flatnonzero(result.x > 0.5)
    selected_zones = zones.iloc[chosen]
    selected_cells = sum(int(sizes[index]) for index in chosen)
    return {
        "status": "outcome_only_diagnostic_not_generator",
        "n_patches": int(len(chosen)),
        "n_cells": int(selected_cells),
        "selected_zone_ids": selected_zones["zone_id"].astype(str).tolist(),
        "island_patch_counts": selected_zones["survey_area_id"].astype(str).value_counts().astype(int).to_dict(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--microterrain-universe", type=Path, required=True)
    parser.add_argument("--gbif-prototypes", type=Path, required=True)
    parser.add_argument("--ndvi", type=Path, required=True)
    parser.add_argument("--detections", type=Path, required=True)
    parser.add_argument("--random-iterations", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20260815)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    universe = pd.read_csv(args.microterrain_universe)
    prototypes = pd.read_csv(args.gbif_prototypes)
    universe, prototypes = attach_ndvi(universe, prototypes, args.ndvi)
    responsibility, support_rank, proto_rows, kernel_scale = environmental_geometry(
        universe, prototypes
    )

    # Generator stage: patch universes and every policy order are frozen here.
    frozen = {}
    policy_specs = []
    for fraction in SUPPORT_FRACTIONS:
        _, zones = make_zones(universe, support_rank, fraction)
        matrix, support, area_cost, islands = patch_responsibilities(
            zones, responsibility, support_rank
        )
        orders = {}
        for support_weight in (0.0, 0.05, 0.10, 0.25):
            for new_component_weight in (0.0, 0.10, 0.25, 0.50):
                for area_cost_weight in (0.0, 0.02, 0.05):
                    name = (
                        f"prototype_cov_sw{support_weight:.2f}_"
                        f"iw{new_component_weight:.2f}_cw{area_cost_weight:.2f}"
                    )
                    orders[name] = greedy_order(
                        matrix,
                        support,
                        area_cost,
                        islands,
                        support_weight,
                        new_component_weight,
                        area_cost_weight,
                    )
                    policy_specs.append(
                        {
                            "support_fraction": float(fraction),
                            "policy": name,
                            "support_weight": float(support_weight),
                            "new_component_weight": float(new_component_weight),
                            "area_cost_weight": float(area_cost_weight),
                        }
                    )
        frozen[float(fraction)] = {"zones": zones, "orders": orders}

    # Development outcomes become visible only below this line.
    detections = pd.read_csv(args.detections)
    results = []
    random_candidates = []
    for spec in policy_specs:
        zones = frozen[spec["support_fraction"]]["zones"]
        order = frozen[spec["support_fraction"]]["orders"][spec["policy"]]
        ranked = ranked_zones_for_order(zones, order)
        frontier = fast_prefix_patch_frontier(universe, ranked, detections, 1.0)
        if frontier is None:
            continue
        row = {**spec, "total_patch_universe": int(len(zones)), **frontier}
        results.append(row)

    results.sort(key=lambda row: (row["n_patches"], row["n_cells"], row["support_fraction"]))
    if not results:
        raise RuntimeError("No prototype-coverage patch policy recovered all 19 clusters")

    # Audit only the distinct best operational fronts to avoid repeated Monte Carlo
    # for tied parameter settings that induce the same patch prefix.
    seen = set()
    for row in results:
        signature = (
            row["support_fraction"],
            row["n_patches"],
            tuple(row["selected_zone_ids"]),
        )
        if signature in seen:
            continue
        seen.add(signature)
        random_candidates.append(row)
        if len(random_candidates) >= 12:
            break

    for i, row in enumerate(random_candidates):
        zones = frozen[row["support_fraction"]]["zones"]
        row["matched_random_patches"] = fast_random_patch_audit(
            universe,
            zones,
            detections,
            row,
            1.0,
            args.random_iterations,
            args.seed + i * 1009,
        )

    best = min(
        random_candidates,
        key=lambda row: (
            row["n_patches"],
            row["matched_random_patches"]["complete_recovery_probability"]
            if row["matched_random_patches"]["complete_recovery_probability"] is not None
            else 1.0,
            row["n_cells"],
        ),
    )

    oracle = {}
    for fraction in SUPPORT_FRACTIONS:
        oracle[str(fraction)] = exact_oracle_set_cover(
            universe, frozen[float(fraction)]["zones"], detections, 1.0
        )

    best_zones = frozen[best["support_fraction"]]["zones"]
    selected_ids = set(best["selected_zone_ids"])
    best_zone_rows = best_zones[
        best_zones["zone_id"].astype(str).isin(selected_ids)
    ].copy()

    args.out.mkdir(parents=True, exist_ok=True)
    best_zone_rows.to_csv(args.out / "best_patch_policy.csv", index=False)
    pd.DataFrame(results).drop(columns=["nearest_km"], errors="ignore").to_csv(
        args.out / "patch_policy_frontier.csv", index=False
    )
    report = {
        "status": "development_only",
        "field_coordinates_used_by_generator": False,
        "generator": "occurrence-prototype environmental responsibility coverage over bounded complete-link patches",
        "prototype_count": int(len(proto_rows)),
        "prototype_kernel_scale": float(kernel_scale),
        "support_fractions": list(SUPPORT_FRACTIONS),
        "merge_distance_m": MERGE_DISTANCE_M,
        "policy_count": int(len(policy_specs)),
        "best_outcome_blind_policy": best,
        "oracle_set_cover": oracle,
        "top_policy_results": results[:50],
        "random_audited_results": random_candidates,
    }
    (args.out / "patch_policy_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
