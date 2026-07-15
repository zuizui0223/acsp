"""Re-audit frozen independent ACSP validation cohorts across many resampling seeds.

This does not regenerate GBIF candidates. Each saved fold already compares ACSP
Top-5 with 200 random Top-5 draws from the identical candidate pool. The audit
asks whether the reported lift survives pair-level resampling, leave-one-pair-out
analysis, and repeated half-sample composition changes.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
MIXED = ROOT / "benchmark_results/general_random_taxa_regions_20260705_hierarchical_confirmatory"
PLANT_EXTENSION = ROOT / "benchmark_results/general_random_taxa_regions_20260706_plant_confirmatory"
SEEDS = (7, 42, 20260702, 20260705, 20260715)


def _load(directory: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    return (
        pd.read_csv(directory / "fold_recovery.csv"),
        pd.read_csv(directory / "predeclared_taxon_region_pairs.csv"),
    )


def pair_level_lifts(
    recovery: pd.DataFrame,
    declared: pd.DataFrame,
    group: str,
    *,
    radius_km: float = 10.0,
    repeats: int = 5,
) -> pd.DataFrame:
    """Build intention-to-evaluate pair means; missing folds contribute zero."""
    declared_group = declared.copy()
    if "status" in declared_group.columns:
        declared_group = declared_group[declared_group["status"].eq("predeclared")]
    declared_group = declared_group[declared_group["taxon_group"].astype(str).eq(str(group))]
    pair_ids = declared_group["scientific_name"].dropna().astype(str).drop_duplicates().tolist()

    selected = recovery[
        recovery["taxon_group"].astype(str).eq(str(group))
        & np.isclose(pd.to_numeric(recovery["radius_km"], errors="coerce"), float(radius_km))
    ]
    rows: list[dict[str, Any]] = []
    for pair_id in pair_ids:
        pair = selected[selected["benchmark_taxon"].astype(str).eq(pair_id)]
        default = float(pd.to_numeric(pair["default_recall"], errors="coerce").fillna(0).sum()) / repeats
        random = float(pd.to_numeric(pair["random_recall"], errors="coerce").fillna(0).sum()) / repeats
        rows.append(
            {
                "benchmark_taxon": pair_id,
                "taxon_group": group,
                "evaluated_folds": int(len(pair)),
                "ite_default_recall": default,
                "ite_random_recall": random,
                "ite_lift": default - random,
            }
        )
    return pd.DataFrame(rows)


def stability_audit(pair_table: pd.DataFrame, *, draws: int = 10_000) -> dict[str, Any]:
    values = pd.to_numeric(pair_table["ite_lift"], errors="coerce").dropna().to_numpy(float)
    if len(values) < 2:
        raise ValueError("Stability audit requires at least two declared taxon-region pairs.")

    leave_one_out = np.array([(values.sum() - value) / (len(values) - 1) for value in values])
    half_size = max(2, int(math.ceil(len(values) / 2)))
    seed_rows = []
    for seed in SEEDS:
        rng = np.random.default_rng(seed)
        bootstrap = rng.choice(values, size=(draws, len(values)), replace=True).mean(axis=1)
        half_samples = np.empty(draws, dtype=float)
        for index in range(draws):
            half_samples[index] = rng.choice(values, size=half_size, replace=False).mean()
        signs = rng.choice(np.array([-1.0, 1.0]), size=(draws, len(values)))
        sign_flips = (signs * values).mean(axis=1)
        observed = abs(float(values.mean()))
        seed_rows.append(
            {
                "seed": seed,
                "bootstrap_ci_low": float(np.quantile(bootstrap, 0.025)),
                "bootstrap_ci_high": float(np.quantile(bootstrap, 0.975)),
                "bootstrap_probability_positive": float(np.mean(bootstrap > 0)),
                "half_sample_probability_positive": float(np.mean(half_samples > 0)),
                "half_sample_q025": float(np.quantile(half_samples, 0.025)),
                "half_sample_q975": float(np.quantile(half_samples, 0.975)),
                "sign_flip_p": float((1 + np.sum(np.abs(sign_flips) >= observed)) / (draws + 1)),
            }
        )

    seed_frame = pd.DataFrame(seed_rows)
    mean_lift = float(values.mean())
    loo_positive = float(np.mean(leave_one_out > 0))
    min_bootstrap_positive = float(seed_frame["bootstrap_probability_positive"].min())
    min_half_positive = float(seed_frame["half_sample_probability_positive"].min())
    robust = bool(
        mean_lift > 0
        and loo_positive >= 0.90
        and min_bootstrap_positive >= 0.95
        and min_half_positive >= 0.80
    )
    return {
        "declared_pairs": int(len(values)),
        "mean_ite_default_recall": float(pair_table["ite_default_recall"].mean()),
        "mean_ite_random_recall": float(pair_table["ite_random_recall"].mean()),
        "mean_lift": mean_lift,
        "pairs_with_positive_lift_fraction": float(np.mean(values > 0)),
        "pairs_with_nonnegative_lift_fraction": float(np.mean(values >= 0)),
        "leave_one_pair_out_min_lift": float(leave_one_out.min()),
        "leave_one_pair_out_max_lift": float(leave_one_out.max()),
        "leave_one_pair_out_positive_fraction": loo_positive,
        "minimum_bootstrap_probability_positive_across_seeds": min_bootstrap_positive,
        "minimum_half_sample_probability_positive_across_seeds": min_half_positive,
        "maximum_sign_flip_p_across_seeds": float(seed_frame["sign_flip_p"].max()),
        "seed_sensitivity": seed_rows,
        "stability_verdict": "stable" if robust else "positive_but_composition_sensitive" if mean_lift > 0 else "not_stable",
    }


def run() -> dict[str, Any]:
    mixed_recovery, mixed_declared = _load(MIXED)
    extension_recovery, extension_declared = _load(PLANT_EXTENSION)

    animals = pair_level_lifts(mixed_recovery, mixed_declared, "animal")
    plants = pd.concat(
        [
            pair_level_lifts(mixed_recovery, mixed_declared, "plant"),
            pair_level_lifts(extension_recovery, extension_declared, "plant"),
        ],
        ignore_index=True,
    )
    if plants["benchmark_taxon"].duplicated().any():
        duplicates = plants.loc[plants["benchmark_taxon"].duplicated(), "benchmark_taxon"].tolist()
        raise ValueError(f"Independent plant cohorts overlap: {duplicates}")

    result = {
        "endpoint": "Top-5 held-out occurrence recovery within 10 km",
        "baseline": "200 random Top-5 draws from the identical fold-specific candidate pool",
        "audit_scope": "pair-level resampling of frozen independent cohorts; no candidate regeneration",
        "animals_independent_mixed_cohort": stability_audit(animals),
        "plants_pooled_independent_cohorts": stability_audit(plants),
    }
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, ensure_ascii=False))
