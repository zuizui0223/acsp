#!/usr/bin/env python3
"""Run the frozen v2 robust-patch untouched confirmation without retuning."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from evaluate_robust_patches_on_dense_surface import _evaluate_fold, _zero_rows
from export_robust_patch_confirmation_folds_v2 import EXPECTED_EXECUTION, _execution


def _provenance(fold_dir: Path) -> dict[str, object]:
    payload = json.loads((fold_dir / "fold_manifest.json").read_text(encoding="utf-8"))
    provenance = payload.get("provenance") or {}
    return {
        "pair_id": int(provenance["pair_id"]),
        "repeat": int(payload["repeat"]),
        "scientific_name": str(provenance["scientific_name"]),
        "taxon_group": str(provenance["taxon_group"]),
        "region_name": str(provenance["region_name"]),
        "fold_status": str(payload.get("status") or "unknown"),
        "fold_failure_reason": str(payload.get("failure_reason") or ""),
    }


def _bootstrap_ci(values: np.ndarray, *, draws: int, seed: int) -> tuple[float, float]:
    if len(values) == 0:
        return float("nan"), float("nan")
    rng = np.random.default_rng(int(seed))
    means = np.empty(int(draws), dtype=float)
    for index in range(int(draws)):
        means[index] = float(rng.choice(values, size=len(values), replace=True).mean())
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def _sign_flip_p(values: np.ndarray, *, draws: int, seed: int) -> float:
    if len(values) == 0:
        return float("nan")
    observed = float(values.mean())
    rng = np.random.default_rng(int(seed))
    extreme = 0
    for _ in range(int(draws)):
        null_mean = float((values * rng.choice((-1.0, 1.0), size=len(values))).mean())
        if null_mean >= observed:
            extreme += 1
    return float((1 + extreme) / (int(draws) + 1))


def run(export_root: Path, output: Path) -> dict[str, object]:
    execution = _execution()
    support_fraction = float(execution["robust_support"]["support_fraction"])
    surface_points = int(execution["robust_support"]["surface_points"])
    surface_seed_base = int(execution["robust_support"]["surface_seed_base"])
    primary_radius = float(execution["recovery"]["primary_radius_km"])
    radii = tuple(sorted([primary_radius] + [float(x) for x in execution["recovery"]["secondary_radii_km"]]))
    random_draws = int(execution["recovery"]["random_draws_per_fold"])
    random_seed_base = int(execution["recovery"]["random_seed_base"])

    fold_dirs = sorted(path.parent for path in export_root.glob("pair_*/fold_*/fold_manifest.json"))
    expected_folds = int(execution["cohort_artifact"]["declared_pairs"]) * int(execution["fold_generation"]["repeats"])
    if len(fold_dirs) != expected_folds:
        raise RuntimeError(f"expected {expected_folds} declared folds, found {len(fold_dirs)}")

    rows: list[dict[str, object]] = []
    for fold_dir in fold_dirs:
        meta = _provenance(fold_dir)
        pair_id = int(meta["pair_id"])
        repeat = int(meta["repeat"])
        try:
            # _evaluate_fold adds 991 internally before creating the RNG.
            # Subtract it here so the effective seed exactly matches the
            # pre-open frozen rule: base + pair_id*10000 + repeat*1009.
            frozen_effective_seed = random_seed_base + pair_id * 10000 + repeat * 1009
            result = _evaluate_fold(
                fold_dir,
                tiers=(support_fraction,),
                radii_km=radii,
                surface_points=surface_points,
                random_draws=random_draws,
                surface_seed_base=surface_seed_base,
                random_seed=frozen_effective_seed - 991,
            )
            if not result:
                result = _zero_rows(
                    fold_dir,
                    tiers=(support_fraction,),
                    radii_km=radii,
                    heldout_count=0,
                    failure_reason=meta["fold_failure_reason"] or "no_evaluable_rows",
                )
        except Exception as exc:
            result = _zero_rows(
                fold_dir,
                tiers=(support_fraction,),
                radii_km=radii,
                heldout_count=0,
                failure_reason=f"{type(exc).__name__}: {exc}",
            )
        for record in result:
            rows.append({**meta, **record})

    folds = pd.DataFrame(rows)
    output.mkdir(parents=True, exist_ok=True)
    folds.to_csv(output / "confirmation_fold_results.csv", index=False)

    primary = folds.loc[
        np.isclose(pd.to_numeric(folds["support_fraction"], errors="coerce"), support_fraction)
        & np.isclose(pd.to_numeric(folds["radius_km"], errors="coerce"), primary_radius)
    ].copy()
    if len(primary) != expected_folds:
        raise RuntimeError(f"primary result table has {len(primary)} rows, expected {expected_folds}")
    pair_counts = primary.groupby("pair_id").size()
    if len(pair_counts) != int(execution["cohort_artifact"]["declared_pairs"]) or not (pair_counts == int(execution["fold_generation"]["repeats"])).all():
        raise RuntimeError("primary result does not contain exactly five rows for every frozen pair")

    pair_results = (
        primary.groupby(["pair_id", "scientific_name", "taxon_group", "region_name"], as_index=False)
        .agg(
            fold_count=("repeat", "count"),
            mean_recall=("recall", "mean"),
            mean_random_recall=("random_mean_recall", "mean"),
            mean_lift=("lift_over_random", "mean"),
            failed_folds=("failure_reason", lambda s: int(pd.Series(s).astype(str).str.len().gt(0).sum())),
            mean_selected_cells=("selected_cells", "mean"),
            mean_patch_count=("patch_count", "mean"),
        )
    )
    pair_results.to_csv(output / "confirmation_pair_results.csv", index=False)

    values = pair_results["mean_lift"].to_numpy(float)
    inference = execution["inference"]
    ci_low, ci_high = _bootstrap_ci(
        values,
        draws=int(inference["bootstrap_draws"]),
        seed=int(inference["bootstrap_seed"]),
    )
    p_value = _sign_flip_p(
        values,
        draws=int(inference["sign_flip_draws"]),
        seed=int(inference["sign_flip_seed"]),
    )
    overall_mean = float(values.mean())
    group_means = {
        str(group): float(frame["mean_lift"].mean())
        for group, frame in pair_results.groupby("taxon_group")
    }
    primary_statistical_gate = bool(
        overall_mean >= float(inference["minimum_practical_absolute_recall_gain"])
        and ci_low > 0.0
        and p_value < 0.05
    )
    cross_taxon_guardrail = bool(group_means.get("plant", 0.0) > 0.0 and group_means.get("animal", 0.0) > 0.0)
    passed = bool(primary_statistical_gate and cross_taxon_guardrail)

    descriptive = (
        folds.groupby(["radius_km"], as_index=False)
        .agg(
            folds=("fold", "count"),
            mean_recall=("recall", "mean"),
            mean_random_recall=("random_mean_recall", "mean"),
            mean_lift=("lift_over_random", "mean"),
        )
    )
    descriptive.to_csv(output / "confirmation_radius_summary.csv", index=False)

    summary = {
        "status": "untouched_confirmation_complete",
        "execution_fingerprint": EXPECTED_EXECUTION,
        "protocol_fingerprint": execution["protocol_fingerprint"],
        "frozen_pairs": int(len(pair_results)),
        "declared_folds": expected_folds,
        "primary_support_fraction": support_fraction,
        "primary_radius_km": primary_radius,
        "overall_pair_mean_lift": overall_mean,
        "pair_bootstrap_95_ci": [ci_low, ci_high],
        "one_sided_sign_flip_p": p_value,
        "taxon_group_mean_lift": group_means,
        "primary_statistical_gate_passed": primary_statistical_gate,
        "cross_taxon_guardrail_passed": cross_taxon_guardrail,
        "overall_confirmation_passed": passed,
        "pairs_with_any_failed_fold": int(pair_results["failed_folds"].gt(0).sum()),
        "retuned_after_outcome_opening": False,
        "claim_if_passed": "cross-taxon enrichment of held-out occurrences by the frozen 2.5% robust-support candidate tier at the 10-km regional screening scale",
        "claim_if_failed": "frozen robust-support rule did not pass its untouched confirmation gate; no retuning is permitted within v2",
    }
    (output / "confirmation_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.export_root, args.output)


if __name__ == "__main__":
    main()
