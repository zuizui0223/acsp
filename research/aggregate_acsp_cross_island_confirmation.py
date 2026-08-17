#!/usr/bin/env python3
"""Aggregate the frozen 24-pair cross-island ACSP confirmation.

All inferential settings are read from the pre-outcome execution protocol.
Robustness diagnostics are descriptive and cannot rescue a failed primary gate.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

EXPECTED_EXECUTION = "24a5cc0d21bcfd4fdfce5dc9b8ccbb2cd8dc1fc717928d8ed6775c79ef8591e1"
EXPECTED_METHOD = "1bff5eb8571928e9b26c193bc7bc0756f239b30def062ab49e0b94ed0c3029f0"
EXPECTED_COHORT_SHA256 = "0bf03cdbf338f57de129a904b29beef91bfa8dd60a31af13c44f94f596ab4843"


def canonical_protocol(path: Path) -> tuple[dict, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    if expected != calculated:
        raise ValueError("execution protocol fingerprint mismatch")
    payload["protocol_fingerprint"] = expected
    return payload, calculated


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def bootstrap_ci(values: np.ndarray, draws: int, seed: int) -> list[float]:
    values = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    means = np.empty(int(draws), dtype=float)
    for i in range(int(draws)):
        means[i] = float(rng.choice(values, size=len(values), replace=True).mean())
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def exact_sign_flip_p(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    nonzero = values[np.abs(values) > 1e-15]
    if len(nonzero) == 0:
        return 1.0
    observed = float(nonzero.sum())
    sums = np.zeros(1, dtype=float)
    for value in nonzero:
        sums = np.concatenate([sums + value, sums - value])
    return float(np.mean(sums >= observed - 1e-12))


def inference(values: np.ndarray, draws: int, seed: int) -> dict:
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return {"n": 0}
    return {
        "n": int(len(values)),
        "mean_lift": float(values.mean()),
        "bootstrap_95ci": bootstrap_ci(values, draws, seed),
        "exact_one_sided_sign_flip_p": exact_sign_flip_p(values),
        "positive": int((values > 0).sum()),
        "negative": int((values < 0).sum()),
        "ties": int((values == 0).sum()),
    }


def leave_one_out_range(frame: pd.DataFrame, group_col: str | None = None) -> list[float]:
    if frame.empty:
        return [float("nan"), float("nan")]
    means = []
    if group_col is None:
        for pair_id in frame["pair_id"]:
            remainder = frame[~frame["pair_id"].eq(pair_id)]
            if len(remainder):
                means.append(float(remainder["mean_lift"].mean()))
    else:
        for value in frame[group_col].drop_duplicates():
            remainder = frame[~frame[group_col].eq(value)]
            if len(remainder):
                means.append(float(remainder["mean_lift"].mean()))
    return [float(min(means)), float(max(means))] if means else [float("nan"), float("nan")]


def exact_half_subset_stability(values: np.ndarray, threshold: float) -> dict:
    values = np.asarray(values, dtype=float)
    n = len(values)
    k = n // 2
    total = math.comb(n, k) if n and k else 0
    if total == 0 or total > 3_000_000:
        return {"computed": False, "reason": f"combination_count_{total}_outside_limit"}
    means = np.empty(total, dtype=float)
    for i, combo in enumerate(itertools.combinations(range(n), k)):
        means[i] = float(values[list(combo)].mean())
    return {
        "computed": True,
        "subset_size": int(k),
        "subsets": int(total),
        "fraction_positive": float(np.mean(means > 0)),
        "fraction_ge_minimum_lift": float(np.mean(means >= float(threshold))),
        "mean_lift_2_5_to_97_5_percentile": [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-protocol", type=Path, required=True)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    protocol, fingerprint = canonical_protocol(args.execution_protocol)
    if fingerprint != EXPECTED_EXECUTION:
        raise ValueError(f"unexpected execution protocol {fingerprint}")
    if protocol["method_freeze"]["fingerprint"] != EXPECTED_METHOD:
        raise ValueError("method fingerprint mismatch")
    if sha256_file(args.cohort) != EXPECTED_COHORT_SHA256:
        raise ValueError("cohort checksum mismatch")

    cohort = pd.read_csv(args.cohort)
    pair_paths = sorted(args.results_root.glob("**/pair_results.csv"))
    fold_paths = sorted(args.results_root.glob("**/fold_results.csv"))
    summary_paths = sorted(args.results_root.glob("**/island_summary.json"))
    pairs = pd.concat([pd.read_csv(path) for path in pair_paths], ignore_index=True) if pair_paths else pd.DataFrame()
    folds = pd.concat([pd.read_csv(path) for path in fold_paths], ignore_index=True) if fold_paths else pd.DataFrame()
    island_summaries = [json.loads(path.read_text()) for path in summary_paths]

    declared_ids = set(cohort["pair_id"].astype(int))
    observed_ids = set(pairs.get("pair_id", pd.Series(dtype=int)).dropna().astype(int))
    missing_pair_results = sorted(declared_ids - observed_ids)
    duplicate_pair_results = sorted(
        pairs.loc[pairs.get("pair_id", pd.Series(dtype=int)).duplicated(keep=False), "pair_id"].astype(int).unique().tolist()
    ) if not pairs.empty else []
    infrastructure = [
        item
        for summary in island_summaries
        for item in summary.get("infrastructure_failures", [])
    ]

    eligible = pairs[pairs.get("status", pd.Series(dtype=str)).eq("ok")].copy()
    diffs = eligible.get("mean_lift", pd.Series(dtype=float)).to_numpy(float)
    primary = inference(
        diffs,
        int(protocol["primary_estimand"]["pair_bootstrap_draws"]),
        int(protocol["primary_estimand"]["inference_seed"]),
    )
    eligibility_rate = float(len(eligible) / len(cohort)) if len(cohort) else 0.0
    primary_rules = protocol["primary_estimand"]
    primary_pass = bool(
        not missing_pair_results
        and not duplicate_pair_results
        and not infrastructure
        and len(eligible) >= int(primary_rules["minimum_eligible_pairs"])
        and eligibility_rate >= float(primary_rules["minimum_eligibility_rate"])
        and primary.get("mean_lift", -np.inf) >= float(primary_rules["minimum_mean_lift"])
        and primary.get("bootstrap_95ci", [-np.inf])[0] > float(primary_rules["pair_bootstrap_95ci_lower_gt"])
        and primary.get("exact_one_sided_sign_flip_p", 1.0) < float(primary_rules["exact_one_sided_sign_flip_p_lt"])
    )

    robustness = {
        "leave_one_pair_out_mean_lift_range": leave_one_out_range(eligible),
        "leave_one_island_out_mean_lift_range": leave_one_out_range(eligible, "island_id"),
        "exact_half_cohort_subset_stability": exact_half_subset_stability(
            diffs, float(primary_rules["minimum_mean_lift"])
        ),
        "record_stratum": {},
        "island": {},
    }
    for stratum, frame in eligible.groupby("record_count_stratum"):
        robustness["record_stratum"][str(int(stratum))] = inference(
            frame["mean_lift"].to_numpy(float),
            int(primary_rules["pair_bootstrap_draws"]),
            int(primary_rules["inference_seed"]) + 10 + int(stratum),
        )
    for i, (island, frame) in enumerate(eligible.groupby("island_id")):
        robustness["island"][str(island)] = {
            "pairs": int(len(frame)),
            "mean_lift": float(frame["mean_lift"].mean()),
            "positive": int((frame["mean_lift"] > 0).sum()),
            "negative": int((frame["mean_lift"] < 0).sum()),
            "ties": int((frame["mean_lift"] == 0).sum()),
        }

    sensitivity = {}
    for radius in protocol["practicality_and_robustness"]["non_gating_recovery_radius_sensitivity_km"]:
        suffix = str(float(radius)).replace(".", "p")
        support_col = f"mean_support_recall_r{suffix}"
        control_col = f"mean_control_recall_r{suffix}"
        if support_col in eligible and control_col in eligible:
            values = (eligible[support_col] - eligible[control_col]).to_numpy(float)
            sensitivity[str(radius)] = inference(
                values,
                int(primary_rules["pair_bootstrap_draws"]),
                int(primary_rules["inference_seed"]) + int(float(radius) * 100),
            )

    zero_filled = cohort[["pair_id"]].merge(
        eligible[["pair_id", "mean_lift"]], on="pair_id", how="left"
    )["mean_lift"].fillna(0.0).to_numpy(float)
    declared_cohort_zero_filled = inference(
        zero_filled,
        int(primary_rules["pair_bootstrap_draws"]),
        int(primary_rules["inference_seed"]) + 999,
    )

    practical = {
        "declared_pairs": int(len(cohort)),
        "pair_result_rows": int(len(pairs)),
        "eligible_pairs": int(len(eligible)),
        "eligibility_rate": eligibility_rate,
        "domain_inapplicable_pairs": int(pairs.get("status", pd.Series(dtype=str)).eq("domain_inapplicable").sum()),
        "information_inapplicable_pairs": int(pairs.get("status", pd.Series(dtype=str)).eq("information_inapplicable").sum()),
        "infrastructure_failure_pairs": int(pairs.get("status", pd.Series(dtype=str)).eq("infrastructure_failure").sum()),
        "missing_pair_results": missing_pair_results,
        "duplicate_pair_results": duplicate_pair_results,
        "method_failure_folds": int(eligible.get("method_failure_folds", pd.Series(dtype=float)).fillna(0).sum()),
        "valid_fold_fraction_of_declared": float(pairs.get("valid_folds", pd.Series(dtype=float)).fillna(0).sum() / (len(cohort) * int(protocol["spatial_validation"]["repeats"]))) if len(cohort) else 0.0,
        "mean_support_eligible_grid_fraction": float(eligible["mean_support_eligible_grid_fraction"].mean()) if len(eligible) else float("nan"),
        "mean_selected_set_jaccard": float(eligible["mean_selected_set_jaccard"].mean()) if len(eligible) else float("nan"),
        "median_support_selection_runtime_seconds": float(eligible["mean_support_selection_runtime_seconds"].median()) if len(eligible) else float("nan"),
        "declared_cohort_zero_filled_lift": declared_cohort_zero_filled,
    }

    summary = {
        "status": "confirmation_complete" if not missing_pair_results and not infrastructure else "confirmation_incomplete_infrastructure",
        "execution_protocol_fingerprint": fingerprint,
        "method_freeze_fingerprint": EXPECTED_METHOD,
        "cohort_sha256": EXPECTED_COHORT_SHA256,
        "primary": primary,
        "primary_confirmation_pass": primary_pass,
        "practicality": practical,
        "robustness": robustness,
        "radius_sensitivity": sensitivity,
        "infrastructure_failures": infrastructure,
        "retuning_performed": False,
        "frozen_192_consumed": False,
        "claim_boundary": protocol["claim_boundary"],
    }

    args.out.mkdir(parents=True, exist_ok=True)
    pairs.sort_values("pair_id").to_csv(args.out / "pair_results.csv", index=False)
    folds.sort_values(["pair_id", "repeat"]).to_csv(args.out / "fold_results.csv", index=False)
    pd.DataFrame(island_summaries).to_json(args.out / "island_summaries.json", orient="records", indent=2)
    (args.out / "confirmation_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
