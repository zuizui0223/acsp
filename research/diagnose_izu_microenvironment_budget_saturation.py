#!/usr/bin/env python3
"""Diagnose when fragmented geographic coverage overwhelms environmental ranking.

The 16-taxon cohort is already inspected and is development-only. This script
keeps the failed Campanula-derived hybrid and NDVI scores fixed, sweeps only the
field-budget/evaluation geometry declared in the generalization-development
protocol, and records all favorable and unfavorable cells.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from scipy.spatial import cKDTree

import benchmark_izu_microenvironment_random_taxa as bench
from campanula_ndvi_microclimate_hybrid import (
    JOINT_STATE,
    NDVI_STATE,
    evaluate,
    fast_matched_random_success,
    fit_distance_rank,
    sample_microclimate,
    terrain_microclimate_surface,
)
from campanula_ndvi_transition_discovery import ndvi_surfaces, sample_surfaces
from run_izu_microenvironment_random_taxa import retrieval_wkt

bench.island_wkt = retrieval_wkt


def selected_grid_distances_km(grid: pd.DataFrame, selected: pd.DataFrame) -> np.ndarray:
    """Approximate distance from every public-grid cell to the selected set."""
    out = np.full(len(grid), np.inf)
    for island, index in grid.groupby("island").groups.items():
        idx = np.asarray(list(index), dtype=int)
        chosen = selected[selected["island"].eq(island)]
        if chosen.empty:
            continue
        lat0 = float(grid.loc[idx, "lat"].mean())
        scale_x = 111.320 * np.cos(np.radians(lat0))
        grid_xy = np.column_stack(
            [grid.loc[idx, "lon"].to_numpy(float) * scale_x,
             grid.loc[idx, "lat"].to_numpy(float) * 111.320]
        )
        selected_xy = np.column_stack(
            [chosen["lon"].to_numpy(float) * scale_x,
             chosen["lat"].to_numpy(float) * 111.320]
        )
        tree = cKDTree(selected_xy)
        out[idx] = tree.query(grid_xy, k=1)[0]
    return out


def taxon_curve(frame: pd.DataFrame) -> pd.DataFrame:
    return (
        frame.groupby(["sample_id", "scientific_name", "budget", "radius_km"], as_index=False)
        .agg(
            hybrid_recall=("hybrid_recall", "mean"),
            ndvi_recall=("ndvi_recall", "mean"),
            random_recall=("random_recall", "mean"),
            hybrid_grid_coverage=("hybrid_grid_coverage", "mean"),
            ndvi_grid_coverage=("ndvi_grid_coverage", "mean"),
            folds=("repeat", "count"),
        )
    )


def summarize_curve(taxon: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (budget, radius), group in taxon.groupby(["budget", "radius_km"]):
        rows.append(
            {
                "budget": int(budget),
                "radius_km": float(radius),
                "taxa": int(len(group)),
                "hybrid_recall": float(group["hybrid_recall"].mean()),
                "ndvi_recall": float(group["ndvi_recall"].mean()),
                "random_recall": float(group["random_recall"].mean()),
                "hybrid_minus_random": float((group["hybrid_recall"] - group["random_recall"]).mean()),
                "ndvi_minus_random": float((group["ndvi_recall"] - group["random_recall"]).mean()),
                "hybrid_minus_ndvi": float((group["hybrid_recall"] - group["ndvi_recall"]).mean()),
                "hybrid_grid_coverage": float(group["hybrid_grid_coverage"].mean()),
                "ndvi_grid_coverage": float(group["ndvi_grid_coverage"].mean()),
            }
        )
    return pd.DataFrame(rows).sort_values(["radius_km", "budget"]).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-protocol", type=Path, required=True)
    parser.add_argument("--transfer-protocol", type=Path, required=True)
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--ndvi", type=Path, required=True)
    parser.add_argument("--dem", action="append", required=True, help="ISLAND=path.tif")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    dev = json.loads(args.development_protocol.read_text())
    transfer = json.loads(args.transfer_protocol.read_text())
    sample = pd.read_csv(args.sample)
    dem_map = {}
    for spec in args.dem:
        island, path = spec.split("=", 1)
        dem_map[island] = Path(path)

    budgets = [int(value) for value in dev["diagnostic"]["candidate_budgets"]]
    radii = [float(value) for value in dev["diagnostic"]["recovery_radii_km"]]
    random_draws = int(dev["diagnostic"]["random_draws_per_fold"])

    grid = bench.build_public_grid(dem_map)
    micro_surfaces = {
        str(path): terrain_microclimate_surface(path)
        for path in sorted(set(dem_map.values()), key=str)
    }

    with rasterio.open(args.ndvi) as src:
        ndvi_transform, ndvi_crs, ndvi_surface_dict = ndvi_surfaces(src, grid["lon"], grid["lat"])
        grid = bench.attach_public_features(
            grid,
            ndvi_transform=ndvi_transform,
            ndvi_crs=ndvi_crs,
            ndvi_surface_dict=ndvi_surface_dict,
            micro_surfaces=micro_surfaces,
            dem_map=dem_map,
        )

        rows = []
        failures = []
        for taxon_index, taxon in sample.iterrows():
            name = str(taxon["scientific_name"])
            try:
                occurrences = bench.fetch_occurrences(
                    int(taxon["speciesKey"]), int(transfer["occurrences"]["max_records_per_taxon"])
                )
                thinned, folds = bench.make_folds(
                    occurrences,
                    block_degrees=float(dev["diagnostic"]["spatial_blocks_degrees"]),
                    repeats=int(dev["diagnostic"]["repeats"]),
                    holdout_fraction=float(dev["diagnostic"]["holdout_fraction"]),
                    min_train=int(transfer["validation"]["minimum_training_prototypes"]),
                    seed=int(transfer["sampling"]["seed"]) + int(taxon_index) * 100,
                )
                if len(folds) != int(dev["diagnostic"]["repeats"]):
                    failures.append({"sample_id": int(taxon["sample_id"]), "scientific_name": name, "reason": f"only_{len(folds)}_valid_folds"})
                    continue

                for repeat_index, fold in enumerate(folds, start=1):
                    train = bench.attach_public_features(
                        fold["train"],
                        ndvi_transform=ndvi_transform,
                        ndvi_crs=ndvi_crs,
                        ndvi_surface_dict=ndvi_surface_dict,
                        micro_surfaces=micro_surfaces,
                        dem_map=dem_map,
                    )
                    _, ndvi_rank = fit_distance_rank(grid, train, NDVI_STATE)
                    _, joint_rank = fit_distance_rank(grid, train, JOINT_STATE)
                    hybrid_score = 0.90 * ndvi_rank + 0.10 * joint_rank
                    hybrid_order = np.argsort(hybrid_score, kind="mergesort")
                    ndvi_order = np.argsort(ndvi_rank, kind="mergesort")

                    # No score or selection below depends on held-out coordinates.
                    selected_cache = {}
                    for budget in budgets:
                        if budget > len(grid):
                            continue
                        hybrid = grid.iloc[hybrid_order[:budget]].copy()
                        ndvi = grid.iloc[ndvi_order[:budget]].copy()
                        selected_cache[budget] = (
                            hybrid,
                            ndvi,
                            selected_grid_distances_km(grid, hybrid),
                            selected_grid_distances_km(grid, ndvi),
                        )

                    held = fold["held"].copy()
                    held_eval = held.rename(columns={"lat": "latitude", "lon": "longitude"})
                    for budget, (hybrid, ndvi, hybrid_grid_d, ndvi_grid_d) in selected_cache.items():
                        for radius in radii:
                            hybrid_result = evaluate(hybrid, held_eval, radius)
                            ndvi_result = evaluate(ndvi, held_eval, radius)
                            random = fast_matched_random_success(
                                grid,
                                held_eval,
                                hybrid,
                                radius,
                                random_draws,
                                int(transfer["sampling"]["seed"]) + int(taxon_index) * 100000 + repeat_index * 1000 + budget + int(radius * 100),
                            )
                            rows.append(
                                {
                                    "sample_id": int(taxon["sample_id"]),
                                    "scientific_name": name,
                                    "repeat": repeat_index,
                                    "budget": int(budget),
                                    "radius_km": radius,
                                    "heldout_points": int(len(held)),
                                    "hybrid_recall": hybrid_result["recovered"] / len(held),
                                    "ndvi_recall": ndvi_result["recovered"] / len(held),
                                    "random_recall": float(random["mean_recovered"]) / len(held),
                                    "hybrid_grid_coverage": float(np.mean(hybrid_grid_d <= radius)),
                                    "ndvi_grid_coverage": float(np.mean(ndvi_grid_d <= radius)),
                                    "hybrid_selected_by_island": json.dumps({str(k): int(v) for k, v in hybrid.groupby("island").size().items()}, sort_keys=True),
                                }
                            )
            except Exception as exc:
                failures.append({"sample_id": int(taxon["sample_id"]), "scientific_name": name, "reason": f"{type(exc).__name__}: {exc}"})

    fold = pd.DataFrame(rows)
    if fold.empty:
        raise RuntimeError("No diagnostic folds completed")
    taxon = taxon_curve(fold)
    curve = summarize_curve(taxon)

    low_budget = curve[curve["budget"].le(80)].copy()
    positive_hybrid = low_budget[low_budget["hybrid_minus_random"].gt(0)]
    positive_ndvi = low_budget[low_budget["ndvi_minus_random"].gt(0)]
    saturation = curve[curve["random_recall"].ge(0.8)].sort_values(["radius_km", "budget"])
    summary = {
        "status": "development_only",
        "taxa_in_sample": int(len(sample)),
        "taxa_with_results": int(taxon["sample_id"].nunique()),
        "failures": failures,
        "budgets": budgets,
        "radii_km": radii,
        "low_budget_hybrid_positive_cells": int(len(positive_hybrid)),
        "low_budget_ndvi_positive_cells": int(len(positive_ndvi)),
        "best_hybrid_minus_random": curve.sort_values("hybrid_minus_random", ascending=False).head(1).to_dict("records")[0],
        "best_ndvi_minus_random": curve.sort_values("ndvi_minus_random", ascending=False).head(1).to_dict("records")[0],
        "first_random_saturation_by_radius": saturation.groupby("radius_km", as_index=False).first().to_dict("records"),
        "decision_rule": dev["decision_logic"],
        "frozen_192_consumed": False,
        "confirmation_claim": False,
    }

    args.out.mkdir(parents=True, exist_ok=True)
    fold.to_csv(args.out / "budget_fold_results.csv", index=False)
    taxon.to_csv(args.out / "budget_taxon_results.csv", index=False)
    curve.to_csv(args.out / "budget_curve.csv", index=False)
    (args.out / "diagnostic_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
