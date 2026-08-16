#!/usr/bin/env python3
"""Development-only robustness audit for the Campanula hybrid frontier.

The full-data hybrid weights are read from a previously produced development
report and never re-tuned inside leave-one-prototype-out perturbations. Each
pre-2026 GBIF microenvironment prototype is omitted once, scores are rebuilt,
and the fixed full-data candidate budget is evaluated against the inspected 2026
clusters. This is a sensitivity audit, not independent confirmation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

from campanula_ndvi_transition_discovery import ndvi_surfaces, sample_surfaces
from campanula_ndvi_microclimate_hybrid import (
    JOINT_STATE,
    NDVI_STATE,
    fit_distance_rank,
    sample_microclimate,
    terrain_microclimate_surface,
)
from campanula_worldcover_discovery import evaluate, minimum_count_for_complete_recovery


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--microterrain-universe", type=Path, required=True)
    parser.add_argument("--gbif-prototypes", type=Path, required=True)
    parser.add_argument("--ndvi", type=Path, required=True)
    parser.add_argument("--dem", action="append", required=True, help="ISLAND=path.tif")
    parser.add_argument("--detections", type=Path, required=True)
    parser.add_argument("--hybrid-report", type=Path, required=True)
    parser.add_argument("--radius-km", type=float, default=1.0)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    dem_map = {}
    for spec in args.dem:
        island, path = spec.split("=", 1)
        dem_map[island] = Path(path)

    universe = pd.read_csv(args.microterrain_universe)
    prototypes = pd.read_csv(args.gbif_prototypes).reset_index(drop=True)
    lon = pd.concat([universe["lon"], prototypes["lon"]], ignore_index=True)
    lat = pd.concat([universe["lat"], prototypes["lat"]], ignore_index=True)

    # Public-layer preprocessing remains outcome blind.
    with rasterio.open(args.ndvi) as src:
        tr, crs, ndvi = ndvi_surfaces(src, lon, lat)
        u_ndvi = sample_surfaces(tr, crs, ndvi, universe["lon"], universe["lat"])
        p_ndvi = sample_surfaces(tr, crs, ndvi, prototypes["lon"], prototypes["lat"])
    universe = pd.concat([universe.reset_index(drop=True), u_ndvi], axis=1)
    prototypes = pd.concat([prototypes, p_ndvi], axis=1)

    terrain = {
        str(path): terrain_microclimate_surface(path)
        for path in sorted(set(dem_map.values()), key=str)
    }
    universe = pd.concat([universe, sample_microclimate(universe, terrain, dem_map)], axis=1)
    prototypes = pd.concat([prototypes, sample_microclimate(prototypes, terrain, dem_map)], axis=1)

    report = json.loads(args.hybrid_report.read_text(encoding="utf-8"))
    endpoints = []
    for key in ("candidate_count_best", "matched_random_best"):
        row = report[key]
        endpoint = {
            "label": key,
            "weight": float(row["ndvi_weight"]),
            "candidate_count": int(row["candidate_count"]),
            "full_grid_fraction": float(row["grid_fraction"]),
            "full_matched_random": row["matched_random"],
        }
        if not any(
            abs(endpoint["weight"] - existing["weight"]) < 1e-12
            and endpoint["candidate_count"] == existing["candidate_count"]
            for existing in endpoints
        ):
            endpoints.append(endpoint)

    # Score components for every prototype omission are frozen before outcomes are loaded.
    loo_scores = []
    for endpoint in endpoints:
        weight = endpoint["weight"]
        full_ndvi_d, full_ndvi_rank = fit_distance_rank(universe, prototypes, NDVI_STATE)
        full_joint_d, full_joint_rank = fit_distance_rank(universe, prototypes, JOINT_STATE)
        full_score = weight * full_ndvi_rank + (1.0 - weight) * full_joint_rank
        full_order = np.argsort(full_score, kind="mergesort")
        full_selected = set(full_order[: endpoint["candidate_count"]].tolist())
        for omitted in range(len(prototypes)):
            remaining = prototypes.drop(index=omitted).reset_index(drop=True)
            _, ndvi_rank = fit_distance_rank(universe, remaining, NDVI_STATE)
            _, joint_rank = fit_distance_rank(universe, remaining, JOINT_STATE)
            score = weight * ndvi_rank + (1.0 - weight) * joint_rank
            order = np.argsort(score, kind="mergesort")
            selected = set(order[: endpoint["candidate_count"]].tolist())
            union = full_selected | selected
            loo_scores.append({
                "endpoint": endpoint["label"],
                "weight": weight,
                "candidate_count": endpoint["candidate_count"],
                "omitted_prototype": int(omitted),
                "omitted_island": str(prototypes.loc[omitted, "island"]),
                "omitted_lat": float(prototypes.loc[omitted, "lat"]),
                "omitted_lon": float(prototypes.loc[omitted, "lon"]),
                "order": order,
                "jaccard_with_full": float(len(full_selected & selected) / len(union)) if union else 1.0,
            })

    # Development outcomes become visible only here.
    detections = pd.read_csv(args.detections)
    rows = []
    for item in loo_scores:
        order = item.pop("order")
        fixed = universe.iloc[order[: item["candidate_count"]]]
        fixed_result = evaluate(fixed, detections, args.radius_km)
        required_count, witness = minimum_count_for_complete_recovery(
            universe, detections, order, args.radius_km
        )
        rows.append({
            **item,
            "fixed_budget_recovered": int(fixed_result["recovered"]),
            "fixed_budget_total": int(fixed_result["total"]),
            "fixed_budget_max_nearest_km": float(fixed_result["max_nearest_km"]),
            "required_count_for_19": None if required_count is None else int(required_count),
            "required_inflation_ratio": None if required_count is None else float(required_count / item["candidate_count"]),
            "detection_witness_ranks": [int(x) for x in witness],
        })

    summary = []
    table = pd.DataFrame(rows)
    for endpoint in endpoints:
        sub = table[table["endpoint"].eq(endpoint["label"])]
        finite_required = pd.to_numeric(sub["required_count_for_19"], errors="coerce").dropna()
        summary.append({
            **endpoint,
            "n_leave_one_out": int(len(sub)),
            "fixed_budget_complete_rate": float((sub["fixed_budget_recovered"] == 19).mean()),
            "min_fixed_budget_recovered": int(sub["fixed_budget_recovered"].min()),
            "median_fixed_budget_recovered": float(sub["fixed_budget_recovered"].median()),
            "median_jaccard_with_full": float(sub["jaccard_with_full"].median()),
            "min_jaccard_with_full": float(sub["jaccard_with_full"].min()),
            "median_required_count_for_19": None if finite_required.empty else float(finite_required.median()),
            "max_required_count_for_19": None if finite_required.empty else int(finite_required.max()),
            "max_required_inflation_ratio": None if finite_required.empty else float((finite_required / endpoint["candidate_count"]).max()),
        })

    args.out.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.out / "prototype_loo_rows.csv", index=False)
    result = {
        "status": "development_only",
        "field_coordinates_used_by_generator": False,
        "weights_retuned_inside_loo": False,
        "n_prototypes": int(len(prototypes)),
        "endpoints": summary,
    }
    (args.out / "prototype_loo_report.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
