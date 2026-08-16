#!/usr/bin/env python3
"""Fully nested development of NDVI spatial aggregation scale.

Only the spatial view of the existing NDVI state changes.  Support footprint,
q values, occurrence thinning, outer/inner spatial folds, survey budgets,
1 km radius and the exact set-level maximum-coverage selector are retained.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

import benchmark_izu_microenvironment_random_taxa as bench
from campanula_ndvi_microclimate_hybrid import evaluate
from develop_izu_nested_training_policy_selection import paired_inference
from develop_izu_strong_coverage_comparator import build_geometry
from fast_max_coverage import greedy_coverage_order_fast
from run_izu_microenvironment_random_taxa import retrieval_wkt
from spatial_ndvi_support_scale import (
    SpatialScaleFamily,
    VIEW_COLUMNS,
    VIEW_TIE_PRIORITY,
    ndvi_surfaces_with_scale_views,
)

bench.island_wkt = retrieval_wkt


def make_orders(
    grid: pd.DataFrame,
    grid_features: pd.DataFrame,
    train_features: pd.DataFrame,
    geometry: dict[str, dict],
    views: list[str],
    quantiles: list[float],
    max_budget: int,
    radius: float,
):
    family = SpatialScaleFamily.build(grid_features, train_features)
    orders: dict[tuple[str, float], pd.DataFrame] = {}
    details: dict[tuple[str, float], dict] = {}
    control_key = ("current_multiscale", 1.0)
    control_mask = family.mask(*control_key)
    orders[control_key] = greedy_coverage_order_fast(
        grid, geometry, control_mask, max_budget=max_budget, radius_km=radius
    )
    details[control_key] = family.detail(*control_key)
    for q in quantiles:
        if q >= 1.0:
            continue
        for view in views:
            key = (view, float(q))
            try:
                mask = family.mask(view, q)
                orders[key] = greedy_coverage_order_fast(
                    grid, geometry, mask, max_budget=max_budget, radius_km=radius
                )
                details[key] = family.detail(view, q)
            except RuntimeError as exc:
                orders[key] = grid.iloc[0:0].copy()
                details[key] = {
                    "scale_view": view,
                    "support_quantile": float(q),
                    "support_cells": 0,
                    "baseline_target_cells": family.target_count(q),
                    "error": str(exc),
                }
    return orders, details


def select_policy_from_inner(
    grid,
    grid_features,
    outer_train,
    geometry,
    *,
    views,
    quantiles,
    budgets,
    radius,
    transform,
    crs,
    surfaces,
    inner_cfg,
    seed,
):
    expected = int(inner_cfg["repeats"])
    _, folds = bench.make_folds(
        outer_train,
        block_degrees=float(inner_cfg["block_degrees"]),
        repeats=expected,
        holdout_fraction=float(inner_cfg["holdout_fraction"]),
        min_train=int(inner_cfg["minimum_training_prototypes"]),
        seed=int(seed),
    )
    fallback = ("current_multiscale", 1.0)
    if len(folds) != expected:
        return {budget: fallback for budget in budgets}, [], "insufficient_inner_folds"

    rows: list[dict] = []
    policies = [fallback] + [
        (view, float(q))
        for q in quantiles
        if q < 1.0
        for view in views
    ]
    for inner_repeat, fold in enumerate(folds, start=1):
        train_features = bench.attach_public_features(
            fold["train"],
            ndvi_transform=transform,
            ndvi_crs=crs,
            ndvi_surface_dict=surfaces,
            micro_surfaces={},
            dem_map={},
        )
        orders, details = make_orders(
            grid,
            grid_features,
            train_features,
            geometry,
            views,
            quantiles,
            max(budgets),
            radius,
        )
        held = fold["held"].rename(columns={"lat": "latitude", "lon": "longitude"})
        for view, q in policies:
            order = orders[(view, q)]
            detail = details[(view, q)]
            for budget in budgets:
                feasible = len(order) >= budget
                recall = np.nan
                if feasible:
                    recall = evaluate(order.iloc[:budget], held, radius)["recovered"] / len(held)
                rows.append(
                    {
                        "inner_repeat": inner_repeat,
                        "scale_view": view,
                        "q": float(q),
                        "budget": int(budget),
                        "feasible": bool(feasible),
                        "recall": recall,
                        "support_cells": int(detail.get("support_cells", 0)),
                    }
                )

    frame = pd.DataFrame(rows)
    selected: dict[int, tuple[str, float]] = {}
    diagnostics: list[dict] = []
    for budget in budgets:
        subset = frame[frame["budget"].eq(budget)]
        control = subset[
            subset["scale_view"].eq("current_multiscale") & subset["q"].eq(1.0)
        ][["inner_repeat", "feasible", "recall"]].rename(
            columns={"feasible": "control_feasible", "recall": "control_recall"}
        )
        candidates: list[tuple[float, float, int, str]] = []
        for q in sorted(value for value in quantiles if value < 1.0):
            for view in views:
                candidate = subset[
                    subset["scale_view"].eq(view) & subset["q"].eq(q)
                ][["inner_repeat", "feasible", "recall", "support_cells"]].rename(
                    columns={"feasible": "candidate_feasible", "recall": "candidate_recall"}
                )
                paired = candidate.merge(control, on="inner_repeat", how="inner")
                complete = bool(
                    len(paired) == expected
                    and paired["candidate_feasible"].all()
                    and paired["control_feasible"].all()
                    and paired["candidate_recall"].notna().all()
                    and paired["control_recall"].notna().all()
                )
                lift = np.nan
                mean_recall = np.nan
                control_mean = np.nan
                support_cells = np.nan
                if complete:
                    lift = float(
                        (paired["candidate_recall"] - paired["control_recall"]).mean()
                    )
                    mean_recall = float(paired["candidate_recall"].mean())
                    control_mean = float(paired["control_recall"].mean())
                    support_cells = float(paired["support_cells"].mean())
                    if lift > 0:
                        candidates.append(
                            (lift, float(q), int(VIEW_TIE_PRIORITY[view]), view)
                        )
                diagnostics.append(
                    {
                        "budget": int(budget),
                        "scale_view": view,
                        "q": float(q),
                        "inner_mean_recall": mean_recall,
                        "inner_control_recall": control_mean,
                        "inner_lift_vs_q1": lift,
                        "complete_inner_folds": int(len(paired)) if complete else 0,
                        "feasible_all_inner_folds": complete,
                        "mean_support_cells": support_cells,
                    }
                )
        if not candidates:
            selected[budget] = fallback
        else:
            # max lift; exact ties broader q, then predeclared view priority.
            best = max(candidates, key=lambda item: (item[0], item[1], item[2]))
            selected[budget] = (best[3], best[1])
    return selected, diagnostics, "ok"


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
    cfg = protocol["retained_layers"]
    views = list(protocol["scale_views"].keys())
    quantiles = [float(x) for x in cfg["support_quantiles"]]
    budgets = [int(x) for x in cfg["budgets"]]
    radius = float(cfg["survey_radius_km"])
    outer_cfg = cfg["outer_folds"]
    inner_cfg = cfg["inner_folds"]
    sample = pd.read_csv(args.sample)

    if set(views) != set(VIEW_COLUMNS):
        raise RuntimeError("protocol spatial views differ from frozen implementation")
    for view, columns in protocol["scale_views"].items():
        if list(columns) != list(VIEW_COLUMNS[view]):
            raise RuntimeError(f"protocol feature list differs for {view}")

    dem_map: dict[str, Path] = {}
    for spec in args.dem:
        island, path = spec.split("=", 1)
        dem_map[island] = Path(path)

    grid = bench.build_public_grid(dem_map)
    geometry = build_geometry(grid)
    global_order = greedy_coverage_order_fast(
        grid,
        geometry,
        np.ones(len(grid), dtype=bool),
        max_budget=max(budgets),
        radius_km=radius,
    )

    outer_rows: list[dict] = []
    inner_rows: list[dict] = []
    failures: list[dict] = []
    fallbacks = 0

    with rasterio.open(args.ndvi) as src:
        transform, crs, surfaces = ndvi_surfaces_with_scale_views(
            src, grid["lon"], grid["lat"]
        )
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
                    failures.append(
                        {
                            "sample_id": int(taxon["sample_id"]),
                            "scientific_name": name,
                            "reason": f"only_{len(outer_folds)}_outer_folds",
                        }
                    )
                    continue

                for outer_repeat, fold in enumerate(outer_folds, start=1):
                    selected, diagnostics, reason = select_policy_from_inner(
                        grid,
                        grid_features,
                        fold["train"],
                        geometry,
                        views=views,
                        quantiles=quantiles,
                        budgets=budgets,
                        radius=radius,
                        transform=transform,
                        crs=crs,
                        surfaces=surfaces,
                        inner_cfg=inner_cfg,
                        seed=int(transfer["sampling"]["seed"])
                        + int(taxon_index) * 10000
                        + outer_repeat * 100,
                    )
                    if reason != "ok":
                        fallbacks += 1
                    for row in diagnostics:
                        inner_rows.append(
                            {
                                "sample_id": int(taxon["sample_id"]),
                                "scientific_name": name,
                                "outer_repeat": outer_repeat,
                                "selection_reason": reason,
                                **row,
                            }
                        )

                    train_features = bench.attach_public_features(
                        fold["train"],
                        ndvi_transform=transform,
                        ndvi_crs=crs,
                        ndvi_surface_dict=surfaces,
                        micro_surfaces={},
                        dem_map={},
                    )
                    needed = {
                        ("current_multiscale", 1.0),
                        ("current_multiscale", 0.10),
                        ("point", 0.10),
                        ("local100", 0.10),
                        ("local250", 0.10),
                    } | set(selected.values())
                    family = SpatialScaleFamily.build(grid_features, train_features)
                    orders: dict[tuple[str, float], pd.DataFrame] = {}
                    for policy in needed:
                        view, q = policy
                        if policy == ("current_multiscale", 1.0):
                            orders[policy] = global_order
                        else:
                            mask = family.mask(view, q)
                            orders[policy] = greedy_coverage_order_fast(
                                grid,
                                geometry,
                                mask,
                                max_budget=max(budgets),
                                radius_km=radius,
                            )

                    # Outer held-out coordinates become visible only after every
                    # scale/q policy and selected site set is frozen.
                    held = fold["held"].rename(
                        columns={"lat": "latitude", "lon": "longitude"}
                    )
                    for budget in budgets:
                        methods = {
                            "spatial_scale_nested_selected": selected[budget],
                            "current_multiscale_fixed_q10": ("current_multiscale", 0.10),
                            "point_fixed_q10": ("point", 0.10),
                            "local100_fixed_q10": ("local100", 0.10),
                            "local250_fixed_q10": ("local250", 0.10),
                            "global_max_coverage": ("current_multiscale", 1.0),
                        }
                        for method, policy in methods.items():
                            order = orders[policy]
                            if len(order) < budget:
                                continue
                            recall = evaluate(order.iloc[:budget], held, radius)["recovered"] / len(held)
                            outer_rows.append(
                                {
                                    "sample_id": int(taxon["sample_id"]),
                                    "scientific_name": name,
                                    "outer_repeat": outer_repeat,
                                    "method": method,
                                    "budget": int(budget),
                                    "selected_scale": policy[0],
                                    "selected_q": float(policy[1]),
                                    "heldout_points": int(len(held)),
                                    "recall": recall,
                                    "selection_reason": reason,
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

    outer = pd.DataFrame(outer_rows)
    if outer.empty:
        raise RuntimeError("No spatial-support-scale outer folds completed")
    taxon = (
        outer.groupby(["sample_id", "scientific_name", "method", "budget"], as_index=False)
        .agg(recall=("recall", "mean"), folds=("outer_repeat", "count"))
    )
    means = taxon.groupby(["method", "budget"], as_index=False).agg(
        mean_recall=("recall", "mean"), taxa=("sample_id", "nunique")
    )

    comparisons = []
    for i, budget in enumerate(budgets):
        comparisons.extend(
            [
                paired_inference(
                    taxon,
                    "spatial_scale_nested_selected",
                    "global_max_coverage",
                    budget,
                    20261310 + i * 30,
                ),
                paired_inference(
                    taxon,
                    "spatial_scale_nested_selected",
                    "current_multiscale_fixed_q10",
                    budget,
                    20261311 + i * 30,
                ),
                paired_inference(
                    taxon,
                    "point_fixed_q10",
                    "current_multiscale_fixed_q10",
                    budget,
                    20261312 + i * 30,
                ),
                paired_inference(
                    taxon,
                    "local100_fixed_q10",
                    "current_multiscale_fixed_q10",
                    budget,
                    20261313 + i * 30,
                ),
                paired_inference(
                    taxon,
                    "local250_fixed_q10",
                    "current_multiscale_fixed_q10",
                    budget,
                    20261314 + i * 30,
                ),
            ]
        )

    selected_counts = (
        outer[outer["method"].eq("spatial_scale_nested_selected")][
            ["sample_id", "outer_repeat", "budget", "selected_scale", "selected_q"]
        ]
        .drop_duplicates()
        .groupby(["budget", "selected_scale", "selected_q"])
        .size()
        .reset_index(name="folds")
        .to_dict("records")
    )

    summary = {
        "status": "development_only",
        "protocol_id": protocol["protocol_id"],
        "taxa": int(taxon["sample_id"].nunique()),
        "failures": failures,
        "inner_selection_fallback_outer_folds": int(fallbacks),
        "selected_policy_counts": selected_counts,
        "method_means": means.to_dict("records"),
        "comparisons": comparisons,
        "outer_heldout_coordinates_used_to_select_policy": False,
        "campanula_field_coordinates_used": False,
        "frozen_192_consumed": False,
        "confirmation_claim": False,
    }

    args.out.mkdir(parents=True, exist_ok=True)
    outer.to_csv(args.out / "spatial_scale_outer_fold_results.csv", index=False)
    taxon.to_csv(args.out / "spatial_scale_taxon_results.csv", index=False)
    means.to_csv(args.out / "spatial_scale_method_means.csv", index=False)
    pd.DataFrame(inner_rows).to_csv(
        args.out / "spatial_scale_inner_diagnostics.csv", index=False
    )
    pd.DataFrame(comparisons).to_csv(
        args.out / "spatial_scale_comparisons.csv", index=False
    )
    (args.out / "spatial_scale_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
