#!/usr/bin/env python3
"""Fully nested development of local prototype-agreement support scale.

Only support representation changes. Candidate universe, NDVI-state features,
q values, spatial folds, budgets, 1 km radius and exact max-coverage set
selection are retained. Inner spatial holdouts choose (k,q); outer held-out
coordinates remain invisible until the policy is frozen.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

import benchmark_izu_microenvironment_random_taxa as bench
from campanula_ndvi_microclimate_hybrid import NDVI_STATE, evaluate
from campanula_ndvi_transition_discovery import ndvi_surfaces
from develop_izu_nested_training_policy_selection import paired_inference
from develop_izu_strong_coverage_comparator import build_geometry
from fast_max_coverage import greedy_coverage_order_fast
from local_prototype_support_scale import LocalScaleFamily
from run_izu_microenvironment_random_taxa import retrieval_wkt

bench.island_wkt = retrieval_wkt


def make_orders(grid, grid_features, train_features, geometry, ks, qs, max_budget, radius):
    family = LocalScaleFamily.build(grid_features, train_features, NDVI_STATE, ks)
    orders = {}
    details = {}
    for q in qs:
        if q >= 1.0:
            key = (1, 1.0)
            if key not in orders:
                mask = family.mask(1, 1.0)
                orders[key] = greedy_coverage_order_fast(grid, geometry, mask, max_budget=max_budget, radius_km=radius)
                details[key] = family.detail(1, 1.0)
            continue
        for k in ks:
            key = (int(k), float(q))
            mask = family.mask(k, q)
            orders[key] = greedy_coverage_order_fast(grid, geometry, mask, max_budget=max_budget, radius_km=radius)
            details[key] = family.detail(k, q)
    return orders, details


def select_policy_from_inner(grid, grid_features, outer_train, geometry, *, ks, qs, budgets, radius, transform, crs, surfaces, inner_cfg, seed):
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
        return {b: (1, 1.0) for b in budgets}, [], "insufficient_inner_folds"

    rows = []
    for rep, fold in enumerate(folds, start=1):
        train_features = bench.attach_public_features(
            fold["train"], ndvi_transform=transform, ndvi_crs=crs,
            ndvi_surface_dict=surfaces, micro_surfaces={}, dem_map={}
        )
        orders, details = make_orders(grid, grid_features, train_features, geometry, ks, qs, max(budgets), radius)
        held = fold["held"].rename(columns={"lat": "latitude", "lon": "longitude"})
        policies = [(1, 1.0)] + [(k, q) for k in ks for q in qs if q < 1.0]
        for k, q in policies:
            order = orders[(k, q)]
            for budget in budgets:
                feasible = len(order) >= budget
                recall = np.nan
                if feasible:
                    recall = evaluate(order.iloc[:budget], held, radius)["recovered"] / len(held)
                rows.append({
                    "inner_repeat": rep, "k": int(k), "q": float(q), "budget": int(budget),
                    "feasible": bool(feasible), "recall": recall,
                    "support_cells": int(details[(k, q)]["support_cells"]),
                })

    frame = pd.DataFrame(rows)
    selected = {}
    diagnostics = []
    for budget in budgets:
        sub = frame[frame["budget"].eq(budget)]
        control = sub[(sub["k"].eq(1)) & (sub["q"].eq(1.0))][["inner_repeat", "feasible", "recall"]].rename(
            columns={"feasible": "control_feasible", "recall": "control_recall"}
        )
        candidates = []
        for k in ks:
            for q in sorted(x for x in qs if x < 1.0):
                cand = sub[(sub["k"].eq(k)) & (sub["q"].eq(q))][["inner_repeat", "feasible", "recall", "support_cells"]].rename(
                    columns={"feasible": "candidate_feasible", "recall": "candidate_recall"}
                )
                paired = cand.merge(control, on="inner_repeat", how="inner")
                complete = bool(
                    len(paired) == expected and paired["candidate_feasible"].all()
                    and paired["control_feasible"].all() and paired["candidate_recall"].notna().all()
                    and paired["control_recall"].notna().all()
                )
                lift = np.nan
                mean_recall = np.nan
                control_mean = np.nan
                support_cells = np.nan
                if complete:
                    lift = float((paired["candidate_recall"] - paired["control_recall"]).mean())
                    mean_recall = float(paired["candidate_recall"].mean())
                    control_mean = float(paired["control_recall"].mean())
                    support_cells = float(paired["support_cells"].mean())
                    if lift > 0:
                        candidates.append((lift, float(q), -int(k), int(k), float(q)))
                diagnostics.append({
                    "budget": int(budget), "k": int(k), "q": float(q),
                    "inner_mean_recall": mean_recall, "inner_control_recall": control_mean,
                    "inner_lift_vs_q1": lift, "complete_inner_folds": int(len(paired)) if complete else 0,
                    "feasible_all_inner_folds": complete, "mean_support_cells": support_cells,
                })
        if not candidates:
            selected[budget] = (1, 1.0)
        else:
            # max lift; exact ties broader q, then smaller k.
            candidates.sort(reverse=True)
            selected[budget] = (int(candidates[0][3]), float(candidates[0][4]))
    return selected, diagnostics, "ok"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--protocol", type=Path, required=True)
    p.add_argument("--transfer-protocol", type=Path, required=True)
    p.add_argument("--sample", type=Path, required=True)
    p.add_argument("--ndvi", type=Path, required=True)
    p.add_argument("--dem", action="append", required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    protocol = json.loads(args.protocol.read_text())
    transfer = json.loads(args.transfer_protocol.read_text())
    cfg = protocol["retained_layers"]
    ks = [int(x) for x in protocol["support_scale"]["prototype_neighbour_counts"]]
    qs = [float(x) for x in cfg["support_quantiles"]]
    budgets = [int(x) for x in cfg["budgets"]]
    radius = float(cfg["survey_radius_km"])
    outer_cfg, inner_cfg = cfg["outer_folds"], cfg["inner_folds"]
    sample = pd.read_csv(args.sample)
    dem_map = {}
    for spec in args.dem:
        island, path = spec.split("=", 1); dem_map[island] = Path(path)

    grid = bench.build_public_grid(dem_map)
    geometry = build_geometry(grid)
    global_order = greedy_coverage_order_fast(grid, geometry, np.ones(len(grid), dtype=bool), max_budget=max(budgets), radius_km=radius)
    outer_rows, inner_rows, failures = [], [], []
    fallbacks = 0

    with rasterio.open(args.ndvi) as src:
        tr, crs, surfaces = ndvi_surfaces(src, grid["lon"], grid["lat"])
        grid_features = bench.attach_public_features(grid, ndvi_transform=tr, ndvi_crs=crs, ndvi_surface_dict=surfaces, micro_surfaces={}, dem_map={})
        for taxon_index, taxon in sample.iterrows():
            try:
                occurrences = bench.fetch_occurrences(int(taxon["speciesKey"]), int(transfer["occurrences"]["max_records_per_taxon"]))
                _, outer_folds = bench.make_folds(
                    occurrences, block_degrees=float(outer_cfg["block_degrees"]), repeats=int(outer_cfg["repeats"]),
                    holdout_fraction=float(outer_cfg["holdout_fraction"]), min_train=int(outer_cfg["minimum_training_prototypes"]),
                    seed=int(transfer["sampling"]["seed"]) + int(taxon_index) * 100,
                )
                if len(outer_folds) != int(outer_cfg["repeats"]):
                    failures.append({"sample_id": int(taxon["sample_id"]), "scientific_name": str(taxon["scientific_name"]), "reason": f"only_{len(outer_folds)}_outer_folds"})
                    continue
                for outer_rep, fold in enumerate(outer_folds, start=1):
                    selected, diag, reason = select_policy_from_inner(
                        grid, grid_features, fold["train"], geometry, ks=ks, qs=qs, budgets=budgets, radius=radius,
                        transform=tr, crs=crs, surfaces=surfaces, inner_cfg=inner_cfg,
                        seed=int(transfer["sampling"]["seed"]) + int(taxon_index) * 10000 + outer_rep * 100,
                    )
                    if reason != "ok": fallbacks += 1
                    for row in diag:
                        inner_rows.append({"sample_id": int(taxon["sample_id"]), "scientific_name": str(taxon["scientific_name"]), "outer_repeat": outer_rep, "selection_reason": reason, **row})

                    train_features = bench.attach_public_features(fold["train"], ndvi_transform=tr, ndvi_crs=crs, ndvi_surface_dict=surfaces, micro_surfaces={}, dem_map={})
                    needed = {(1, 1.0), (1, 0.10), (2, 0.10), (3, 0.10)} | set(selected.values())
                    family = LocalScaleFamily.build(grid_features, train_features, NDVI_STATE, ks)
                    orders = {}
                    for k, q in needed:
                        mask = family.mask(k, q)
                        orders[(k, q)] = greedy_coverage_order_fast(grid, geometry, mask, max_budget=max(budgets), radius_km=radius)
                    held = fold["held"].rename(columns={"lat": "latitude", "lon": "longitude"})
                    for budget in budgets:
                        methods = {
                            "scale_nested_selected": selected[budget],
                            "single_k1_fixed_q10": (1, 0.10),
                            "fixed_k2_q10": (2, 0.10),
                            "fixed_k3_q10": (3, 0.10),
                            "global_max_coverage": (1, 1.0),
                        }
                        for method, policy in methods.items():
                            order = global_order if policy == (1, 1.0) else orders[policy]
                            if len(order) < budget: continue
                            rec = evaluate(order.iloc[:budget], held, radius)["recovered"] / len(held)
                            outer_rows.append({
                                "sample_id": int(taxon["sample_id"]), "scientific_name": str(taxon["scientific_name"]),
                                "outer_repeat": outer_rep, "method": method, "budget": int(budget),
                                "selected_k": int(policy[0]), "selected_q": float(policy[1]), "recall": rec,
                                "heldout_points": int(len(held)), "selection_reason": reason,
                            })
            except Exception as exc:
                failures.append({"sample_id": int(taxon["sample_id"]), "scientific_name": str(taxon["scientific_name"]), "reason": f"{type(exc).__name__}: {exc}"})

    outer = pd.DataFrame(outer_rows)
    if outer.empty: raise RuntimeError("No support-scale outer folds completed")
    taxon = outer.groupby(["sample_id", "scientific_name", "method", "budget"], as_index=False).agg(
        recall=("recall", "mean"), mean_selected_k=("selected_k", "mean"), mean_selected_q=("selected_q", "mean"), folds=("outer_repeat", "count")
    )
    means = taxon.groupby(["method", "budget"], as_index=False).agg(mean_recall=("recall", "mean"), taxa=("sample_id", "nunique"))
    comparisons = []
    for i, b in enumerate(budgets):
        comparisons += [
            paired_inference(taxon, "scale_nested_selected", "global_max_coverage", b, 20261210+i*20),
            paired_inference(taxon, "scale_nested_selected", "single_k1_fixed_q10", b, 20261211+i*20),
            paired_inference(taxon, "fixed_k2_q10", "single_k1_fixed_q10", b, 20261212+i*20),
            paired_inference(taxon, "fixed_k3_q10", "single_k1_fixed_q10", b, 20261213+i*20),
        ]
    selected_counts = outer[outer["method"].eq("scale_nested_selected")][["sample_id", "outer_repeat", "budget", "selected_k", "selected_q"]].drop_duplicates().groupby(["budget", "selected_k", "selected_q"]).size().reset_index(name="folds").to_dict("records")
    summary = {
        "status": "development_only", "protocol_id": protocol["protocol_id"], "taxa": int(taxon["sample_id"].nunique()),
        "failures": failures, "inner_selection_fallback_outer_folds": int(fallbacks), "selected_policy_counts": selected_counts,
        "method_means": means.to_dict("records"), "comparisons": comparisons,
        "outer_heldout_coordinates_used_to_select_policy": False, "campanula_field_coordinates_used": False,
        "frozen_192_consumed": False, "confirmation_claim": False,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    outer.to_csv(args.out/"support_scale_outer_fold_results.csv", index=False)
    taxon.to_csv(args.out/"support_scale_taxon_results.csv", index=False)
    means.to_csv(args.out/"support_scale_method_means.csv", index=False)
    pd.DataFrame(inner_rows).to_csv(args.out/"support_scale_inner_diagnostics.csv", index=False)
    pd.DataFrame(comparisons).to_csv(args.out/"support_scale_comparisons.csv", index=False)
    (args.out/"support_scale_summary.json").write_text(json.dumps(summary, indent=2)+"\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__": main()
