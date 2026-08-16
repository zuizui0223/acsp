#!/usr/bin/env python3
"""Develop hierarchical island allocation with environment-free within-island coverage."""
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
from develop_izu_support_constrained_coverage import bootstrap_ci, sign_flip_p
from develop_izu_strong_coverage_comparator import build_geometry
from develop_izu_strong_coverage_sweep import greedy_coverage_order
from run_izu_microenvironment_random_taxa import retrieval_wkt

bench.island_wkt = retrieval_wkt
ISLANDS = ("kozushima", "niijima", "oshima", "shikinejima", "toshima")


def integer_allocate(weights: dict[str, float], total: int) -> dict[str, int]:
    """Largest-remainder allocation with stable alphabetical tie breaking."""
    values = np.array([max(0.0, float(weights.get(island, 0.0))) for island in ISLANDS])
    if values.sum() <= 0:
        values[:] = 1.0
    raw = values / values.sum() * int(total)
    base = np.floor(raw).astype(int)
    remaining = int(total) - int(base.sum())
    remainder = raw - base
    order = sorted(range(len(ISLANDS)), key=lambda i: (-remainder[i], ISLANDS[i]))
    for i in order[:remaining]:
        base[i] += 1
    return {island: int(base[i]) for i, island in enumerate(ISLANDS)}


def select_from_allocation(
    grid: pd.DataFrame,
    island_orders: dict[str, pd.DataFrame],
    allocation: dict[str, int],
) -> pd.DataFrame:
    parts = []
    for island in ISLANDS:
        count = int(allocation.get(island, 0))
        if count > 0:
            parts.append(island_orders[island].iloc[:count].copy())
    return pd.concat(parts, ignore_index=True) if parts else grid.iloc[0:0].copy()


def infer_pair(taxon: pd.DataFrame, method: str, control: str, seed: int) -> dict:
    left = taxon[taxon["method"].eq(method)][["sample_id", "recall"]]
    right = taxon[taxon["method"].eq(control)][["sample_id", "recall"]].rename(
        columns={"recall": "control_recall"}
    )
    merged = left.merge(right, on="sample_id", how="inner")
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
    budget = int(protocol["budget"])
    radius = float(protocol["survey_radius_km"])
    alphas = [float(x) for x in protocol["occurrence_pseudocounts"]]
    q = float(protocol["ndvi_support_quantile"])

    dem_map: dict[str, Path] = {}
    for spec in args.dem:
        island, path = spec.split("=", 1)
        dem_map[island] = Path(path)

    grid = bench.build_public_grid(dem_map)
    geometry = build_geometry(grid)
    island_orders = {}
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
    land_weights = {island: float(grid["island"].eq(island).sum()) for island in ISLANDS}
    land_alloc = integer_allocate(land_weights, budget)
    equal_alloc = {island: budget // len(ISLANDS) for island in ISLANDS}
    for island in ISLANDS[: budget % len(ISLANDS)]:
        equal_alloc[island] += 1
    deterministic = {
        "global_max_coverage": global_selected,
        "equal_islands": select_from_allocation(grid, island_orders, equal_alloc),
        "land_area": select_from_allocation(grid, island_orders, land_alloc),
    }

    rows = []
    failures = []
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
                    block_degrees=float(protocol["evaluation"]["spatial_blocks_degrees"]),
                    repeats=int(protocol["evaluation"]["repeats"]),
                    holdout_fraction=float(protocol["evaluation"]["holdout_fraction"]),
                    min_train=int(transfer["validation"]["minimum_training_prototypes"]),
                    seed=int(transfer["sampling"]["seed"]) + int(taxon_index) * 100,
                )
                if len(folds) != int(protocol["evaluation"]["repeats"]):
                    failures.append({"sample_id": int(taxon["sample_id"]), "scientific_name": name, "reason": f"only_{len(folds)}_folds"})
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
                    support_weights = {
                        island: float(((ndvi_grid["island"].eq(island)).to_numpy() & (support_rank <= q + 1e-12)).sum())
                        for island in ISLANDS
                    }
                    support_alloc = integer_allocate(support_weights, budget)
                    methods = dict(deterministic)
                    methods["ndvi_support_area"] = select_from_allocation(
                        grid, island_orders, support_alloc
                    )
                    train_counts = fold["train"].groupby("island").size().to_dict()
                    for alpha in alphas:
                        weights = {island: float(train_counts.get(island, 0)) + alpha for island in ISLANDS}
                        alloc = integer_allocate(weights, budget)
                        methods[f"training_occurrence_alpha_{alpha:g}"] = select_from_allocation(
                            grid, island_orders, alloc
                        )

                    # All sets are frozen before held-out coordinates are inspected.
                    held = fold["held"].rename(columns={"lat": "latitude", "lon": "longitude"})
                    for method, selected in methods.items():
                        result = evaluate(selected, held, radius)
                        rows.append(
                            {
                                "sample_id": int(taxon["sample_id"]),
                                "scientific_name": name,
                                "repeat": repeat_index,
                                "method": method,
                                "recall": result["recovered"] / len(held),
                                "island_allocation": json.dumps({str(k): int(v) for k, v in selected.groupby("island").size().items()}, sort_keys=True),
                            }
                        )
            except Exception as exc:
                failures.append({"sample_id": int(taxon["sample_id"]), "scientific_name": name, "reason": f"{type(exc).__name__}: {exc}"})

    fold = pd.DataFrame(rows)
    if fold.empty:
        raise RuntimeError("No hierarchical allocation folds completed")
    taxon = (
        fold.groupby(["sample_id", "scientific_name", "method"], as_index=False)
        .agg(recall=("recall", "mean"), folds=("repeat", "count"))
    )
    means = taxon.groupby("method", as_index=False).agg(mean_recall=("recall", "mean"), taxa=("sample_id", "nunique"))
    comparisons = []
    for i, method in enumerate(sorted(set(taxon["method"]) - {"global_max_coverage"})):
        comparisons.append(infer_pair(taxon, method, "global_max_coverage", 20260830 + i * 10))
    comp = pd.DataFrame(comparisons)
    best = comp.sort_values(["difference", "bootstrap_95ci"], ascending=[False, False]).head(1).to_dict("records")[0]

    occurrence_methods = [name for name in taxon["method"].unique() if name.startswith("training_occurrence_")]
    best_occurrence = means[means["method"].isin(occurrence_methods)].sort_values("mean_recall", ascending=False).head(1)
    environment_survives = False
    env_vs_best_nonenv = None
    if not best_occurrence.empty:
        best_nonenv_name = str(best_occurrence.iloc[0]["method"])
        env_vs_best_nonenv = infer_pair(taxon, "ndvi_support_area", best_nonenv_name, 20260999)
        environment_survives = bool(
            env_vs_best_nonenv["passes"]
            and next((x["passes"] for x in comparisons if x["method"] == "ndvi_support_area"), False)
        )

    occurrence_survives = any(
        row["passes"] for row in comparisons if row["method"].startswith("training_occurrence_")
    )
    summary = {
        "status": "development_only",
        "budget": budget,
        "radius_km": radius,
        "taxa": int(taxon["sample_id"].nunique()),
        "failures": failures,
        "method_means": means.to_dict("records"),
        "vs_global_max_coverage": comparisons,
        "best_vs_global_max_coverage": best,
        "ndvi_support_vs_best_occurrence_allocation": env_vs_best_nonenv,
        "environment_allocation_survives": environment_survives,
        "occurrence_allocation_survives": occurrence_survives,
        "frozen_192_consumed": False,
        "confirmation_claim": False,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    fold.to_csv(args.out / "hierarchical_allocation_fold_results.csv", index=False)
    taxon.to_csv(args.out / "hierarchical_allocation_taxon_results.csv", index=False)
    means.to_csv(args.out / "hierarchical_allocation_method_means.csv", index=False)
    comp.to_csv(args.out / "hierarchical_allocation_vs_global.csv", index=False)
    (args.out / "hierarchical_allocation_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
