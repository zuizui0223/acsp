#!/usr/bin/env python3
"""Evaluate robust candidate tiers on existing training/held-out comparator exports.

This bridge is for already-inspected development cohorts only. It reuses the
frozen comparator folds so held-out coordinates remain outside the generator.
The candidate pool supplies a common terrain universe. Training occurrences are
mapped to their nearest candidate only to recover the corresponding terrain
feature vector; held-out coordinates are used solely after support generation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from acsp.field_validation import detection_recovery_table, recovery_summary
from acsp.robust_patches import leave_one_out_consensus_support, support_cells_to_patches

RAW_FEATURES = ("elevation", "slope", "aspect", "roughness", "tpi")
ROBUST_FEATURES = ("elevation", "slope", "aspect_sin", "aspect_cos", "roughness", "tpi")
DEFAULT_TIERS = (0.025, 0.05, 0.10, 0.20)
DEFAULT_RADII_KM = (1.0, 2.0, 5.0, 10.0)
EARTH_RADIUS_KM = 6371.0088


def _csv_floats(value: str) -> tuple[float, ...]:
    values = tuple(float(item.strip()) for item in value.split(",") if item.strip())
    if not values:
        raise argparse.ArgumentTypeError("expected comma-separated numbers")
    return tuple(sorted(set(values)))


def _coords(frame: pd.DataFrame) -> np.ndarray:
    return frame[["latitude", "longitude"]].apply(pd.to_numeric, errors="coerce").to_numpy(float)


def _nearest_indices(points: np.ndarray, candidates: np.ndarray) -> np.ndarray:
    lat1 = np.radians(points[:, 0])[:, None]
    lon1 = np.radians(points[:, 1])[:, None]
    lat2 = np.radians(candidates[:, 0])[None, :]
    lon2 = np.radians(candidates[:, 1])[None, :]
    a = np.sin((lat2 - lat1) / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2.0) ** 2
    distance = 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
    return np.argmin(distance, axis=1)


def _terrain_features(frame: pd.DataFrame) -> pd.DataFrame:
    missing = set(RAW_FEATURES) - set(frame.columns)
    if missing:
        raise ValueError("candidate pool lacks terrain features: " + ", ".join(sorted(missing)))
    out = frame.copy()
    for column in RAW_FEATURES:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    radians = np.radians(out["aspect"].to_numpy(float))
    out["aspect_sin"] = np.sin(radians)
    out["aspect_cos"] = np.cos(radians)
    return out


def _fold_result(
    fold_dir: Path,
    *,
    tiers: tuple[float, ...],
    radii_km: tuple[float, ...],
    merge_distance_m: float,
    random_draws: int,
    seed: int,
) -> list[dict[str, object]]:
    candidates = pd.read_csv(fold_dir / "candidates.csv")
    training = pd.read_csv(fold_dir / "training_occurrences.csv")
    heldout = pd.read_csv(fold_dir / "held_out_occurrences.csv")
    if candidates.empty or training.empty or heldout.empty:
        return []
    universe = _terrain_features(candidates)
    complete = universe.loc[universe[list(ROBUST_FEATURES)].notna().all(axis=1)].copy().reset_index(drop=True)
    if len(complete) < 5:
        return []
    training = training.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)
    heldout = heldout.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)
    if training.empty or heldout.empty:
        return []

    nearest = _nearest_indices(_coords(training), _coords(complete))
    prototype_indices = np.unique(nearest)
    prototypes = complete.iloc[prototype_indices][list(ROBUST_FEATURES)].copy().reset_index(drop=True)
    if len(prototypes) < 5:
        return []

    consensus, uncertainty, audit = leave_one_out_consensus_support(
        complete,
        prototypes,
        feature_columns=ROBUST_FEATURES,
        support_world_dtype="float32",
    )
    complete["consensus_support_rank"] = consensus
    complete["consensus_support_uncertainty"] = uncertainty
    complete["survey_area_id"] = "region"
    heldout = heldout.copy()
    heldout["survey_area_id"] = "region"

    rng = np.random.default_rng(int(seed))
    rows: list[dict[str, object]] = []
    for tier in tiers:
        selected_cells, patches = support_cells_to_patches(
            complete,
            consensus,
            threshold=float(tier),
            merge_distance_m=float(merge_distance_m),
            area_col="survey_area_id",
        )
        if selected_cells.empty:
            continue
        observed = recovery_summary(
            detection_recovery_table(
                selected_cells,
                heldout,
                radii_km=radii_km,
                area_col="survey_area_id",
                detection_area_col="survey_area_id",
            ),
            radii_km=radii_km,
        )
        random_by_radius = {float(radius): [] for radius in radii_km}
        draw_count = min(len(selected_cells), len(complete))
        for _ in range(int(random_draws)):
            random_cells = complete.iloc[rng.choice(len(complete), size=draw_count, replace=False)].copy()
            random_cells["site_id"] = np.arange(len(random_cells)).astype(str)
            summary = recovery_summary(
                detection_recovery_table(
                    random_cells,
                    heldout,
                    radii_km=radii_km,
                    area_col="survey_area_id",
                    detection_area_col="survey_area_id",
                ),
                radii_km=radii_km,
            )
            for record in summary.itertuples(index=False):
                random_by_radius[float(record.radius_km)].append(float(record.detection_recall))
        for record in observed.itertuples(index=False):
            random_values = np.asarray(random_by_radius[float(record.radius_km)], dtype=float)
            random_mean = float(random_values.mean()) if len(random_values) else float("nan")
            rows.append(
                {
                    "fold": str(fold_dir),
                    "support_fraction": float(tier),
                    "candidate_universe": int(len(complete)),
                    "prototype_count": int(audit.prototype_count),
                    "selected_cells": int(len(selected_cells)),
                    "patch_count": int(len(patches)),
                    "radius_km": float(record.radius_km),
                    "heldout_count": int(record.n_detection_clusters),
                    "recall": float(record.detection_recall),
                    "random_mean_recall": random_mean,
                    "lift_over_random": float(record.detection_recall) - random_mean,
                    "median_nearest_km": float(record.median_nearest_candidate_km),
                    "max_nearest_km": float(record.max_nearest_candidate_km),
                }
            )
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-root", type=Path, required=True)
    parser.add_argument("--tiers", type=_csv_floats, default=DEFAULT_TIERS)
    parser.add_argument("--radii-km", type=_csv_floats, default=DEFAULT_RADII_KM)
    parser.add_argument("--merge-distance-m", type=float, default=1000.0)
    parser.add_argument("--random-draws", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20260819)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows: list[dict[str, object]] = []
    fold_dirs = sorted(path.parent for path in args.export_root.glob("pair_*/fold_*/fold_manifest.json"))
    for index, fold_dir in enumerate(fold_dirs):
        try:
            rows.extend(
                _fold_result(
                    fold_dir,
                    tiers=args.tiers,
                    radii_km=args.radii_km,
                    merge_distance_m=args.merge_distance_m,
                    random_draws=args.random_draws,
                    seed=args.seed + index * 1009,
                )
            )
        except (ValueError, FileNotFoundError):
            continue
    results = pd.DataFrame(rows)
    args.out.mkdir(parents=True, exist_ok=True)
    results.to_csv(args.out / "robust_patch_fold_results.csv", index=False)
    if results.empty:
        summary = pd.DataFrame()
    else:
        summary = (
            results.groupby(["support_fraction", "radius_km"], as_index=False)
            .agg(
                folds=("fold", "nunique"),
                mean_recall=("recall", "mean"),
                mean_random_recall=("random_mean_recall", "mean"),
                mean_lift=("lift_over_random", "mean"),
                median_patches=("patch_count", "median"),
            )
        )
    summary.to_csv(args.out / "robust_patch_development_summary.csv", index=False)
    manifest = {
        "status": "historical_development_only",
        "untouched_confirmation_opened": False,
        "folds_discovered": int(len(fold_dirs)),
        "folds_evaluated": int(results["fold"].nunique()) if not results.empty else 0,
        "terrain_features": list(ROBUST_FEATURES),
        "prototype_rule": "training occurrence -> nearest training-built candidate terrain vector -> unique prototypes",
        "tiers": list(args.tiers),
        "radii_km": list(args.radii_km),
        "tier_auto_selection": False,
    }
    (args.out / "robust_patch_development_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
