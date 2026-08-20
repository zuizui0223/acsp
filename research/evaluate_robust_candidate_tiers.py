#!/usr/bin/env python3
"""Evaluate robust candidate tiers on held-out occurrences without tuning on final confirmation data.

This development harness accepts an already-generated robust support surface and
held-out occurrence clusters. For each predeclared support tier it measures
same-area recovery and a same-area matched-random baseline. It does not choose a
winning tier automatically and it must not be run on the untouched confirmation
cohort before the tier rule is frozen.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from acsp.field_validation import detection_recovery_table, recovery_summary

DEFAULT_TIERS = (0.025, 0.05, 0.10, 0.20)
DEFAULT_RADII_KM = (1.0, 2.0, 5.0, 10.0)


def _csv_floats(value: str) -> tuple[float, ...]:
    values = tuple(float(item.strip()) for item in value.split(",") if item.strip())
    if not values:
        raise argparse.ArgumentTypeError("expected at least one comma-separated number")
    return tuple(sorted(set(values)))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--surface", type=Path, required=True)
    parser.add_argument("--heldout", type=Path, required=True)
    parser.add_argument("--tiers", type=_csv_floats, default=DEFAULT_TIERS)
    parser.add_argument("--radii-km", type=_csv_floats, default=DEFAULT_RADII_KM)
    parser.add_argument("--area-column", default="survey_area_id")
    parser.add_argument("--heldout-area-column", default="survey_area_id")
    parser.add_argument("--iterations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260819)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def _random_recall(
    pool: pd.DataFrame,
    selected: pd.DataFrame,
    heldout: pd.DataFrame,
    *,
    radii_km: tuple[float, ...],
    area_col: str,
    heldout_area_col: str,
    iterations: int,
    seed: int,
) -> pd.DataFrame:
    quotas = selected.groupby(area_col, dropna=False).size().astype(int).to_dict()
    groups = {str(area): frame.copy() for area, frame in pool.groupby(area_col, dropna=False)}
    rng = np.random.default_rng(int(seed))
    rows: list[dict[str, float | int]] = []
    for iteration in range(1, int(iterations) + 1):
        parts: list[pd.DataFrame] = []
        feasible = True
        for area, quota in quotas.items():
            frame = groups.get(str(area))
            if frame is None or len(frame) < int(quota):
                feasible = False
                break
            draw = rng.choice(len(frame), size=int(quota), replace=False)
            parts.append(frame.iloc[draw])
        if not feasible or not parts:
            continue
        sample = pd.concat(parts, ignore_index=True)
        recovery = detection_recovery_table(
            sample,
            heldout,
            radii_km=radii_km,
            area_col=area_col,
            detection_area_col=heldout_area_col,
        )
        summary = recovery_summary(recovery, radii_km=radii_km)
        for row in summary.itertuples(index=False):
            rows.append(
                {
                    "iteration": int(iteration),
                    "radius_km": float(row.radius_km),
                    "random_recall": float(row.detection_recall),
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    args = parse_args()
    surface = pd.read_csv(args.surface)
    heldout = pd.read_csv(args.heldout)
    required_surface = {
        "latitude",
        "longitude",
        args.area_column,
        "consensus_support_rank",
    }
    missing = required_surface - set(surface.columns)
    if missing:
        raise ValueError("support surface lacks required columns: " + ", ".join(sorted(missing)))
    if args.heldout_area_column not in heldout.columns:
        raise ValueError(f"held-out table lacks area column {args.heldout_area_column!r}")

    surface = surface.copy().reset_index(drop=True)
    surface["site_id"] = np.arange(len(surface)).astype(str)
    ranks = pd.to_numeric(surface["consensus_support_rank"], errors="coerce")
    result_rows: list[dict[str, object]] = []
    random_exports: list[pd.DataFrame] = []

    for tier_index, tier in enumerate(args.tiers):
        selected = surface.loc[ranks.le(float(tier))].copy()
        if selected.empty:
            continue
        observed = recovery_summary(
            detection_recovery_table(
                selected,
                heldout,
                radii_km=args.radii_km,
                area_col=args.area_column,
                detection_area_col=args.heldout_area_column,
            ),
            radii_km=args.radii_km,
        )
        draws = _random_recall(
            surface,
            selected,
            heldout,
            radii_km=args.radii_km,
            area_col=args.area_column,
            heldout_area_col=args.heldout_area_column,
            iterations=args.iterations,
            seed=args.seed + tier_index * 1009,
        )
        draws["support_fraction"] = float(tier)
        random_exports.append(draws)
        for row in observed.itertuples(index=False):
            random_at_radius = draws.loc[draws["radius_km"].eq(float(row.radius_km)), "random_recall"]
            random_mean = float(random_at_radius.mean()) if len(random_at_radius) else float("nan")
            result_rows.append(
                {
                    "support_fraction": float(tier),
                    "selected_cells": int(len(selected)),
                    "radius_km": float(row.radius_km),
                    "heldout_count": int(row.n_detection_clusters),
                    "recovered": int(row.n_recovered),
                    "recall": float(row.detection_recall),
                    "median_nearest_km": float(row.median_nearest_candidate_km),
                    "max_nearest_km": float(row.max_nearest_candidate_km),
                    "random_mean_recall": random_mean,
                    "lift_over_random": float(row.detection_recall) - random_mean,
                    "random_q025": float(random_at_radius.quantile(0.025)) if len(random_at_radius) else None,
                    "random_q975": float(random_at_radius.quantile(0.975)) if len(random_at_radius) else None,
                }
            )

    results = pd.DataFrame(result_rows)
    draws_all = pd.concat(random_exports, ignore_index=True) if random_exports else pd.DataFrame()
    args.out.mkdir(parents=True, exist_ok=True)
    results.to_csv(args.out / "robust_tier_development_results.csv", index=False)
    draws_all.to_csv(args.out / "robust_tier_random_draws.csv", index=False)
    manifest = {
        "status": "development_only_no_auto_selection",
        "final_confirmation_cohort_allowed": False,
        "field_or_heldout_outcomes_used_to_generate_support": False,
        "tier_rule_selected_automatically": False,
        "tiers": list(args.tiers),
        "radii_km": list(args.radii_km),
        "iterations": int(args.iterations),
        "seed": int(args.seed),
        "result_rows": int(len(results)),
    }
    (args.out / "robust_tier_development_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
