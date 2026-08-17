#!/usr/bin/env python3
"""Final development sweep of NDVI support masks under strong max-coverage selection."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from scipy.spatial import cKDTree

import benchmark_izu_microenvironment_random_taxa as bench
from campanula_ndvi_microclimate_hybrid import NDVI_STATE, evaluate, fit_distance_rank
from campanula_ndvi_transition_discovery import ndvi_surfaces
from develop_izu_support_constrained_coverage import bootstrap_ci, sign_flip_p
from develop_izu_strong_coverage_comparator import build_geometry
from run_izu_microenvironment_random_taxa import retrieval_wkt

bench.island_wkt = retrieval_wkt


def greedy_coverage_order(
    grid: pd.DataFrame,
    geometry: dict[str, dict],
    eligible: np.ndarray,
    *,
    max_budget: int,
    radius_km: float,
) -> pd.DataFrame:
    eligible = np.asarray(eligible, dtype=bool)
    covered = np.zeros(len(grid), dtype=bool)
    selected_mask = np.zeros(len(grid), dtype=bool)
    selected: list[int] = []
    for _ in range(min(int(max_budget), int(eligible.sum()))):
        best_gain = -1
        best_global = None
        for island in sorted(geometry):
            geo = geometry[island]
            idx = geo["idx"]
            candidate_global = idx[eligible[idx] & ~selected_mask[idx]]
            if not len(candidate_global):
                continue
            candidate_local = np.searchsorted(idx, candidate_global)
            uncovered_local = np.flatnonzero(~covered[idx])
            if len(uncovered_local):
                tree = cKDTree(geo["xy"][uncovered_local])
                gains = tree.query_ball_point(
                    geo["xy"][candidate_local], r=float(radius_km), return_length=True
                )
            else:
                gains = np.zeros(len(candidate_global), dtype=int)
            local_max = int(np.max(gains))
            tied = candidate_global[np.asarray(gains) == local_max]
            candidate = int(np.min(tied))
            if local_max > best_gain or (
                local_max == best_gain and (best_global is None or candidate < best_global)
            ):
                best_gain = local_max
                best_global = candidate
        if best_global is None:
            break
        selected.append(best_global)
        selected_mask[best_global] = True
        island = str(grid.loc[best_global, "island"])
        geo = geometry[island]
        idx = geo["idx"]
        local = int(np.searchsorted(idx, best_global))
        newly = geo["tree"].query_ball_point(geo["xy"][local], r=float(radius_km))
        covered[idx[np.asarray(newly, dtype=int)]] = True
    return grid.loc[selected].copy().reset_index(drop=True)


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
    quantiles = [float(x) for x in protocol["support_quantiles"]]
    budgets = [int(x) for x in protocol["budgets"]]
    radius = float(protocol["survey_radius_km"])
    max_budget = max(budgets)

    dem_map: dict[str, Path] = {}
    for spec in args.dem:
        island, path = spec.split("=", 1)
        dem_map[island] = Path(path)

    grid = bench.build_public_grid(dem_map)
    geometry = build_geometry(grid)
    coverage_order = greedy_coverage_order(
        grid,
        geometry,
        np.ones(len(grid), dtype=bool),
        max_budget=max_budget,
        radius_km=radius,
    )
    fold_rows: list[dict] = []
    failures: list[dict] = []

    with rasterio.open(args.ndvi) as src:
        transform, crs, surfaces = ndvi_surfaces(src, grid["lon"], grid["lat"])
        ndvi_grid = bench.attach_public_features(
            grid,
            ndvi_transform=transform,
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
                    failures.append({"sample_id": int(taxon["sample_id"]), "scientific_name": name, "reason": f"only_{len(folds)}_folds"})
                    continue
                for repeat_index, fold in enumerate(folds, start=1):
                    train = bench.attach_public_features(
                        fold["train"],
                        ndvi_transform=transform,
                        ndvi_crs=crs,
                        ndvi_surface_dict=surfaces,
                        micro_surfaces={},
                        dem_map={},
                    )
                    _, support_rank = fit_distance_rank(ndvi_grid, train, NDVI_STATE)
                    orders: dict[float, pd.DataFrame] = {1.0: coverage_order}
                    for q in quantiles:
                        if q >= 1.0:
                            continue
                        orders[q] = greedy_coverage_order(
                            grid,
                            geometry,
                            support_rank <= q + 1e-12,
                            max_budget=max_budget,
                            radius_km=radius,
                        )

                    held = fold["held"].rename(columns={"lat": "latitude", "lon": "longitude"})
                    for q in quantiles:
                        order = orders[q]
                        for budget in budgets:
                            if len(order) < budget:
                                continue
                            selected = order.iloc[:budget].copy()
                            result = evaluate(selected, held, radius)
                            fold_rows.append(
                                {
                                    "sample_id": int(taxon["sample_id"]),
                                    "scientific_name": name,
                                    "repeat": repeat_index,
                                    "support_quantile": q,
                                    "budget": budget,
                                    "recall": result["recovered"] / len(held),
                                }
                            )
            except Exception as exc:
                failures.append({"sample_id": int(taxon["sample_id"]), "scientific_name": name, "reason": f"{type(exc).__name__}: {exc}"})

    fold = pd.DataFrame(fold_rows)
    if fold.empty:
        raise RuntimeError("No max-coverage sweep folds completed")
    taxon = (
        fold.groupby(["sample_id", "scientific_name", "support_quantile", "budget"], as_index=False)
        .agg(recall=("recall", "mean"), folds=("repeat", "count"))
    )
    cells = (
        taxon.groupby(["support_quantile", "budget"], as_index=False)
        .agg(mean_recall=("recall", "mean"), taxa=("sample_id", "nunique"))
    )

    comparisons = []
    for budget, group in taxon.groupby("budget"):
        control = group[group["support_quantile"].eq(1.0)][["sample_id", "recall"]].rename(columns={"recall": "coverage_only_recall"})
        for q in sorted(x for x in quantiles if x < 1.0):
            candidate = group[group["support_quantile"].eq(q)][["sample_id", "recall"]]
            merged = candidate.merge(control, on="sample_id", how="inner")
            diff = (merged["recall"] - merged["coverage_only_recall"]).to_numpy(float)
            ci = bootstrap_ci(diff, 10000, 20260816 + int(q * 1000) + int(budget))
            p = sign_flip_p(diff, 50000, 20260817 + int(q * 1000) + int(budget))
            comparisons.append(
                {
                    "support_quantile": q,
                    "budget": int(budget),
                    "taxa": int(len(merged)),
                    "support_recall": float(merged["recall"].mean()),
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
    comparisons = pd.DataFrame(comparisons)
    stable = comparisons[comparisons["stable_positive"]].copy()
    best = comparisons.sort_values(["difference", "bootstrap_low"], ascending=[False, False]).head(1).to_dict("records")[0]
    summary = {
        "status": "development_only",
        "taxa": int(taxon["sample_id"].nunique()),
        "failures": failures,
        "survey_radius_km": radius,
        "stable_support_cells": int(len(stable)),
        "best_support_vs_coverage_only": best,
        "decision": "retain_ndvi_support_constraint" if len(stable) else "drop_ndvi_support_constraint",
        "frozen_192_consumed": False,
        "confirmation_claim": False,
    }

    args.out.mkdir(parents=True, exist_ok=True)
    fold.to_csv(args.out / "strong_sweep_fold_results.csv", index=False)
    taxon.to_csv(args.out / "strong_sweep_taxon_results.csv", index=False)
    cells.to_csv(args.out / "strong_sweep_cells.csv", index=False)
    comparisons.to_csv(args.out / "strong_sweep_vs_coverage_only.csv", index=False)
    (args.out / "strong_sweep_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
