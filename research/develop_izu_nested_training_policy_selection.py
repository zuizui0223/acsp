#!/usr/bin/env python3
"""Select island survey support breadth by fully nested training-only recovery.

For each outer spatial holdout, support quantile q is selected only inside the
outer training data. Inner spatial holdouts score the complete downstream policy:
NDVI support mask followed by greedy maximum geographic coverage at the declared
survey budget and radius. Outer held-out coordinates are read only after q and
all outer candidate sets are frozen.
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


def make_orders(
    grid: pd.DataFrame,
    grid_features: pd.DataFrame,
    train_features: pd.DataFrame,
    geometry: dict[str, dict],
    quantiles: list[float],
    max_budget: int,
    radius: float,
) -> dict[float, pd.DataFrame]:
    _, support_rank = fit_distance_rank(grid_features, train_features, NDVI_STATE)
    orders: dict[float, pd.DataFrame] = {}
    for q in quantiles:
        eligible = np.ones(len(grid), dtype=bool) if q >= 1.0 else support_rank <= q + 1e-12
        orders[q] = greedy_coverage_order(
            grid,
            geometry,
            eligible,
            max_budget=max_budget,
            radius_km=radius,
        )
    return orders


def select_q_from_inner(
    grid: pd.DataFrame,
    grid_features: pd.DataFrame,
    outer_train: pd.DataFrame,
    geometry: dict[str, dict],
    *,
    quantiles: list[float],
    budgets: list[int],
    radius: float,
    transform,
    crs,
    surfaces,
    inner_cfg: dict,
    seed: int,
) -> tuple[dict[int, float], list[dict], str]:
    _, inner_folds = bench.make_folds(
        outer_train,
        block_degrees=float(inner_cfg["block_degrees"]),
        repeats=int(inner_cfg["repeats"]),
        holdout_fraction=float(inner_cfg["holdout_fraction"]),
        min_train=int(inner_cfg["minimum_training_prototypes"]),
        seed=int(seed),
    )
    if len(inner_folds) != int(inner_cfg["repeats"]):
        return {budget: 1.0 for budget in budgets}, [], "insufficient_inner_folds"

    max_budget = max(budgets)
    inner_rows: list[dict] = []
    for inner_index, fold in enumerate(inner_folds, start=1):
        train_features = bench.attach_public_features(
            fold["train"],
            ndvi_transform=transform,
            ndvi_crs=crs,
            ndvi_surface_dict=surfaces,
            micro_surfaces={},
            dem_map={},
        )
        orders = make_orders(
            grid,
            grid_features,
            train_features,
            geometry,
            quantiles,
            max_budget,
            radius,
        )
        held = fold["held"].rename(columns={"lat": "latitude", "lon": "longitude"})
        for q in quantiles:
            order = orders[q]
            for budget in budgets:
                if len(order) < budget:
                    continue
                result = evaluate(order.iloc[:budget], held, radius)
                inner_rows.append(
                    {
                        "inner_repeat": inner_index,
                        "support_quantile": float(q),
                        "budget": int(budget),
                        "heldout_points": int(len(held)),
                        "recall": result["recovered"] / len(held),
                    }
                )

    frame = pd.DataFrame(inner_rows)
    selected: dict[int, float] = {}
    diagnostics: list[dict] = []
    for budget in budgets:
        subset = frame[frame["budget"].eq(budget)]
        means = subset.groupby("support_quantile")["recall"].mean().to_dict()
        control = float(means.get(1.0, np.nan))
        candidates: list[tuple[float, float]] = []
        for q in sorted(float(x) for x in quantiles if x < 1.0):
            value = float(means.get(q, np.nan))
            lift = value - control if np.isfinite(value) and np.isfinite(control) else np.nan
            diagnostics.append(
                {
                    "budget": int(budget),
                    "support_quantile": q,
                    "inner_mean_recall": value,
                    "inner_control_recall": control,
                    "inner_lift_vs_q1": lift,
                }
            )
            if np.isfinite(lift) and lift > 0:
                candidates.append((lift, q))
        if not candidates:
            selected[budget] = 1.0
        else:
            # Highest positive lift; exact ties prefer broader support (larger q).
            candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
            selected[budget] = float(candidates[0][1])
    return selected, diagnostics, "ok"


def paired_inference(taxon: pd.DataFrame, method: str, control: str, budget: int, seed: int) -> dict:
    left = taxon[(taxon["method"].eq(method)) & (taxon["budget"].eq(budget))][["sample_id", "recall"]]
    right = taxon[(taxon["method"].eq(control)) & (taxon["budget"].eq(budget))][["sample_id", "recall"]].rename(columns={"recall": "control_recall"})
    merged = left.merge(right, on="sample_id", how="inner")
    diff = (merged["recall"] - merged["control_recall"]).to_numpy(float)
    if len(diff) == 0:
        return {"method": method, "control": control, "budget": int(budget), "taxa": 0, "passes": False}
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
    cfg = protocol["method"]
    sample = pd.read_csv(args.sample)
    quantiles = [float(x) for x in cfg["support_quantiles"]]
    budgets = [int(x) for x in cfg["budgets"]]
    radius = float(cfg["survey_radius_km"])
    outer_cfg = cfg["outer_folds"]
    inner_cfg = cfg["inner_folds"]
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
    inner_rows: list[dict] = []
    failures: list[dict] = []
    selection_failures = 0

    with rasterio.open(args.ndvi) as src:
        transform, crs, surfaces = ndvi_surfaces(src, grid["lon"], grid["lat"])
        grid_features = bench.attach_public_features(
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
                _, outer_folds = bench.make_folds(
                    occurrences,
                    block_degrees=float(outer_cfg["block_degrees"]),
                    repeats=int(outer_cfg["repeats"]),
                    holdout_fraction=float(outer_cfg["holdout_fraction"]),
                    min_train=int(outer_cfg["minimum_training_prototypes"]),
                    seed=int(transfer["sampling"]["seed"]) + int(taxon_index) * 100,
                )
                if len(outer_folds) != int(outer_cfg["repeats"]):
                    failures.append({"sample_id": int(taxon["sample_id"]), "scientific_name": name, "reason": f"only_{len(outer_folds)}_outer_folds"})
                    continue

                for outer_index, fold in enumerate(outer_folds, start=1):
                    selected_q, diagnostics, reason = select_q_from_inner(
                        grid,
                        grid_features,
                        fold["train"],
                        geometry,
                        quantiles=quantiles,
                        budgets=budgets,
                        radius=radius,
                        transform=transform,
                        crs=crs,
                        surfaces=surfaces,
                        inner_cfg=inner_cfg,
                        seed=int(transfer["sampling"]["seed"]) + int(taxon_index) * 10000 + outer_index * 100,
                    )
                    if reason != "ok":
                        selection_failures += 1
                    for row in diagnostics:
                        inner_rows.append(
                            {
                                "sample_id": int(taxon["sample_id"]),
                                "scientific_name": name,
                                "outer_repeat": outer_index,
                                "selection_reason": reason,
                                "selected_q": selected_q[int(row["budget"])],
                                **row,
                            }
                        )

                    outer_train_features = bench.attach_public_features(
                        fold["train"],
                        ndvi_transform=transform,
                        ndvi_crs=crs,
                        ndvi_surface_dict=surfaces,
                        micro_surfaces={},
                        dem_map={},
                    )
                    needed_q = sorted(set(selected_q.values()) | {0.10, 1.0})
                    orders = make_orders(
                        grid,
                        grid_features,
                        outer_train_features,
                        geometry,
                        needed_q,
                        max_budget,
                        radius,
                    )
                    # Outer held-out coordinates become visible only after every q and set is frozen.
                    held = fold["held"].rename(columns={"lat": "latitude", "lon": "longitude"})
                    for budget in budgets:
                        methods = {
                            "nested_training_selected": (selected_q[budget], orders[selected_q[budget]]),
                            "fixed_q10": (0.10, orders[0.10]),
                            "global_max_coverage": (1.0, global_order),
                        }
                        for method_name, (q, order) in methods.items():
                            if len(order) < budget:
                                continue
                            result = evaluate(order.iloc[:budget], held, radius)
                            fold_rows.append(
                                {
                                    "sample_id": int(taxon["sample_id"]),
                                    "scientific_name": name,
                                    "outer_repeat": outer_index,
                                    "method": method_name,
                                    "budget": int(budget),
                                    "selected_q": float(q),
                                    "selection_reason": reason,
                                    "heldout_points": int(len(held)),
                                    "recall": result["recovered"] / len(held),
                                }
                            )
            except Exception as exc:
                failures.append({"sample_id": int(taxon["sample_id"]), "scientific_name": name, "reason": f"{type(exc).__name__}: {exc}"})

    fold = pd.DataFrame(fold_rows)
    if fold.empty:
        raise RuntimeError("No nested policy-selection folds completed")
    taxon = (
        fold.groupby(["sample_id", "scientific_name", "method", "budget"], as_index=False)
        .agg(recall=("recall", "mean"), mean_selected_q=("selected_q", "mean"), folds=("outer_repeat", "count"))
    )
    means = taxon.groupby(["method", "budget"], as_index=False).agg(mean_recall=("recall", "mean"), taxa=("sample_id", "nunique"))
    comparisons = []
    for i, budget in enumerate(budgets):
        comparisons.append(paired_inference(taxon, "nested_training_selected", "global_max_coverage", budget, 20261010 + i * 10))
        comparisons.append(paired_inference(taxon, "nested_training_selected", "fixed_q10", budget, 20261011 + i * 10))

    selected_counts = (
        fold[fold["method"].eq("nested_training_selected")][["sample_id", "outer_repeat", "budget", "selected_q"]]
        .drop_duplicates()
        .groupby(["budget", "selected_q"])
        .size()
        .reset_index(name="folds")
        .to_dict("records")
    )
    summary = {
        "status": "development_only",
        "taxa": int(taxon["sample_id"].nunique()),
        "failures": failures,
        "inner_selection_fallback_outer_folds": int(selection_failures),
        "selected_q_counts": selected_counts,
        "method_means": means.to_dict("records"),
        "comparisons": comparisons,
        "outer_heldout_coordinates_used_to_select_q": False,
        "campanula_field_coordinates_used": False,
        "frozen_192_consumed": False,
        "confirmation_claim": False,
    }

    args.out.mkdir(parents=True, exist_ok=True)
    fold.to_csv(args.out / "nested_policy_outer_fold_results.csv", index=False)
    taxon.to_csv(args.out / "nested_policy_taxon_results.csv", index=False)
    means.to_csv(args.out / "nested_policy_method_means.csv", index=False)
    pd.DataFrame(inner_rows).to_csv(args.out / "nested_policy_inner_diagnostics.csv", index=False)
    pd.DataFrame(comparisons).to_csv(args.out / "nested_policy_comparisons.csv", index=False)
    (args.out / "nested_policy_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
