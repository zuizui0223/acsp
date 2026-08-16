#!/usr/bin/env python3
"""Strict v2 wrapper for nested training-only support-policy selection.

This file supersedes the v1 development run before its output is inspected.
It changes only inner q selection: a q must be feasible at the requested K in
every inner spatial fold, and its lift is computed pairwise against q=1 on the
same inner folds. Outer evaluation remains delegated to the v1 runner.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import benchmark_izu_microenvironment_random_taxa as bench
from campanula_ndvi_microclimate_hybrid import evaluate
import develop_izu_nested_training_policy_selection as base


def strict_select_q_from_inner(
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
    expected_repeats = int(inner_cfg["repeats"])
    _, inner_folds = bench.make_folds(
        outer_train,
        block_degrees=float(inner_cfg["block_degrees"]),
        repeats=expected_repeats,
        holdout_fraction=float(inner_cfg["holdout_fraction"]),
        min_train=int(inner_cfg["minimum_training_prototypes"]),
        seed=int(seed),
    )
    if len(inner_folds) != expected_repeats:
        return {budget: 1.0 for budget in budgets}, [], "insufficient_inner_folds"

    max_budget = max(budgets)
    rows: list[dict] = []
    for inner_index, fold in enumerate(inner_folds, start=1):
        train_features = bench.attach_public_features(
            fold["train"],
            ndvi_transform=transform,
            ndvi_crs=crs,
            ndvi_surface_dict=surfaces,
            micro_surfaces={},
            dem_map={},
        )
        orders = base.make_orders(
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
                feasible = len(order) >= budget
                recall = np.nan
                if feasible:
                    result = evaluate(order.iloc[:budget], held, radius)
                    recall = result["recovered"] / len(held)
                rows.append(
                    {
                        "inner_repeat": inner_index,
                        "support_quantile": float(q),
                        "budget": int(budget),
                        "feasible": bool(feasible),
                        "heldout_points": int(len(held)),
                        "recall": recall,
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
        for q in sorted(float(x) for x in quantiles if x < 1.0):
            candidate = subset[subset["support_quantile"].eq(q)][
                ["inner_repeat", "feasible", "recall"]
            ].rename(columns={"feasible": "candidate_feasible", "recall": "candidate_recall"})
            paired = candidate.merge(control, on="inner_repeat", how="inner")
            complete = bool(
                len(paired) == expected_repeats
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
            else:
                mean_recall = np.nan
                control_mean = float(paired["control_recall"].mean()) if len(paired) else np.nan
                lift = np.nan

            diagnostics.append(
                {
                    "budget": int(budget),
                    "support_quantile": q,
                    "inner_mean_recall": mean_recall,
                    "inner_control_recall": control_mean,
                    "inner_lift_vs_q1": lift,
                    "paired_complete_inner_folds": int(len(paired)) if complete else 0,
                    "q_feasible_all_inner_folds": complete,
                }
            )

        if not candidates:
            selected[budget] = 1.0
        else:
            candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
            selected[budget] = float(candidates[0][1])

    return selected, diagnostics, "ok"


if __name__ == "__main__":
    base.select_q_from_inner = strict_select_q_from_inner
    base.main()
