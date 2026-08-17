#!/usr/bin/env python3
"""Develop mode-balanced ecological support under the frozen ACSP set policy.

Only the ecological-support representation changes relative to strict nested
single-envelope development. Environmental variables, q values, spatial folds,
K budgets, 1 km survey radius, q=1 fallback, and greedy maximum-coverage set
selection are retained. Mode inference is training-only and reuses the historic
robust MST-gap rule without tuning it on outer outcomes.
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
from develop_izu_nested_training_policy_selection import paired_inference
from develop_izu_strong_coverage_comparator import build_geometry
from environmental_mode_support import multimodal_support_mask
from fast_max_coverage import greedy_coverage_order_fast
from run_izu_microenvironment_random_taxa import retrieval_wkt

bench.island_wkt = retrieval_wkt


def make_multimodal_orders(
    grid: pd.DataFrame,
    grid_features: pd.DataFrame,
    train_features: pd.DataFrame,
    geometry: dict[str, dict],
    quantiles: list[float],
    max_budget: int,
    radius: float,
    gap_multiplier: float,
) -> tuple[dict[float, pd.DataFrame], dict[float, dict]]:
    orders: dict[float, pd.DataFrame] = {}
    info: dict[float, dict] = {}
    for q in quantiles:
        mask, detail = multimodal_support_mask(
            grid_features,
            train_features,
            NDVI_STATE,
            q,
            gap_multiplier=gap_multiplier,
        )
        orders[q] = greedy_coverage_order_fast(
            grid,
            geometry,
            mask,
            max_budget=max_budget,
            radius_km=radius,
        )
        info[q] = detail
    return orders, info


def single_envelope_order(
    grid: pd.DataFrame,
    grid_features: pd.DataFrame,
    train_features: pd.DataFrame,
    geometry: dict[str, dict],
    *,
    q: float,
    max_budget: int,
    radius: float,
) -> pd.DataFrame:
    _, rank = fit_distance_rank(grid_features, train_features, NDVI_STATE)
    eligible = np.ones(len(grid), dtype=bool) if q >= 1.0 else rank <= q + 1e-12
    return greedy_coverage_order_fast(
        grid,
        geometry,
        eligible,
        max_budget=max_budget,
        radius_km=radius,
    )


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
    gap_multiplier: float,
    seed: int,
) -> tuple[dict[int, float], list[dict], str]:
    expected = int(inner_cfg["repeats"])
    _, folds = bench.make_folds(
        outer_train,
        block_degrees=float(inner_cfg["block_degrees"]),
        repeats=expected,
        holdout_fraction=float(inner_cfg["holdout_fraction"]),
        min_train=int(inner_cfg["minimum_training_prototypes"]),
        seed=int(seed),
    )
    if len(folds) != expected:
        return {budget: 1.0 for budget in budgets}, [], "insufficient_inner_folds"

    max_budget = max(budgets)
    rows: list[dict] = []
    for inner_repeat, fold in enumerate(folds, start=1):
        train_features = bench.attach_public_features(
            fold["train"],
            ndvi_transform=transform,
            ndvi_crs=crs,
            ndvi_surface_dict=surfaces,
            micro_surfaces={},
            dem_map={},
        )
        orders, details = make_multimodal_orders(
            grid,
            grid_features,
            train_features,
            geometry,
            quantiles,
            max_budget,
            radius,
            gap_multiplier,
        )
        held = fold["held"].rename(columns={"lat": "latitude", "lon": "longitude"})
        for q in quantiles:
            order = orders[q]
            detail = details[q]
            for budget in budgets:
                feasible = len(order) >= budget
                recall = np.nan
                if feasible:
                    result = evaluate(order.iloc[:budget], held, radius)
                    recall = result["recovered"] / len(held)
                rows.append(
                    {
                        "inner_repeat": inner_repeat,
                        "support_quantile": float(q),
                        "budget": int(budget),
                        "feasible": bool(feasible),
                        "heldout_points": int(len(held)),
                        "recall": recall,
                        "component_count": int(detail["component_count"]),
                        "component_sizes": json.dumps(detail["component_sizes"]),
                        "gap_strength": float(detail["gap_strength"]),
                        "support_cells": int(detail["target_cells"]),
                    }
                )

    frame = pd.DataFrame(rows)
    selected: dict[int, float] = {}
    diagnostics: list[dict] = []
    for budget in budgets:
        subset = frame[frame["budget"].eq(budget)].copy()
        control = subset[subset["support_quantile"].eq(1.0)][
            ["inner_repeat", "feasible", "recall"]
        ].rename(columns={"feasible": "control_feasible", "recall": "control_recall"})
        candidates: list[tuple[float, float]] = []
        for q in sorted(float(value) for value in quantiles if value < 1.0):
            candidate = subset[subset["support_quantile"].eq(q)][
                ["inner_repeat", "feasible", "recall", "component_count", "component_sizes", "gap_strength", "support_cells"]
            ].rename(columns={"feasible": "candidate_feasible", "recall": "candidate_recall"})
            paired = candidate.merge(control, on="inner_repeat", how="inner")
            complete = bool(
                len(paired) == expected
                and paired["candidate_feasible"].all()
                and paired["control_feasible"].all()
                and paired["candidate_recall"].notna().all()
                and paired["control_recall"].notna().all()
            )
            if complete:
                diffs = (paired["candidate_recall"] - paired["control_recall"]).to_numpy(float)
                mean_recall = float(paired["candidate_recall"].mean())
                control_mean = float(paired["control_recall"].mean())
                lift = float(diffs.mean())
                if lift > 0:
                    candidates.append((lift, q))
                mode_count = float(paired["component_count"].mean())
                gap_strength = float(paired["gap_strength"].mean())
                support_cells = float(paired["support_cells"].mean())
            else:
                mean_recall = np.nan
                control_mean = float(paired["control_recall"].mean()) if len(paired) else np.nan
                lift = np.nan
                mode_count = np.nan
                gap_strength = np.nan
                support_cells = np.nan
            diagnostics.append(
                {
                    "budget": int(budget),
                    "support_quantile": q,
                    "inner_mean_recall": mean_recall,
                    "inner_control_recall": control_mean,
                    "inner_lift_vs_q1": lift,
                    "paired_complete_inner_folds": int(len(paired)) if complete else 0,
                    "q_feasible_all_inner_folds": complete,
                    "mean_component_count": mode_count,
                    "mean_gap_strength": gap_strength,
                    "mean_support_cells": support_cells,
                }
            )
        if not candidates:
            selected[budget] = 1.0
        else:
            candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
            selected[budget] = float(candidates[0][1])
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
    multimodal = protocol["multimodal_representation"]
    sample = pd.read_csv(args.sample)
    quantiles = [float(x) for x in cfg["support_quantiles"]]
    budgets = [int(x) for x in cfg["budgets"]]
    radius = float(cfg["survey_radius_km"])
    gap_multiplier = float(multimodal["gap_multiplier"])
    outer_cfg = cfg["outer_folds"]
    inner_cfg = cfg["inner_folds"]
    max_budget = max(budgets)

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
        max_budget=max_budget,
        radius_km=radius,
    )

    outer_rows: list[dict] = []
    inner_rows: list[dict] = []
    failures: list[dict] = []
    selection_fallbacks = 0

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

                for outer_repeat, fold in enumerate(outer_folds, start=1):
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
                        gap_multiplier=gap_multiplier,
                        seed=int(transfer["sampling"]["seed"]) + int(taxon_index) * 10000 + outer_repeat * 100,
                    )
                    if reason != "ok":
                        selection_fallbacks += 1
                    for row in diagnostics:
                        inner_rows.append(
                            {
                                "sample_id": int(taxon["sample_id"]),
                                "scientific_name": name,
                                "outer_repeat": outer_repeat,
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
                    mode_orders, mode_info = make_multimodal_orders(
                        grid,
                        grid_features,
                        outer_train_features,
                        geometry,
                        needed_q,
                        max_budget,
                        radius,
                        gap_multiplier,
                    )
                    single_q10 = single_envelope_order(
                        grid,
                        grid_features,
                        outer_train_features,
                        geometry,
                        q=0.10,
                        max_budget=max_budget,
                        radius=radius,
                    )

                    # Every representation, q and site set is frozen before this line.
                    held = fold["held"].rename(columns={"lat": "latitude", "lon": "longitude"})
                    for budget in budgets:
                        methods = {
                            "multimodal_nested_selected": (selected_q[budget], mode_orders[selected_q[budget]], mode_info[selected_q[budget]]),
                            "multimodal_fixed_q10": (0.10, mode_orders[0.10], mode_info[0.10]),
                            "single_fixed_q10": (0.10, single_q10, mode_info[0.10]),
                            "global_max_coverage": (1.0, global_order, mode_info[1.0]),
                        }
                        for method_name, (q, order, detail) in methods.items():
                            if len(order) < budget:
                                continue
                            result = evaluate(order.iloc[:budget], held, radius)
                            outer_rows.append(
                                {
                                    "sample_id": int(taxon["sample_id"]),
                                    "scientific_name": name,
                                    "outer_repeat": outer_repeat,
                                    "method": method_name,
                                    "budget": int(budget),
                                    "selected_q": float(q),
                                    "selection_reason": reason,
                                    "heldout_points": int(len(held)),
                                    "recall": result["recovered"] / len(held),
                                    "component_count": int(detail["component_count"]),
                                    "component_sizes": json.dumps(detail["component_sizes"]),
                                    "gap_strength": float(detail["gap_strength"]),
                                }
                            )
            except Exception as exc:
                failures.append({"sample_id": int(taxon["sample_id"]), "scientific_name": name, "reason": f"{type(exc).__name__}: {exc}"})

    outer = pd.DataFrame(outer_rows)
    if outer.empty:
        raise RuntimeError("No multimodal outer folds completed")
    taxon = (
        outer.groupby(["sample_id", "scientific_name", "method", "budget"], as_index=False)
        .agg(
            recall=("recall", "mean"),
            mean_selected_q=("selected_q", "mean"),
            mean_component_count=("component_count", "mean"),
            folds=("outer_repeat", "count"),
        )
    )
    means = taxon.groupby(["method", "budget"], as_index=False).agg(
        mean_recall=("recall", "mean"), taxa=("sample_id", "nunique")
    )

    comparisons = []
    for i, budget in enumerate(budgets):
        comparisons.append(paired_inference(taxon, "multimodal_nested_selected", "global_max_coverage", budget, 20261110 + i * 20))
        comparisons.append(paired_inference(taxon, "multimodal_nested_selected", "single_fixed_q10", budget, 20261111 + i * 20))
        comparisons.append(paired_inference(taxon, "multimodal_fixed_q10", "single_fixed_q10", budget, 20261112 + i * 20))

    selected_counts = (
        outer[outer["method"].eq("multimodal_nested_selected")][["sample_id", "outer_repeat", "budget", "selected_q"]]
        .drop_duplicates()
        .groupby(["budget", "selected_q"])
        .size()
        .reset_index(name="folds")
        .to_dict("records")
    )
    outer_modes = (
        outer[outer["method"].eq("multimodal_nested_selected")][["sample_id", "outer_repeat", "component_count"]]
        .drop_duplicates()
    )
    mode_distribution = outer_modes.groupby("component_count").size().to_dict()

    summary = {
        "status": "development_only",
        "protocol_id": protocol["protocol_id"],
        "taxa": int(taxon["sample_id"].nunique()),
        "failures": failures,
        "inner_selection_fallback_outer_folds": int(selection_fallbacks),
        "selected_q_counts": selected_counts,
        "outer_component_count_distribution": {str(int(k)): int(v) for k, v in mode_distribution.items()},
        "method_means": means.to_dict("records"),
        "comparisons": comparisons,
        "outer_heldout_coordinates_used_to_select_q_or_modes": False,
        "campanula_field_coordinates_used": False,
        "frozen_192_consumed": False,
        "confirmation_claim": False,
    }

    args.out.mkdir(parents=True, exist_ok=True)
    outer.to_csv(args.out / "multimodal_outer_fold_results.csv", index=False)
    taxon.to_csv(args.out / "multimodal_taxon_results.csv", index=False)
    means.to_csv(args.out / "multimodal_method_means.csv", index=False)
    pd.DataFrame(inner_rows).to_csv(args.out / "multimodal_inner_diagnostics.csv", index=False)
    pd.DataFrame(comparisons).to_csv(args.out / "multimodal_comparisons.csv", index=False)
    (args.out / "multimodal_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
