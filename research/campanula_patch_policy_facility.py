#!/usr/bin/env python3
"""Development-only facility-coverage Campanula patch policy.

This experiment starts from the already supported occurrence-conditioned NDVI
patch universe.  It asks whether a finite survey decision improves when a
selected patch receives credit for the *supported patch catchment* that can be
searched within the declared 1-km development radius.

All patch universes, environmental responsibilities, catchment relations,
coverage-degree rarity weights, component balancing, survey-gap scores, and
policy orders are frozen from pre-2026 GBIF + public NDVI before the inspected
2026 field clusters are read.  Field outcomes are used only for development
scoring and for the separately labelled outcome-only set-cover oracle.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

import campanula_patch_policy as base
import campanula_patch_policy_spatial as spatial
from campanula_patch_policy_fast import cached_prefix, json_safe_oracle
from campanula_persistent_patch_hash import fast_random_patch_audit
from campanula_worldcover_discovery import haversine_km

SUPPORT_FRACTION = 0.05
CATCHMENT_RADII_KM = (0.75, 1.0, 1.25)
FACILITY_WEIGHTS = (0.25, 0.5, 1.0, 2.0)
RARITY_POWERS = (0.5, 1.0, 2.0)
COMPONENT_BALANCE_POWERS = (0.0, 0.5, 1.0)
GEO_WEIGHTS = (0.0, 0.5, 1.0)
GAP_WEIGHTS = (0.0, 0.05)

# Keep the already successful environmental-policy terms fixed near the current
# optimum so this experiment isolates the new finite-survey catchment term.
SUPPORT_WEIGHT = 0.10
NEW_COMPONENT_WEIGHT = 0.10
AREA_COST_WEIGHT = 0.02


def zone_member_coordinates(universe: pd.DataFrame, zone: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    indices = base.patch.member_indices(zone)
    if not indices:
        return np.asarray([], dtype=float), np.asarray([], dtype=float)
    members = universe.loc[indices]
    return (
        pd.to_numeric(members["lat"], errors="coerce").to_numpy(float),
        pd.to_numeric(members["lon"], errors="coerce").to_numpy(float),
    )


def patch_catchment_matrix(
    universe: pd.DataFrame,
    zones: pd.DataFrame,
    radius_km: float,
) -> np.ndarray:
    """Return patch-to-patch search catchments without field outcomes.

    Target patch j is covered by survey patch i when any supported member cell
    of j lies within ``radius_km`` of any supported member cell of i.  This uses
    the same operational distance scale as the declared development endpoint,
    but contains no 2026 coordinates.
    """
    n = len(zones)
    catchment = np.zeros((n, n), dtype=bool)
    member_coords = [zone_member_coordinates(universe, row) for _, row in zones.iterrows()]
    islands = zones["survey_area_id"].astype(str).to_numpy()

    for i in range(n):
        lat_i, lon_i = member_coords[i]
        if not len(lat_i):
            continue
        for j in range(i, n):
            if islands[i] != islands[j]:
                continue
            lat_j, lon_j = member_coords[j]
            if not len(lat_j):
                continue
            minimum = np.inf
            # Patch sizes are small after bounded complete-link aggregation, so
            # exact member-to-member distances are cheap and avoid centroid bias.
            for lat0, lon0 in zip(lat_i, lon_i):
                d = haversine_km(lat0, lon0, lat_j, lon_j)
                if len(d):
                    minimum = min(minimum, float(np.min(d)))
                if minimum <= radius_km:
                    break
            if minimum <= radius_km:
                catchment[i, j] = True
                catchment[j, i] = True

    # A patch must always cover itself even under malformed/missing coordinates.
    np.fill_diagonal(catchment, True)
    return catchment


def catchment_target_weights(
    catchment: np.ndarray,
    islands: np.ndarray,
    rarity_power: float,
    component_balance_power: float,
) -> np.ndarray:
    """Weight hard-to-cover patches more strongly, outcome-blind.

    The coverage degree is the number of survey patches whose declared
    catchment could cover a target patch.  Inverse degree therefore gives more
    weight to isolated / weakly substitutable supported patches.  A partial
    component-size normalization prevents a record-rich island from dominating
    the objective merely because it contains more candidate patches.
    """
    degree = np.maximum(catchment.sum(axis=0).astype(float), 1.0)
    weights = np.power(degree, -float(rarity_power))
    for component in sorted(set(islands.astype(str))):
        idx = np.flatnonzero(islands.astype(str) == component)
        if not len(idx):
            continue
        weights[idx] /= float(len(idx)) ** float(component_balance_power)
    total = float(weights.sum())
    if total <= 0 or not np.isfinite(total):
        return np.full(len(weights), 1.0 / max(len(weights), 1), dtype=float)
    return weights / total


def greedy_facility_order(
    matrix: np.ndarray,
    support: np.ndarray,
    area_cost: np.ndarray,
    islands: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
    gap: np.ndarray,
    spatial_scale: dict[str, float],
    catchment: np.ndarray,
    target_weights: np.ndarray,
    facility_weight: float,
    geo_weight: float,
    gap_weight: float,
) -> list[int]:
    """Greedy finite-survey policy with prototype and facility coverage."""
    n_patches, n_prototypes = matrix.shape
    current_proto = np.zeros(n_prototypes, dtype=float)
    covered_targets = np.zeros(n_patches, dtype=bool)
    selected = np.zeros(n_patches, dtype=bool)
    seen_components: set[str] = set()
    min_selected_distance = np.full(n_patches, np.inf, dtype=float)
    order: list[int] = []

    for _ in range(n_patches):
        remaining = np.flatnonzero(~selected)
        if not len(remaining):
            break

        if n_prototypes:
            proto_gain = np.mean(
                np.maximum(matrix[remaining], current_proto[None, :])
                - current_proto[None, :],
                axis=1,
            )
        else:
            proto_gain = np.zeros(len(remaining), dtype=float)

        uncovered = ~covered_targets
        if uncovered.any():
            facility_gain = (
                catchment[remaining][:, uncovered].astype(float)
                @ target_weights[uncovered]
            )
        else:
            facility_gain = np.zeros(len(remaining), dtype=float)

        component_bonus = np.asarray(
            [float(str(islands[i]) not in seen_components) for i in remaining],
            dtype=float,
        )
        geographic = np.zeros(len(remaining), dtype=float)
        for pos, index in enumerate(remaining):
            component = str(islands[index])
            if component not in seen_components:
                geographic[pos] = 1.0
            else:
                scale = max(float(spatial_scale.get(component, 1.0)), 1e-6)
                geographic[pos] = min(float(min_selected_distance[index]) / scale, 1.0)

        values = (
            proto_gain
            + float(facility_weight) * facility_gain
            + SUPPORT_WEIGHT * support[remaining]
            + NEW_COMPONENT_WEIGHT * component_bonus
            + float(geo_weight) * geographic
            + float(gap_weight) * gap[remaining]
            - AREA_COST_WEIGHT * area_cost[remaining]
        )

        # Stable deterministic tie-breaking keeps the experiment reproducible.
        keys = list(
            zip(
                values,
                facility_gain,
                proto_gain,
                geographic,
                gap[remaining],
                support[remaining],
                -area_cost[remaining],
                -remaining,
            )
        )
        best_pos = max(range(len(remaining)), key=lambda pos: keys[pos])
        best_index = int(remaining[best_pos])

        selected[best_index] = True
        current_proto = np.maximum(current_proto, matrix[best_index])
        covered_targets |= catchment[best_index]
        component = str(islands[best_index])
        seen_components.add(component)
        order.append(best_index)

        same = np.flatnonzero((islands.astype(str) == component) & (~selected))
        if len(same):
            d = haversine_km(
                lat[best_index],
                lon[best_index],
                lat[same],
                lon[same],
            )
            min_selected_distance[same] = np.minimum(
                min_selected_distance[same], np.asarray(d, dtype=float)
            )

    return order


def main() -> None:
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
    universe, prototypes = base.attach_ndvi(universe, prototypes, args.ndvi)
    responsibility, support_rank, proto_rows, kernel_scale = base.environmental_geometry(
        universe, prototypes
    )

    # Generator stage: the 5% support universe is chosen because it contains the
    # smallest 1-km oracle (11 patches) in the already completed diagnostic.
    # The oracle outcome itself is not read here and never enters ordering.
    _, zones = base.make_zones(universe, support_rank, SUPPORT_FRACTION)
    matrix, support, area_cost, islands = base.patch_responsibilities(
        zones, responsibility, support_rank
    )
    gap, spatial_scale, islands, lat, lon = spatial.patch_spatial_features(
        zones, proto_rows
    )

    frozen_orders: dict[str, list[int]] = {}
    policy_specs: list[dict[str, float | str]] = []
    catchment_cache: dict[float, np.ndarray] = {}
    for radius in CATCHMENT_RADII_KM:
        catchment = patch_catchment_matrix(universe, zones, radius)
        catchment_cache[float(radius)] = catchment
        for rarity_power in RARITY_POWERS:
            for balance_power in COMPONENT_BALANCE_POWERS:
                target_weights = catchment_target_weights(
                    catchment,
                    islands,
                    rarity_power,
                    balance_power,
                )
                for facility_weight in FACILITY_WEIGHTS:
                    for geo_weight in GEO_WEIGHTS:
                        for gap_weight in GAP_WEIGHTS:
                            name = (
                                f"facility_r{radius:.2f}_fw{facility_weight:.2f}_"
                                f"rare{rarity_power:.1f}_bal{balance_power:.1f}_"
                                f"gw{geo_weight:.2f}_gap{gap_weight:.2f}"
                            )
                            frozen_orders[name] = greedy_facility_order(
                                matrix,
                                support,
                                area_cost,
                                islands,
                                lat,
                                lon,
                                gap,
                                spatial_scale,
                                catchment,
                                target_weights,
                                facility_weight,
                                geo_weight,
                                gap_weight,
                            )
                            policy_specs.append(
                                {
                                    "policy": name,
                                    "support_fraction": SUPPORT_FRACTION,
                                    "catchment_radius_km": float(radius),
                                    "facility_weight": float(facility_weight),
                                    "rarity_power": float(rarity_power),
                                    "component_balance_power": float(balance_power),
                                    "geo_weight": float(geo_weight),
                                    "gap_weight": float(gap_weight),
                                }
                            )

    # Development scoring only from here down.
    detections = pd.read_csv(args.detections)
    results: list[dict] = []
    for spec in policy_specs:
        order = frozen_orders[str(spec["policy"])]
        ranked = base.ranked_zones_for_order(zones, order)
        frontier = cached_prefix(universe, ranked, detections, 1.0)
        if frontier is not None:
            results.append(
                {
                    **spec,
                    "total_patch_universe": int(len(zones)),
                    **frontier,
                }
            )
    results.sort(key=lambda row: (row["n_patches"], row["n_cells"], row["policy"]))
    if not results:
        raise RuntimeError("No facility patch policy recovered all 19 clusters")

    distinct: list[dict] = []
    seen = set()
    for row in results:
        signature = (row["n_patches"], tuple(row["selected_zone_ids"]))
        if signature in seen:
            continue
        seen.add(signature)
        distinct.append(row)
        if len(distinct) >= 20:
            break

    for i, row in enumerate(distinct):
        row["matched_random_patches"] = fast_random_patch_audit(
            universe,
            zones,
            detections,
            row,
            1.0,
            args.random_iterations,
            args.seed + 1009 * i,
        )

    best = min(
        distinct,
        key=lambda row: (
            row["n_patches"],
            row["matched_random_patches"]["complete_recovery_probability"]
            if row["matched_random_patches"]["complete_recovery_probability"] is not None
            else 1.0,
            row["n_cells"],
        ),
    )
    oracle = json_safe_oracle(universe, zones, detections, 1.0)
    selected = set(best["selected_zone_ids"])
    best_rows = zones[zones["zone_id"].astype(str).isin(selected)].copy()

    args.out.mkdir(parents=True, exist_ok=True)
    best_rows.to_csv(args.out / "best_facility_patch_policy.csv", index=False)
    pd.DataFrame(results).drop(columns=["nearest_km"], errors="ignore").to_csv(
        args.out / "facility_patch_policy_frontier.csv", index=False
    )
    report = {
        "status": "development_only",
        "field_coordinates_used_by_generator": False,
        "generator": (
            "environmental prototype coverage + rarity-aware supported-patch "
            "facility coverage + component bonus + optional geographic "
            "complementarity + pre-2026 survey-gap value"
        ),
        "support_fraction": SUPPORT_FRACTION,
        "prototype_count": int(len(proto_rows)),
        "prototype_kernel_scale": float(kernel_scale),
        "policy_count": int(len(policy_specs)),
        "prior_spatial_policy": {
            "n_patches": 32,
            "n_cells": 284,
            "matched_random_complete_probability": 0.0004,
        },
        "best_outcome_blind_policy": best,
        "oracle_set_cover": oracle,
        "random_audited_results": distinct,
        "top_policy_results": results[:80],
    }
    (args.out / "facility_patch_policy_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
