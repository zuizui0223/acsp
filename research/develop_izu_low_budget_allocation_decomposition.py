#!/usr/bin/env python3
"""Decompose the sole q=0.10/K=5 NDVI-support signal in Izu development.

This is development-only. The q/K/r cell and all comparison families were
predeclared before this implementation in
validation/izu_microenvironment_generalization_development/
low_budget_allocation_decomposition_protocol.json.

All candidate sets are frozen from training occurrences/public layers before
held-out coordinates are inspected.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

import benchmark_izu_microenvironment_random_taxa as bench
from campanula_ndvi_microclimate_hybrid import NDVI_STATE, evaluate, fit_distance_rank
from campanula_ndvi_transition_discovery import ndvi_surfaces
from develop_izu_hierarchical_island_allocation import (
    ISLANDS,
    integer_allocate,
    select_from_allocation,
)
from develop_izu_strong_coverage_comparator import build_geometry
from develop_izu_strong_coverage_sweep import greedy_coverage_order
from develop_izu_support_constrained_coverage import bootstrap_ci, sign_flip_p
from run_izu_microenvironment_random_taxa import retrieval_wkt

bench.island_wkt = retrieval_wkt


def compare(taxon: pd.DataFrame, method: str, control: str, seed: int) -> dict:
    left = taxon[taxon["method"].eq(method)][["sample_id", "recall"]]
    right = taxon[taxon["method"].eq(control)][["sample_id", "recall"]].rename(
        columns={"recall": "control_recall"}
    )
    merged = left.merge(right, on="sample_id", how="inner")
    if merged.empty:
        return {
            "method": method,
            "control": control,
            "taxa": 0,
            "passes": False,
        }
    diff = (merged["recall"] - merged["control_recall"]).to_numpy(float)
    ci = bootstrap_ci(diff, 10000, seed)
    p = sign_flip_p(diff, 50000, seed + 1)
    return {
        "method": method,
        "control": control,
        "taxa": int(len(merged)),
        "method_recall": float(merged["recall"].mean()),
        "control_recall": float(merged["control_recall"].mean()),
        "difference": float(diff.mean()),
        "bootstrap_95ci": ci,
        "sign_flip_p": p,
        "positive_taxa": int((diff > 0).sum()),
        "negative_taxa": int((diff < 0).sum()),
        "ties": int((diff == 0).sum()),
        "passes": bool(diff.mean() > 0 and ci[0] > 0 and p < 0.05),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--transfer-protocol", type=Path, required=True)
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--ndvi", type=Path, required=True)
    parser.add_argument("--dem", action="append", required=True, help="ISLAND=path.tif")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    protocol = json.loads(args.protocol.read_text())
    transfer = json.loads(args.transfer_protocol.read_text())
    sample = pd.read_csv(args.sample)
    target = protocol["target"]
    q = float(target["support_quantile"])
    budget = int(target["budget"])
    radius = float(target["radius_km"])

    dem_map: dict[str, Path] = {}
    for spec in args.dem:
        island, path = spec.split("=", 1)
        dem_map[island] = Path(path)

    grid = bench.build_public_grid(dem_map)
    geometry = build_geometry(grid)
    island_orders: dict[str, pd.DataFrame] = {}
    for island in ISLANDS:
        mask = grid["island"].eq(island).to_numpy()
        island_orders[island] = greedy_coverage_order(
            grid, geometry, mask, max_budget=budget, radius_km=radius
        )
    global_order = greedy_coverage_order(
        grid,
        geometry,
        np.ones(len(grid), dtype=bool),
        max_budget=budget,
        radius_km=radius,
    )
    global_selected = global_order.iloc[:budget].copy()
    equal_allocation = {island: 1 for island in ISLANDS}
    equal_selected = select_from_allocation(grid, island_orders, equal_allocation)

    alphas = (0.0, 0.5, 1.0, 2.0, 4.0)
    rows: list[dict] = []
    failures: list[dict] = []

    with rasterio.open(args.ndvi) as src:
        tr, crs, surfaces = ndvi_surfaces(src, grid["lon"], grid["lat"])
        ndvi_grid = bench.attach_public_features(
            grid,
            ndvi_transform=tr,
            ndvi_crs=crs,
            ndvi_surface_dict=surfaces,
            micro_surfaces={},
            dem_map={},
        )

        for taxon_index, taxon in sample.iterrows():
            name = str(taxon["scientific_name"])
            try:
                occurrences = bench.fetch_occurrences(
                    int(taxon["speciesKey"]),
                    int(transfer["occurrences"]["max_records_per_taxon"]),
                )
                _, folds = bench.make_folds(
                    occurrences,
                    block_degrees=0.03,
                    repeats=5,
                    holdout_fraction=0.2,
                    min_train=int(transfer["validation"]["minimum_training_prototypes"]),
                    seed=int(transfer["sampling"]["seed"]) + int(taxon_index) * 100,
                )
                if len(folds) != 5:
                    failures.append(
                        {
                            "sample_id": int(taxon["sample_id"]),
                            "scientific_name": name,
                            "reason": f"only_{len(folds)}_folds",
                        }
                    )
                    continue

                for repeat_index, fold in enumerate(folds, start=1):
                    train = bench.attach_public_features(
                        fold["train"],
                        ndvi_transform=tr,
                        ndvi_crs=crs,
                        ndvi_surface_dict=surfaces,
                        micro_surfaces={},
                        dem_map={},
                    )
                    _, support_rank = fit_distance_rank(ndvi_grid, train, NDVI_STATE)
                    support_mask = support_rank <= q + 1e-12
                    support_order = greedy_coverage_order(
                        grid,
                        geometry,
                        support_mask,
                        max_budget=budget,
                        radius_km=radius,
                    )
                    support_selected = support_order.iloc[:budget].copy()
                    if len(support_selected) != budget:
                        raise RuntimeError(
                            f"q10 support produced {len(support_selected)} sites, expected {budget}"
                        )

                    support_allocation = {
                        str(k): int(v)
                        for k, v in support_selected.groupby("island").size().to_dict().items()
                    }
                    same_allocation = select_from_allocation(
                        grid, island_orders, support_allocation
                    )

                    methods: dict[str, pd.DataFrame] = {
                        "q10_support_max_coverage": support_selected,
                        "same_island_allocation_max_coverage_without_environment": same_allocation,
                        "equal_one_per_island": equal_selected,
                        "global_max_coverage": global_selected,
                    }
                    train_counts = fold["train"].groupby("island").size().to_dict()
                    for alpha in alphas:
                        weights = {
                            island: float(train_counts.get(island, 0)) + alpha
                            for island in ISLANDS
                        }
                        allocation = integer_allocate(weights, budget)
                        methods[f"training_occurrence_allocation_alpha_{alpha:g}"] = (
                            select_from_allocation(grid, island_orders, allocation)
                        )

                    # Held-out data become visible only after all nine sets are frozen.
                    held = fold["held"].rename(
                        columns={"lat": "latitude", "lon": "longitude"}
                    )
                    for method, selected in methods.items():
                        result = evaluate(selected, held, radius)
                        rows.append(
                            {
                                "sample_id": int(taxon["sample_id"]),
                                "scientific_name": name,
                                "repeat": repeat_index,
                                "method": method,
                                "recall": result["recovered"] / len(held),
                                "selected_sites": int(len(selected)),
                                "island_allocation": json.dumps(
                                    {
                                        str(k): int(v)
                                        for k, v in selected.groupby("island").size().items()
                                    },
                                    sort_keys=True,
                                ),
                            }
                        )
            except Exception as exc:
                failures.append(
                    {
                        "sample_id": int(taxon["sample_id"]),
                        "scientific_name": name,
                        "reason": f"{type(exc).__name__}: {exc}",
                    }
                )

    fold = pd.DataFrame(rows)
    if fold.empty:
        raise RuntimeError("No low-budget decomposition folds completed")
    taxon = (
        fold.groupby(["sample_id", "scientific_name", "method"], as_index=False)
        .agg(recall=("recall", "mean"), folds=("repeat", "count"))
    )
    means = (
        taxon.groupby("method", as_index=False)
        .agg(mean_recall=("recall", "mean"), taxa=("sample_id", "nunique"))
        .sort_values("mean_recall", ascending=False)
    )

    within_island = compare(
        taxon,
        "q10_support_max_coverage",
        "same_island_allocation_max_coverage_without_environment",
        20261001,
    )
    q10_vs_equal = compare(
        taxon, "q10_support_max_coverage", "equal_one_per_island", 20261011
    )
    q10_vs_global = compare(
        taxon, "q10_support_max_coverage", "global_max_coverage", 20261021
    )

    occurrence_methods = [
        f"training_occurrence_allocation_alpha_{alpha:g}" for alpha in alphas
    ]
    occurrence_vs_global = [
        compare(taxon, method, "global_max_coverage", 20261100 + i * 10)
        for i, method in enumerate(occurrence_methods)
    ]
    occurrence_means = means[means["method"].isin(occurrence_methods)]
    best_occurrence_method = str(occurrence_means.iloc[0]["method"])
    q10_vs_best_occurrence = compare(
        taxon, "q10_support_max_coverage", best_occurrence_method, 20261201
    )
    best_occurrence_vs_global = next(
        item for item in occurrence_vs_global if item["method"] == best_occurrence_method
    )

    within_island_ndvi_survives = bool(within_island["passes"])
    ndvi_allocation_survives = bool(
        q10_vs_equal["passes"] and q10_vs_best_occurrence["passes"]
    )
    occurrence_policy_survives = bool(
        any(item["passes"] for item in occurrence_vs_global)
    )

    if within_island_ndvi_survives:
        decision = "retain_within_island_ndvi_support"
    elif ndvi_allocation_survives:
        decision = "retain_ndvi_between_island_allocation_only"
    elif occurrence_policy_survives:
        decision = "retain_training_occurrence_island_allocation_only"
    else:
        decision = "drop_environment_and_occurrence_allocation; retain_geometry_only_coverage"

    summary = {
        "status": "development_only",
        "protocol_id": protocol["protocol_id"],
        "support_quantile": q,
        "budget": budget,
        "radius_km": radius,
        "taxa": int(taxon["sample_id"].nunique()),
        "failures": failures,
        "method_means": means.to_dict("records"),
        "within_island_ndvi_test": within_island,
        "q10_vs_equal_one_per_island": q10_vs_equal,
        "q10_vs_global_max_coverage": q10_vs_global,
        "occurrence_allocations_vs_global": occurrence_vs_global,
        "best_occurrence_method": best_occurrence_method,
        "best_occurrence_vs_global": best_occurrence_vs_global,
        "q10_vs_best_occurrence": q10_vs_best_occurrence,
        "within_island_ndvi_survives": within_island_ndvi_survives,
        "ndvi_allocation_survives": ndvi_allocation_survives,
        "occurrence_policy_survives": occurrence_policy_survives,
        "decision": decision,
        "weights_or_qkr_retuned": False,
        "frozen_192_consumed": False,
        "confirmation_claim": False,
    }

    args.out.mkdir(parents=True, exist_ok=True)
    fold.to_csv(args.out / "low_budget_decomposition_fold_results.csv", index=False)
    taxon.to_csv(args.out / "low_budget_decomposition_taxon_results.csv", index=False)
    means.to_csv(args.out / "low_budget_decomposition_method_means.csv", index=False)
    (args.out / "low_budget_decomposition_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
