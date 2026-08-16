#!/usr/bin/env python3
"""Test the best support mask against a strong set-level geographic comparator."""
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
    NDVI_STATE,
    evaluate,
    fast_matched_random_success,
    fit_distance_rank,
)
from campanula_ndvi_transition_discovery import ndvi_surfaces
from develop_izu_support_constrained_coverage import bootstrap_ci, sign_flip_p
from run_izu_microenvironment_random_taxa import retrieval_wkt

bench.island_wkt = retrieval_wkt


def build_geometry(grid: pd.DataFrame) -> dict[str, dict]:
    geometry = {}
    for island, indices in grid.groupby("island").groups.items():
        idx = np.asarray(sorted(indices), dtype=int)
        frame = grid.loc[idx]
        lat0 = float(frame["lat"].mean())
        scale_x = 111.320 * np.cos(np.radians(lat0))
        xy = np.column_stack(
            [
                frame["lon"].to_numpy(float) * scale_x,
                frame["lat"].to_numpy(float) * 111.320,
            ]
        )
        geometry[str(island)] = {
            "idx": idx,
            "xy": xy,
            "tree": cKDTree(xy),
        }
    return geometry


def greedy_max_coverage(
    grid: pd.DataFrame,
    geometry: dict[str, dict],
    eligible: np.ndarray,
    *,
    budget: int,
    radius_km: float,
) -> pd.DataFrame:
    """Greedily maximize newly covered public land-grid cells."""
    eligible = np.asarray(eligible, dtype=bool)
    covered = np.zeros(len(grid), dtype=bool)
    selected_mask = np.zeros(len(grid), dtype=bool)
    selected: list[int] = []

    for _ in range(min(int(budget), int(eligible.sum()))):
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
                uncovered_tree = cKDTree(geo["xy"][uncovered_local])
                gains = uncovered_tree.query_ball_point(
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


def infer(taxon: pd.DataFrame, a: str, b: str, seed: int) -> dict:
    diff = (taxon[a] - taxon[b]).to_numpy(float)
    ci = bootstrap_ci(diff, 10000, seed)
    p = sign_flip_p(diff, 50000, seed + 1)
    return {
        "mean_difference": float(diff.mean()),
        "bootstrap_95ci": ci,
        "sign_flip_p": p,
        "positive_taxa": int((diff > 0).sum()),
        "negative_taxa": int((diff < 0).sum()),
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
    target = protocol["target_cell"]
    q = float(target["support_quantile"])
    budget = int(target["budget"])
    radius = float(target["survey_radius_km"])

    dem_map = {}
    for spec in args.dem:
        island, path = spec.split("=", 1)
        dem_map[island] = Path(path)

    grid = bench.build_public_grid(dem_map)
    geometry = build_geometry(grid)
    fold_rows = []
    failures = []

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
                        ndvi_transform=ndvi_transform,
                        ndvi_crs=ndvi_crs,
                        ndvi_surface_dict=ndvi_surface_dict,
                        micro_surfaces={},
                        dem_map={},
                    )
                    _, support_rank = fit_distance_rank(ndvi_grid, train, NDVI_STATE)
                    support_selected = greedy_max_coverage(
                        grid,
                        geometry,
                        support_rank <= q + 1e-12,
                        budget=budget,
                        radius_km=radius,
                    )
                    coverage_selected = greedy_max_coverage(
                        grid,
                        geometry,
                        np.ones(len(grid), dtype=bool),
                        budget=budget,
                        radius_km=radius,
                    )

                    # Held-out coordinates are inspected only after both deterministic sets are frozen.
                    held = fold["held"].rename(columns={"lat": "latitude", "lon": "longitude"})
                    support_result = evaluate(support_selected, held, radius)
                    coverage_result = evaluate(coverage_selected, held, radius)
                    random_result = fast_matched_random_success(
                        grid,
                        held,
                        support_selected,
                        radius,
                        500,
                        int(transfer["sampling"]["seed"]) + int(taxon_index) * 1000 + repeat_index,
                    )
                    fold_rows.append(
                        {
                            "sample_id": int(taxon["sample_id"]),
                            "scientific_name": name,
                            "repeat": repeat_index,
                            "heldout_points": int(len(held)),
                            "support_max_coverage_recall": support_result["recovered"] / len(held),
                            "coverage_only_recall": coverage_result["recovered"] / len(held),
                            "matched_random_recall": float(random_result["mean_recovered"]) / len(held),
                            "support_selected_by_island": json.dumps({str(k): int(v) for k, v in support_selected.groupby("island").size().items()}, sort_keys=True),
                            "coverage_selected_by_island": json.dumps({str(k): int(v) for k, v in coverage_selected.groupby("island").size().items()}, sort_keys=True),
                        }
                    )
            except Exception as exc:
                failures.append({"sample_id": int(taxon["sample_id"]), "scientific_name": name, "reason": f"{type(exc).__name__}: {exc}"})

    fold = pd.DataFrame(fold_rows)
    if fold.empty:
        raise RuntimeError("No strong-comparator folds completed")
    taxon = (
        fold.groupby(["sample_id", "scientific_name"], as_index=False)
        .agg(
            support_max_coverage_recall=("support_max_coverage_recall", "mean"),
            coverage_only_recall=("coverage_only_recall", "mean"),
            matched_random_recall=("matched_random_recall", "mean"),
            folds=("repeat", "count"),
        )
    )
    support_vs_coverage = infer(
        taxon, "support_max_coverage_recall", "coverage_only_recall", 20260816
    )
    support_vs_random = infer(
        taxon, "support_max_coverage_recall", "matched_random_recall", 20260818
    )
    summary = {
        "status": "development_only",
        "taxa": int(len(taxon)),
        "failures": failures,
        "support_quantile": q,
        "budget": budget,
        "survey_radius_km": radius,
        "mean_support_max_coverage_recall": float(taxon["support_max_coverage_recall"].mean()),
        "mean_coverage_only_recall": float(taxon["coverage_only_recall"].mean()),
        "mean_matched_random_recall": float(taxon["matched_random_recall"].mean()),
        "support_vs_coverage_only": support_vs_coverage,
        "support_vs_matched_random": support_vs_random,
        "promotion_gate": bool(support_vs_coverage["passes"] and support_vs_random["passes"]),
        "frozen_192_consumed": False,
        "confirmation_claim": False,
    }

    args.out.mkdir(parents=True, exist_ok=True)
    fold.to_csv(args.out / "strong_coverage_fold_results.csv", index=False)
    taxon.to_csv(args.out / "strong_coverage_taxon_results.csv", index=False)
    (args.out / "strong_coverage_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
