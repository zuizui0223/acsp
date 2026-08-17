#!/usr/bin/env python3
"""Develop a set-level survey policy after cell-ranking transfer failure.

Occurrence-conditioned NDVI support defines only an eligible region. Within
that mask, selected survey points are chosen by a deterministic geographic
farthest-first objective. q=1.0 is the coverage-only control and contains no
environmental restriction. The 16 taxa are inspected development data only.
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
from run_izu_microenvironment_random_taxa import retrieval_wkt

bench.island_wkt = retrieval_wkt


def projected_xy(frame: pd.DataFrame) -> np.ndarray:
    lat0 = float(frame["lat"].mean())
    scale_x = 111.320 * np.cos(np.radians(lat0))
    return np.column_stack(
        [
            frame["lon"].to_numpy(float) * scale_x,
            frame["lat"].to_numpy(float) * 111.320,
        ]
    )


def farthest_order(frame: pd.DataFrame, max_k: int) -> pd.DataFrame:
    """Return one deterministic maximin order; smaller budgets use prefixes."""
    if frame.empty or max_k <= 0:
        return frame.iloc[0:0].copy()
    max_k = min(int(max_k), len(frame))
    xy = projected_xy(frame)
    centroid = xy.mean(axis=0)
    first = int(np.argmin(np.square(xy - centroid).sum(axis=1)))
    selected = [first]
    min_d2 = np.square(xy - xy[first]).sum(axis=1)
    min_d2[first] = -1.0
    while len(selected) < max_k:
        nxt = int(np.argmax(min_d2))
        selected.append(nxt)
        d2 = np.square(xy - xy[nxt]).sum(axis=1)
        min_d2 = np.minimum(min_d2, d2)
        min_d2[selected] = -1.0
    return frame.iloc[selected].copy().reset_index(drop=True)


def bootstrap_ci(values: np.ndarray, draws: int, seed: int) -> list[float]:
    values = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    means = np.empty(draws, dtype=float)
    for i in range(draws):
        means[i] = float(np.mean(rng.choice(values, size=len(values), replace=True)))
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def sign_flip_p(values: np.ndarray, draws: int, seed: int) -> float:
    values = np.asarray(values, dtype=float)
    observed = float(np.mean(values))
    if observed <= 0:
        return 1.0
    rng = np.random.default_rng(seed)
    extreme = 0
    for _ in range(draws):
        signs = rng.choice(np.array([-1.0, 1.0]), size=len(values), replace=True)
        extreme += int(float(np.mean(values * signs)) >= observed)
    return float((extreme + 1) / (draws + 1))


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
    quantiles = [float(value) for value in protocol["support_quantiles"]]
    budgets = [int(value) for value in protocol["budgets"]]
    radii = [float(value) for value in protocol["recovery_radii_km"]]
    max_budget = max(budgets)

    dem_map: dict[str, Path] = {}
    for spec in args.dem:
        island, path = spec.split("=", 1)
        dem_map[island] = Path(path)

    grid = bench.build_public_grid(dem_map)
    args.out.mkdir(parents=True, exist_ok=True)
    fold_rows: list[dict] = []
    failures: list[dict] = []

    with rasterio.open(args.ndvi) as src:
        ndvi_transform, ndvi_crs, ndvi_surface_dict = ndvi_surfaces(
            src, grid["lon"], grid["lat"]
        )
        ndvi_grid = bench.attach_public_features(
            grid,
            ndvi_transform=ndvi_transform,
            ndvi_crs=ndvi_crs,
            ndvi_surface_dict=ndvi_surface_dict,
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
                    block_degrees=float(protocol["spatial_blocks_degrees"]),
                    repeats=int(protocol["repeats"]),
                    holdout_fraction=float(protocol["holdout_fraction"]),
                    min_train=int(protocol["minimum_training_prototypes"]),
                    seed=int(transfer["sampling"]["seed"]) + int(taxon_index) * 100,
                )
                if len(folds) != int(protocol["repeats"]):
                    failures.append(
                        {
                            "sample_id": int(taxon["sample_id"]),
                            "scientific_name": name,
                            "reason": f"only_{len(folds)}_valid_folds",
                        }
                    )
                    continue

                for repeat_index, fold in enumerate(folds, start=1):
                    train = bench.attach_public_features(
                        fold["train"],
                        ndvi_transform=ndvi_transform,
                        ndvi_crs=ndvi_crs,
                        ndvi_surface_dict=ndvi_surface_dict,
                        micro_surfaces={},
                        dem_map={},
                    )
                    _, support_rank = fit_distance_rank(ndvi_grid, train, NDVI_STATE)

                    selections: dict[tuple[float, int], pd.DataFrame] = {}
                    for q in quantiles:
                        eligible = ndvi_grid.loc[support_rank <= q + 1e-12].copy()
                        if eligible.empty:
                            continue
                        ordered = farthest_order(eligible, max_budget)
                        for budget in budgets:
                            if len(ordered) >= budget:
                                selections[(q, budget)] = ordered.iloc[:budget].copy()

                    # Held-out coordinates become visible only after every q/K set is frozen.
                    held = fold["held"].rename(columns={"lat": "latitude", "lon": "longitude"})
                    for (q, budget), selected in selections.items():
                        for radius in radii:
                            result = evaluate(selected, held, radius)
                            fold_rows.append(
                                {
                                    "sample_id": int(taxon["sample_id"]),
                                    "scientific_name": name,
                                    "repeat": repeat_index,
                                    "support_quantile": q,
                                    "budget": budget,
                                    "radius_km": radius,
                                    "heldout_points": int(len(held)),
                                    "recall": result["recovered"] / len(held),
                                    "selected_oshima": int(selected["island"].eq("oshima").sum()),
                                    "selected_toshima": int(selected["island"].eq("toshima").sum()),
                                    "selected_niijima": int(selected["island"].eq("niijima").sum()),
                                    "selected_shikinejima": int(selected["island"].eq("shikinejima").sum()),
                                    "selected_kozushima": int(selected["island"].eq("kozushima").sum()),
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

    fold = pd.DataFrame(fold_rows)
    if fold.empty:
        raise RuntimeError("No support-constrained coverage folds completed")
    taxon = (
        fold.groupby(
            ["sample_id", "scientific_name", "support_quantile", "budget", "radius_km"],
            as_index=False,
        )
        .agg(recall=("recall", "mean"), folds=("repeat", "count"))
    )
    cell = (
        taxon.groupby(["support_quantile", "budget", "radius_km"], as_index=False)
        .agg(mean_recall=("recall", "mean"), taxa=("sample_id", "nunique"))
    )

    comparison_rows = []
    for (budget, radius), group in taxon.groupby(["budget", "radius_km"]):
        control = group[group["support_quantile"].eq(1.0)][["sample_id", "recall"]].rename(
            columns={"recall": "coverage_only_recall"}
        )
        for q in sorted(value for value in group["support_quantile"].unique() if value < 1.0):
            candidate = group[group["support_quantile"].eq(q)][["sample_id", "recall"]]
            merged = candidate.merge(control, on="sample_id", how="inner")
            if merged.empty:
                continue
            diff = (merged["recall"] - merged["coverage_only_recall"]).to_numpy(float)
            ci = bootstrap_ci(diff, 10000, 20260816 + int(budget * 10 + radius * 100 + q * 1000))
            p = sign_flip_p(diff, 50000, 20260817 + int(budget * 10 + radius * 100 + q * 1000))
            comparison_rows.append(
                {
                    "support_quantile": q,
                    "budget": int(budget),
                    "radius_km": float(radius),
                    "taxa": int(len(merged)),
                    "support_constrained_recall": float(merged["recall"].mean()),
                    "coverage_only_recall": float(merged["coverage_only_recall"].mean()),
                    "difference": float(diff.mean()),
                    "bootstrap_low": ci[0],
                    "bootstrap_high": ci[1],
                    "sign_flip_p": p,
                    "positive_taxa": int((diff > 0).sum()),
                    "negative_taxa": int((diff < 0).sum()),
                    "stable_positive": bool(diff.mean() > 0 and ci[0] > 0 and p < 0.05),
                }
            )
    comparisons = pd.DataFrame(comparison_rows)
    stable = comparisons[comparisons["stable_positive"]].copy()
    best = None
    if not comparisons.empty:
        best = comparisons.sort_values(
            ["difference", "bootstrap_low"], ascending=[False, False]
        ).head(1).to_dict("records")[0]

    summary = {
        "status": "development_only",
        "taxa_in_sample": int(len(sample)),
        "taxa_with_results": int(taxon["sample_id"].nunique()),
        "failures": failures,
        "stable_environment_support_cells": int(len(stable)),
        "best_support_constraint_vs_coverage_only": best,
        "decision": (
            "environment_support_adds_stable_set_level_value"
            if len(stable)
            else "no_stable_ndvi_support_value_over_coverage_only"
        ),
        "frozen_192_consumed": False,
        "confirmation_claim": False,
    }

    fold.to_csv(args.out / "coverage_set_fold_results.csv", index=False)
    taxon.to_csv(args.out / "coverage_set_taxon_results.csv", index=False)
    cell.to_csv(args.out / "coverage_set_cells.csv", index=False)
    comparisons.to_csv(args.out / "support_vs_coverage_only.csv", index=False)
    (args.out / "coverage_set_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
