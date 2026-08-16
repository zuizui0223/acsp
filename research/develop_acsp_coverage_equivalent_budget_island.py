#!/usr/bin/env python3
"""Develop the ACSP coverage-equivalent budget on one predeclared island.

This is a new development cohort. It never reads the inspected 24-pair external
confirmation cohort. q=0.10, NDVI state, thinning and the domain gate are held
fixed; only the operational budget representation changes from fixed K to an
equal land-grid design-footprint curve.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd
import rasterio

from acsp_training_domain_gate import infer_training_domain
from benchmark_izu_microenvironment_random_taxa import attach_public_features
from campanula_microterrain_discovery import thin_500m
from campanula_ndvi_microclimate_hybrid import NDVI_STATE, fit_distance_rank
from campanula_ndvi_transition_discovery import ndvi_surfaces
from develop_izu_strong_coverage_comparator import build_geometry
from fast_max_coverage import SparseCoverageIndex
from run_acsp_cross_island_confirmation_island import (
    build_grid,
    fetch_occurrences,
    score_set,
    training_land_fraction,
)

EXPECTED_DEVELOPMENT = "c5c63afc1e5f9d3857938dd4801e33ef2cc78b26d45bd483a36a60e32f3dcdf4"
EXPECTED_COHORT_SHA256 = "fe0aa6222af28a32d3e6b76dea317a8aeb67776d4d8c9289625cfe4a45f921a1"


def canonical(path: Path) -> tuple[dict, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    if expected != calculated:
        raise ValueError(f"protocol fingerprint mismatch: {path}")
    payload["protocol_fingerprint"] = expected
    return payload, calculated


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def add_blocks(frame: pd.DataFrame, block_degrees: float) -> pd.DataFrame:
    out = frame.copy().reset_index(drop=True)
    out["block"] = (
        np.floor(out["lat"] / float(block_degrees)).astype(int).astype(str)
        + ":"
        + np.floor(out["lon"] / float(block_degrees)).astype(int).astype(str)
    )
    return out


def coverage_curve(index: SparseCoverageIndex, selected: pd.DataFrame, n_grid: int) -> np.ndarray:
    covered = np.zeros(int(n_grid), dtype=bool)
    curve = []
    for raw_idx in selected["_global_idx"].to_numpy(int):
        start = index.adjacency.indptr[raw_idx]
        stop = index.adjacency.indptr[raw_idx + 1]
        covered[index.adjacency.indices[start:stop]] = True
        curve.append(float(covered.mean()))
    return np.asarray(curve, dtype=float)


def target_prefixes(
    selected: pd.DataFrame,
    curve: np.ndarray,
    targets: list[float],
) -> dict[float, tuple[pd.DataFrame, float] | None]:
    result = {}
    for target in targets:
        positions = np.flatnonzero(curve >= float(target) - 1e-12)
        if not len(positions):
            result[float(target)] = None
            continue
        k = int(positions[0] + 1)
        result[float(target)] = (selected.iloc[:k].copy().reset_index(drop=True), float(curve[k - 1]))
    return result


def normalized_auc(targets: list[float], values: list[float]) -> float:
    x = np.asarray(targets, dtype=float)
    y = np.asarray(values, dtype=float)
    width = float(x[-1] - x[0])
    if width <= 0:
        raise ValueError("coverage targets must span a positive range")
    return float(np.trapezoid(y, x) / width)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-protocol", type=Path, required=True)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--island", required=True)
    parser.add_argument("--dem", type=Path, required=True)
    parser.add_argument("--ndvi", type=Path, required=True)
    parser.add_argument("--layer-manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    protocol, fingerprint = canonical(args.development_protocol)
    if fingerprint != EXPECTED_DEVELOPMENT:
        raise ValueError(f"unexpected development protocol {fingerprint}")
    if sha256_file(args.cohort) != EXPECTED_COHORT_SHA256:
        raise ValueError("development cohort checksum mismatch")
    layer_manifest = json.loads(args.layer_manifest.read_text())
    if layer_manifest["development_protocol_fingerprint"] != fingerprint:
        raise ValueError("public-layer protocol mismatch")
    if layer_manifest["selected_taxon_occurrences_read"] is not False:
        raise ValueError("public-layer outcome boundary violated")

    cohort = pd.read_csv(args.cohort)
    pairs = cohort[cohort["island_id"].astype(str).eq(args.island)].copy()
    if len(pairs) != 3:
        raise RuntimeError(f"expected 3 development pairs for {args.island}, found {len(pairs)}")
    bounds = tuple(float(pairs.iloc[0][key]) for key in ("west", "south", "east", "north"))
    grid, dem_surface = build_grid(
        args.dem, args.island, bounds,
        float(protocol["retained_components"]["candidate_grid_m"]),
    )
    if grid.empty:
        raise RuntimeError("empty public land grid")
    grid = grid.copy()
    grid["_global_idx"] = np.arange(len(grid), dtype=int)
    geometry = build_geometry(grid)
    radius = float(protocol["budget"]["design_radius_km"])
    max_sites = int(protocol["budget"]["max_sites"])
    targets = [float(x) for x in protocol["budget"]["target_land_grid_coverage_fractions"]]
    sparse = SparseCoverageIndex.from_geometry(grid, geometry, radius)
    control_order = sparse.select(grid, np.ones(len(grid), dtype=bool), max_budget=max_sites)
    control_curve = coverage_curve(sparse, control_order, len(grid))
    control_prefix = target_prefixes(control_order, control_curve, targets)

    pair_rows: list[dict] = []
    fold_rows: list[dict] = []
    curve_rows: list[dict] = []
    failures: list[dict] = []

    with rasterio.open(args.ndvi) as src:
        ndvi_transform, ndvi_crs, ndvi_surface_dict = ndvi_surfaces(src, grid["lon"], grid["lat"])
        grid_features = attach_public_features(
            grid,
            ndvi_transform=ndvi_transform,
            ndvi_crs=ndvi_crs,
            ndvi_surface_dict=ndvi_surface_dict,
            micro_surfaces={},
            dem_map={},
        )

        for _, pair in pairs.sort_values("pair_id").iterrows():
            pair_id = int(pair["pair_id"])
            base = {
                "pair_id": pair_id,
                "island_id": args.island,
                "scientific_name": str(pair["scientific_name"]),
                "record_count_stratum": int(pair["record_count_stratum"]),
            }
            try:
                occurrences = fetch_occurrences(
                    int(pair["speciesKey"]), bounds, 300, args.island
                )
                thinned = thin_500m(occurrences).reset_index(drop=True)
                full_land_fraction = training_land_fraction(thinned, dem_surface) if len(thinned) else 0.0
                full_domain = infer_training_domain(
                    {"kingdom": "Plantae", "phylum": pair["phylum"], "class": pair["class"]},
                    training_land_fraction=full_land_fraction,
                )
                minimum_deploy = int(protocol["adequacy"]["deployment_information_adequacy"]["minimum_thinned_training_occurrences"])
                deployment_adequate = bool(
                    len(thinned) >= minimum_deploy
                    and full_domain.terrestrial_policy_applicable
                )

                blocked = add_blocks(thinned, float(protocol["adequacy"]["benchmark_evaluability"]["block_degrees"])) if len(thinned) else thinned.assign(block=pd.Series(dtype=str))
                unique_blocks = sorted(blocked["block"].unique().tolist()) if len(blocked) else []
                valid_folds = []
                min_train = int(protocol["adequacy"]["benchmark_evaluability"]["minimum_training_prototypes_per_fold"])
                for block in unique_blocks:
                    held = blocked[blocked["block"].eq(block)].drop(columns="block").reset_index(drop=True)
                    train = blocked[~blocked["block"].eq(block)].drop(columns="block").reset_index(drop=True)
                    if len(train) < min_train or held.empty:
                        continue
                    land_fraction = training_land_fraction(train, dem_surface)
                    fold_domain = infer_training_domain(
                        {"kingdom": "Plantae", "phylum": pair["phylum"], "class": pair["class"]},
                        training_land_fraction=land_fraction,
                    )
                    if not fold_domain.terrestrial_policy_applicable:
                        continue
                    valid_folds.append({"block": block, "train": train, "held": held, "land_fraction": land_fraction})

                min_valid = int(protocol["adequacy"]["benchmark_evaluability"]["minimum_valid_folds"])
                benchmark_evaluable = bool(
                    len(unique_blocks) >= int(protocol["adequacy"]["benchmark_evaluability"]["minimum_unique_spatial_blocks"])
                    and len(valid_folds) >= min_valid
                )

                pair_base = {
                    **base,
                    "raw_unique_occurrences": int(len(occurrences)),
                    "thinned_occurrences": int(len(thinned)),
                    "full_training_land_fraction": float(full_land_fraction),
                    "full_training_domain": full_domain.domain,
                    "deployment_information_adequate": deployment_adequate,
                    "unique_spatial_blocks": int(len(unique_blocks)),
                    "valid_loso_folds": int(len(valid_folds)),
                    "benchmark_evaluable": benchmark_evaluable,
                }
                if not benchmark_evaluable:
                    pair_rows.append({**pair_base, "status": "not_benchmark_evaluable"})
                    continue

                per_fold_auc = []
                fold_target_rows = []
                for fold_index, fold in enumerate(valid_folds, start=1):
                    train_features = attach_public_features(
                        fold["train"],
                        ndvi_transform=ndvi_transform,
                        ndvi_crs=ndvi_crs,
                        ndvi_surface_dict=ndvi_surface_dict,
                        micro_surfaces={},
                        dem_map={},
                    )
                    _, support_rank = fit_distance_rank(grid_features, train_features, NDVI_STATE)
                    eligible = support_rank <= 0.10 + 1e-12
                    start = time.perf_counter()
                    support_order = sparse.select(grid, eligible, max_budget=max_sites)
                    support_seconds = float(time.perf_counter() - start)
                    support_curve = coverage_curve(sparse, support_order, len(grid))
                    support_prefix = target_prefixes(support_order, support_curve, targets)

                    # Both method and control sets are fully determined above.
                    # Held-out coordinates are now used only for evaluation.
                    support_recalls=[]; control_recalls=[]
                    complete_curve = True
                    for target in targets:
                        support_item = support_prefix[target]
                        control_item = control_prefix[target]
                        if support_item is None or control_item is None:
                            complete_curve = False
                            curve_rows.append({
                                **base, "fold": fold_index, "heldout_block": fold["block"],
                                "target_coverage_fraction": target,
                                "status": "coverage_target_infeasible",
                            })
                            continue
                        support_set, support_coverage = support_item
                        control_set, control_coverage = control_item
                        support_recall = score_set(support_set, fold["held"], radius)
                        control_recall = score_set(control_set, fold["held"], radius)
                        support_recalls.append(support_recall)
                        control_recalls.append(control_recall)
                        row = {
                            **base,
                            "fold": fold_index,
                            "heldout_block": fold["block"],
                            "target_coverage_fraction": target,
                            "status": "ok",
                            "training_land_fraction": float(fold["land_fraction"]),
                            "training_points": int(len(fold["train"])),
                            "heldout_points": int(len(fold["held"])),
                            "candidate_grid_cells": int(len(grid)),
                            "support_eligible_grid_fraction": float(eligible.mean()),
                            "support_sites": int(len(support_set)),
                            "control_sites": int(len(control_set)),
                            "support_achieved_coverage_fraction": float(support_coverage),
                            "control_achieved_coverage_fraction": float(control_coverage),
                            "support_recall": support_recall,
                            "control_recall": control_recall,
                            "lift": float(support_recall - control_recall),
                            "support_recall_per_site": float(support_recall / len(support_set)) if len(support_set) else np.nan,
                            "control_recall_per_site": float(control_recall / len(control_set)) if len(control_set) else np.nan,
                            "support_selection_runtime_seconds": support_seconds,
                        }
                        curve_rows.append(row)
                        fold_target_rows.append(row)
                    if complete_curve and len(support_recalls) == len(targets):
                        support_auc = normalized_auc(targets, support_recalls)
                        control_auc = normalized_auc(targets, control_recalls)
                        per_fold_auc.append((support_auc, control_auc))
                        fold_rows.append({
                            **base,
                            "fold": fold_index,
                            "heldout_block": fold["block"],
                            "status": "ok",
                            "support_auc": support_auc,
                            "control_auc": control_auc,
                            "auc_lift": float(support_auc - control_auc),
                        })
                    else:
                        fold_rows.append({
                            **base,
                            "fold": fold_index,
                            "heldout_block": fold["block"],
                            "status": "incomplete_coverage_curve",
                        })

                complete_folds = [row for row in fold_rows if row.get("pair_id") == pair_id and row.get("status") == "ok"]
                if len(complete_folds) < min_valid:
                    pair_rows.append({**pair_base, "status": "coverage_curve_incomplete", "complete_curve_folds": int(len(complete_folds))})
                    continue
                auc_frame = pd.DataFrame(complete_folds)
                result = {
                    **pair_base,
                    "status": "ok",
                    "complete_curve_folds": int(len(auc_frame)),
                    "mean_support_auc": float(auc_frame["support_auc"].mean()),
                    "mean_control_auc": float(auc_frame["control_auc"].mean()),
                    "mean_auc_lift": float(auc_frame["auc_lift"].mean()),
                }
                target_frame = pd.DataFrame([row for row in fold_target_rows if row.get("status") == "ok"])
                for target in targets:
                    sub = target_frame[np.isclose(target_frame["target_coverage_fraction"], target)]
                    token = str(target).replace(".", "p")
                    if len(sub):
                        result[f"mean_lift_c{token}"] = float(sub["lift"].mean())
                        result[f"mean_support_sites_c{token}"] = float(sub["support_sites"].mean())
                        result[f"mean_control_sites_c{token}"] = float(sub["control_sites"].mean())
                        result[f"mean_support_recall_c{token}"] = float(sub["support_recall"].mean())
                        result[f"mean_control_recall_c{token}"] = float(sub["control_recall"].mean())
                pair_rows.append(result)
            except Exception as exc:
                failures.append({**base, "reason": f"{type(exc).__name__}: {exc}"})
                pair_rows.append({**base, "status": "infrastructure_failure", "reason": f"{type(exc).__name__}: {exc}"})

    args.out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(pair_rows).to_csv(args.out / "pair_results.csv", index=False)
    pd.DataFrame(fold_rows).to_csv(args.out / "fold_auc_results.csv", index=False)
    pd.DataFrame(curve_rows).to_csv(args.out / "coverage_curve_results.csv", index=False)
    summary = {
        "status": "development_partial_island_result",
        "island_id": args.island,
        "development_protocol_fingerprint": fingerprint,
        "cohort_sha256": EXPECTED_COHORT_SHA256,
        "pairs": 3,
        "deployment_information_adequate_pairs": int(sum(bool(row.get("deployment_information_adequate")) for row in pair_rows)),
        "benchmark_evaluable_pairs": int(sum(bool(row.get("benchmark_evaluable")) for row in pair_rows)),
        "completed_pairs": int(sum(row.get("status") == "ok" for row in pair_rows)),
        "infrastructure_failures": failures,
        "confirmation_24_reused": False,
        "frozen_192_consumed": False,
    }
    (args.out / "island_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
