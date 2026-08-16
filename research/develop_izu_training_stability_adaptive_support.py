#!/usr/bin/env python3
"""Develop a training-only adaptive ecological-support rule for island surveys.

A fixed support quantile is not transferred across taxa.  This procedure chooses
support breadth inside each training fold using only thinned training occurrences:
each training prototype is omitted in turn, the remaining prototypes define an
NDVI-state support surface, and the smallest public-grid support quantile that
recovers a declared fraction of omitted training prototypes is used.  If the
training occurrences do not justify a narrow envelope, q=1 is selected and the
method reduces to pure geographic maximum coverage.

The inspected 16-taxon Izu cohort is development-only. Held-out occurrence
coordinates are not read until q and all candidate sets have been frozen.
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
from develop_izu_strong_coverage_comparator import build_geometry
from develop_izu_strong_coverage_sweep import greedy_coverage_order
from develop_izu_support_constrained_coverage import bootstrap_ci, sign_flip_p
from run_izu_microenvironment_random_taxa import retrieval_wkt

bench.island_wkt = retrieval_wkt


def _omitted_rank(grid_features: pd.DataFrame, remaining: pd.DataFrame, omitted: pd.DataFrame) -> float:
    """Return the omitted prototype's percentile rank against the public grid.

    The omitted row is appended only to obtain its environmental-distance rank;
    all inputs are training-fold data. Its single extra row changes the empirical
    percentile by <1/grid-size and cannot expose held-out outcomes.
    """
    probe = pd.concat(
        [grid_features[NDVI_STATE].reset_index(drop=True), omitted[NDVI_STATE].reset_index(drop=True)],
        ignore_index=True,
    )
    _, ranks = fit_distance_rank(probe, remaining, NDVI_STATE)
    return float(ranks[-1])


def choose_support_quantile(
    grid_features: pd.DataFrame,
    train_features: pd.DataFrame,
    quantiles: list[float],
    recovery_target: float,
) -> tuple[float, list[dict]]:
    """Choose the smallest q meeting training-only prototype LOO recovery."""
    quantiles = sorted(float(q) for q in quantiles)
    omitted_ranks: list[float] = []
    mask_jaccards: dict[float, list[float]] = {q: [] for q in quantiles}
    _, full_rank = fit_distance_rank(grid_features, train_features, NDVI_STATE)

    for i in range(len(train_features)):
        remaining = train_features.drop(train_features.index[i]).reset_index(drop=True)
        omitted = train_features.iloc[[i]].reset_index(drop=True)
        rank = _omitted_rank(grid_features, remaining, omitted)
        omitted_ranks.append(rank)
        _, loo_rank = fit_distance_rank(grid_features, remaining, NDVI_STATE)
        for q in quantiles:
            full_mask = full_rank <= q + 1e-12
            loo_mask = loo_rank <= q + 1e-12
            union = np.logical_or(full_mask, loo_mask).sum()
            inter = np.logical_and(full_mask, loo_mask).sum()
            mask_jaccards[q].append(float(inter / union) if union else 1.0)

    diagnostics = []
    selected = 1.0
    for q in quantiles:
        recovery = float(np.mean(np.asarray(omitted_ranks) <= q + 1e-12))
        stability = float(np.median(mask_jaccards[q])) if mask_jaccards[q] else np.nan
        diagnostics.append(
            {
                "support_quantile": q,
                "training_loo_environmental_recovery": recovery,
                "median_mask_jaccard": stability,
            }
        )
        if recovery >= float(recovery_target) and selected == 1.0:
            selected = q
    return float(selected), diagnostics


def paired_inference(taxon: pd.DataFrame, method: str, control: str, budget: int, seed: int) -> dict:
    left = taxon[(taxon["method"].eq(method)) & (taxon["budget"].eq(budget))][
        ["sample_id", "recall"]
    ]
    right = taxon[(taxon["method"].eq(control)) & (taxon["budget"].eq(budget))][
        ["sample_id", "recall"]
    ].rename(columns={"recall": "control_recall"})
    merged = left.merge(right, on="sample_id", how="inner")
    diff = (merged["recall"] - merged["control_recall"]).to_numpy(float)
    if len(diff) == 0:
        return {"method": method, "control": control, "budget": budget, "taxa": 0, "passes": False}
    ci = bootstrap_ci(diff, 10000, seed)
    p = sign_flip_p(diff, 50000, seed + 1)
    return {
        "method": method,
        "control": control,
        "budget": int(budget),
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
    method = protocol["method"]
    evaluation = protocol["evaluation"]
    quantiles = [float(q) for q in method["support_quantiles"]]
    target = float(method["loo_environmental_recovery_target"])
    budgets = [int(k) for k in method["budgets"]]
    radius = float(method["survey_radius_km"])
    max_budget = max(budgets)

    dem_map: dict[str, Path] = {}
    for spec in args.dem:
        island, path = spec.split("=", 1)
        dem_map[island] = Path(path)

    grid = bench.build_public_grid(dem_map)
    geometry = build_geometry(grid)
    global_order = greedy_coverage_order(
        grid,
        geometry,
        np.ones(len(grid), dtype=bool),
        max_budget=max_budget,
        radius_km=radius,
    )

    fold_rows: list[dict] = []
    q_rows: list[dict] = []
    failures: list[dict] = []

    with rasterio.open(args.ndvi) as src:
        ndvi_transform, ndvi_crs, ndvi_surfaces_dict = ndvi_surfaces(src, grid["lon"], grid["lat"])
        grid_features = bench.attach_public_features(
            grid,
            ndvi_transform=ndvi_transform,
            ndvi_crs=ndvi_crs,
            ndvi_surface_dict=ndvi_surfaces_dict,
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
                    block_degrees=float(evaluation["spatial_blocks_degrees"]),
                    repeats=int(evaluation["repeats"]),
                    holdout_fraction=float(evaluation["holdout_fraction"]),
                    min_train=int(evaluation["minimum_training_prototypes"]),
                    seed=int(transfer["sampling"]["seed"]) + int(taxon_index) * 100,
                )
                if len(folds) != int(evaluation["repeats"]):
                    failures.append(
                        {"sample_id": int(taxon["sample_id"]), "scientific_name": name, "reason": f"only_{len(folds)}_valid_folds"}
                    )
                    continue

                for repeat_index, fold in enumerate(folds, start=1):
                    train_features = bench.attach_public_features(
                        fold["train"],
                        ndvi_transform=ndvi_transform,
                        ndvi_crs=ndvi_crs,
                        ndvi_surface_dict=ndvi_surfaces_dict,
                        micro_surfaces={},
                        dem_map={},
                    )
                    selected_q, diagnostics = choose_support_quantile(
                        grid_features, train_features, quantiles, target
                    )
                    for diagnostic in diagnostics:
                        q_rows.append(
                            {
                                "sample_id": int(taxon["sample_id"]),
                                "scientific_name": name,
                                "repeat": repeat_index,
                                "selected_q": selected_q,
                                **diagnostic,
                            }
                        )

                    # Every support mask and set is frozen before held-out coordinates are inspected.
                    _, rank = fit_distance_rank(grid_features, train_features, NDVI_STATE)
                    adaptive_order = greedy_coverage_order(
                        grid,
                        geometry,
                        rank <= selected_q + 1e-12,
                        max_budget=max_budget,
                        radius_km=radius,
                    )
                    q10_order = greedy_coverage_order(
                        grid,
                        geometry,
                        rank <= 0.10 + 1e-12,
                        max_budget=max_budget,
                        radius_km=radius,
                    )
                    selections = {
                        "adaptive_training_stability": adaptive_order,
                        "fixed_q10": q10_order,
                        "global_max_coverage": global_order,
                    }

                    held = fold["held"].rename(columns={"lat": "latitude", "lon": "longitude"})
                    for budget in budgets:
                        for method_name, order in selections.items():
                            if len(order) < budget:
                                continue
                            selected = order.iloc[:budget].copy()
                            result = evaluate(selected, held, radius)
                            fold_rows.append(
                                {
                                    "sample_id": int(taxon["sample_id"]),
                                    "scientific_name": name,
                                    "repeat": repeat_index,
                                    "method": method_name,
                                    "budget": budget,
                                    "selected_q": selected_q if method_name == "adaptive_training_stability" else (0.10 if method_name == "fixed_q10" else 1.0),
                                    "heldout_points": int(len(held)),
                                    "recall": result["recovered"] / len(held),
                                }
                            )
            except Exception as exc:
                failures.append(
                    {"sample_id": int(taxon["sample_id"]), "scientific_name": name, "reason": f"{type(exc).__name__}: {exc}"}
                )

    fold = pd.DataFrame(fold_rows)
    if fold.empty:
        raise RuntimeError("No adaptive-support folds completed")
    taxon = (
        fold.groupby(["sample_id", "scientific_name", "method", "budget"], as_index=False)
        .agg(recall=("recall", "mean"), mean_selected_q=("selected_q", "mean"), folds=("repeat", "count"))
    )
    means = taxon.groupby(["method", "budget"], as_index=False).agg(
        mean_recall=("recall", "mean"), taxa=("sample_id", "nunique")
    )

    comparisons = []
    for i, budget in enumerate(budgets):
        comparisons.append(
            paired_inference(taxon, "adaptive_training_stability", "global_max_coverage", budget, 20260910 + i * 10)
        )
        comparisons.append(
            paired_inference(taxon, "adaptive_training_stability", "fixed_q10", budget, 20260911 + i * 10)
        )
    comparisons_df = pd.DataFrame(comparisons)
    q_diag = pd.DataFrame(q_rows)
    selected_q_counts = (
        q_diag[["sample_id", "repeat", "selected_q"]]
        .drop_duplicates()
        .groupby("selected_q")
        .size()
        .to_dict()
        if not q_diag.empty
        else {}
    )

    summary = {
        "status": "development_only",
        "taxa": int(taxon["sample_id"].nunique()),
        "failures": failures,
        "loo_environmental_recovery_target": target,
        "selected_q_fold_counts": {str(float(k)): int(v) for k, v in selected_q_counts.items()},
        "method_means": means.to_dict("records"),
        "comparisons": comparisons,
        "heldout_coordinates_used_to_choose_q": False,
        "campanula_field_coordinates_used": False,
        "frozen_192_consumed": False,
        "confirmation_claim": False,
    }

    args.out.mkdir(parents=True, exist_ok=True)
    fold.to_csv(args.out / "adaptive_support_fold_results.csv", index=False)
    taxon.to_csv(args.out / "adaptive_support_taxon_results.csv", index=False)
    means.to_csv(args.out / "adaptive_support_method_means.csv", index=False)
    comparisons_df.to_csv(args.out / "adaptive_support_comparisons.csv", index=False)
    q_diag.to_csv(args.out / "adaptive_support_training_diagnostics.csv", index=False)
    (args.out / "adaptive_support_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
