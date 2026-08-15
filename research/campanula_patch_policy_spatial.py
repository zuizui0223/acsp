#!/usr/bin/env python3
"""Development-only spatially complementary Campanula patch policy.

All patch universes, environmental prototype responsibilities, training-record
survey-gap scores, and spatially complementary policy orders are frozen from
pre-2026 GBIF + public NDVI before the inspected 2026 field clusters are read.
Field outcomes are used only for development scoring and the separately labeled
outcome-only set-cover oracle.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

import campanula_patch_policy as base
from campanula_patch_policy_fast import cached_prefix, json_safe_oracle
from campanula_persistent_patch_hash import fast_random_patch_audit
from campanula_worldcover_discovery import haversine_km

SUPPORT_FRACTIONS = (0.0381, 0.05, 0.075, 0.10)


def patch_spatial_features(zones, prototypes):
    """Outcome-blind gap and within-component spatial scale for each patch."""
    n = len(zones)
    gap = np.zeros(n, dtype=float)
    island = zones["survey_area_id"].astype(str).to_numpy()
    lat = pd.to_numeric(zones["latitude"], errors="coerce").to_numpy(float)
    lon = pd.to_numeric(zones["longitude"], errors="coerce").to_numpy(float)

    local_proto = {
        name: frame
        for name, frame in prototypes.groupby(prototypes["island"].astype(str))
    }
    for i in range(n):
        source = local_proto.get(island[i])
        if source is None or source.empty:
            gap[i] = np.nan
            continue
        d = haversine_km(
            lat[i],
            lon[i],
            source["lat"].to_numpy(float),
            source["lon"].to_numpy(float),
        )
        gap[i] = float(np.min(d))

    # Normalize survey gap within each disconnected component. A component with
    # no training occurrences receives maximal exploratory gap, but still needs
    # environmental support because the patch universe is NDVI-conditioned.
    gap_norm = np.zeros(n, dtype=float)
    spatial_scale = {}
    for name in sorted(set(island)):
        idx = np.flatnonzero(island == name)
        values = gap[idx]
        finite = np.isfinite(values)
        if finite.any():
            hi = float(np.quantile(values[finite], 0.95))
            hi = max(hi, 1e-6)
            gap_norm[idx[finite]] = np.clip(values[finite] / hi, 0.0, 1.0)
            gap_norm[idx[~finite]] = 1.0
        else:
            gap_norm[idx] = 1.0

        if len(idx) <= 1:
            spatial_scale[name] = 1.0
        else:
            distances = []
            for pos, i in enumerate(idx[:-1]):
                d = haversine_km(
                    lat[i], lon[i], lat[idx[pos + 1 :]], lon[idx[pos + 1 :]]
                )
                distances.extend(np.asarray(d, dtype=float).tolist())
            spatial_scale[name] = max(float(np.quantile(distances, 0.90)), 0.25)

    return gap_norm, spatial_scale, island, lat, lon


def greedy_spatial_order(
    matrix,
    support,
    area_cost,
    islands,
    lat,
    lon,
    gap,
    spatial_scale,
    support_weight,
    new_component_weight,
    area_cost_weight,
    geo_weight,
    gap_weight,
):
    n_patches, n_prototypes = matrix.shape
    current = np.zeros(n_prototypes, dtype=float)
    selected = np.zeros(n_patches, dtype=bool)
    selected_by_island: dict[str, list[int]] = {}
    order = []
    for _ in range(n_patches):
        best_key = None
        best_index = None
        for index in np.flatnonzero(~selected):
            updated = np.maximum(current, matrix[index])
            coverage_gain = float(np.mean(updated - current)) if n_prototypes else 0.0
            component = str(islands[index])
            previous = selected_by_island.get(component, [])
            component_bonus = float(len(previous) == 0)
            if previous:
                d = haversine_km(
                    lat[index],
                    lon[index],
                    lat[np.asarray(previous, dtype=int)],
                    lon[np.asarray(previous, dtype=int)],
                )
                geographic_complementarity = min(
                    float(np.min(d)) / float(spatial_scale[component]), 1.0
                )
            else:
                geographic_complementarity = 1.0
            value = (
                coverage_gain
                + float(support_weight) * support[index]
                + float(new_component_weight) * component_bonus
                + float(geo_weight) * geographic_complementarity
                + float(gap_weight) * gap[index]
                - float(area_cost_weight) * area_cost[index]
            )
            key = (
                value,
                coverage_gain,
                geographic_complementarity,
                gap[index],
                support[index],
                -area_cost[index],
                -index,
            )
            if best_key is None or key > best_key:
                best_key = key
                best_index = int(index)
        if best_index is None:
            break
        selected[best_index] = True
        current = np.maximum(current, matrix[best_index])
        selected_by_island.setdefault(str(islands[best_index]), []).append(best_index)
        order.append(best_index)
    return order


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
    universe, prototypes = base.attach_ndvi(universe, prototypes, args.ndvi)
    responsibility, support_rank, proto_rows, kernel_scale = base.environmental_geometry(
        universe, prototypes
    )

    # Generator stage: freeze every patch universe and policy order before fields.
    frozen = {}
    policy_specs = []
    for fraction in SUPPORT_FRACTIONS:
        _, zones = base.make_zones(universe, support_rank, fraction)
        matrix, support, area_cost, islands = base.patch_responsibilities(
            zones, responsibility, support_rank
        )
        gap, spatial_scale, islands, lat, lon = patch_spatial_features(zones, proto_rows)
        orders = {}
        # Keep the successful environmental-policy settings near their prior
        # optimum while searching only the two new ecological terms densely.
        for support_weight in (0.10, 0.25):
            for new_component_weight in (0.10, 0.25):
                for area_cost_weight in (0.02, 0.05):
                    for geo_weight in (0.02, 0.05, 0.10, 0.25, 0.50, 1.00):
                        for gap_weight in (0.0, 0.02, 0.05, 0.10, 0.25, 0.50):
                            name = (
                                f"spatial_sw{support_weight:.2f}_iw{new_component_weight:.2f}_"
                                f"cw{area_cost_weight:.2f}_gw{geo_weight:.2f}_gap{gap_weight:.2f}"
                            )
                            orders[name] = greedy_spatial_order(
                                matrix,
                                support,
                                area_cost,
                                islands,
                                lat,
                                lon,
                                gap,
                                spatial_scale,
                                support_weight,
                                new_component_weight,
                                area_cost_weight,
                                geo_weight,
                                gap_weight,
                            )
                            policy_specs.append(
                                {
                                    "support_fraction": float(fraction),
                                    "policy": name,
                                    "support_weight": float(support_weight),
                                    "new_component_weight": float(new_component_weight),
                                    "area_cost_weight": float(area_cost_weight),
                                    "geo_weight": float(geo_weight),
                                    "gap_weight": float(gap_weight),
                                }
                            )
        frozen[float(fraction)] = {"zones": zones, "orders": orders}

    # Development scoring only from here down.
    detections = pd.read_csv(args.detections)
    results = []
    for spec in policy_specs:
        zones = frozen[spec["support_fraction"]]["zones"]
        order = frozen[spec["support_fraction"]]["orders"][spec["policy"]]
        ranked = base.ranked_zones_for_order(zones, order)
        frontier = cached_prefix(universe, ranked, detections, 1.0)
        if frontier is not None:
            results.append({**spec, "total_patch_universe": int(len(zones)), **frontier})
    results.sort(key=lambda row: (row["n_patches"], row["n_cells"], row["support_fraction"]))
    if not results:
        raise RuntimeError("No spatial patch policy recovered all 19 clusters")

    distinct = []
    seen = set()
    for row in results:
        signature = (row["support_fraction"], row["n_patches"], tuple(row["selected_zone_ids"]))
        if signature in seen:
            continue
        seen.add(signature)
        distinct.append(row)
        if len(distinct) >= 15:
            break
    for i, row in enumerate(distinct):
        zones = frozen[row["support_fraction"]]["zones"]
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

    oracle = {
        str(fraction): json_safe_oracle(
            universe, frozen[float(fraction)]["zones"], detections, 1.0
        )
        for fraction in SUPPORT_FRACTIONS
    }
    selected = set(best["selected_zone_ids"])
    best_zones = frozen[best["support_fraction"]]["zones"]
    best_rows = best_zones[best_zones["zone_id"].astype(str).isin(selected)].copy()

    args.out.mkdir(parents=True, exist_ok=True)
    best_rows.to_csv(args.out / "best_spatial_patch_policy.csv", index=False)
    pd.DataFrame(results).drop(columns=["nearest_km"], errors="ignore").to_csv(
        args.out / "spatial_patch_policy_frontier.csv", index=False
    )
    report = {
        "status": "development_only",
        "field_coordinates_used_by_generator": False,
        "generator": "environmental prototype coverage + within-component geographic complementarity + pre-2026 survey-gap value",
        "prototype_count": int(len(proto_rows)),
        "prototype_kernel_scale": float(kernel_scale),
        "policy_count": int(len(policy_specs)),
        "prior_policy": {"n_patches": 51, "n_cells": 275, "matched_random_complete_probability": 0.113},
        "best_outcome_blind_policy": best,
        "oracle_set_cover": oracle,
        "top_policy_results": results[:60],
        "random_audited_results": distinct,
    }
    (args.out / "spatial_patch_policy_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
