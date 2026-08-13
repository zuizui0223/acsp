#!/usr/bin/env python3
"""Reproduce vNext2 safe policy-router development on the reclassified 192 pairs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from acsp.practical_rescue_router import (
    ROUTER_CATEGORICAL_FEATURES,
    ROUTER_NUMERIC_FEATURES,
    ROUTER_PROTOCOL_FINGERPRINT,
    SafeRescueRouterPolicy,
    build_router_features,
    choose_router_policy,
    frozen_v1_ids,
    make_router_estimator,
    router_training_weights,
)
from run_practical_core_confirmation_pair import _coverage_sets, _recall

EXPECTED_FRESH_PROTOCOL = "c7d84a3160e9d9b0b05b932c44444be5dfd750200e72749fb413592499bcf8bd"
EXPECTED_PAIRS = 192
EXPECTED_FOLDS = 5


def _canonical_protocol(path: Path) -> tuple[dict[str, object], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    stored = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if not stored or stored != calculated or stored != ROUTER_PROTOCOL_FINGERPRINT:
        raise ValueError(
            f"vNext2 router protocol mismatch: stored={stored!r}, calculated={calculated!r}"
        )
    payload["protocol_fingerprint"] = stored
    return payload, calculated


def _inference(values: np.ndarray, draws: int, seed: int) -> dict[str, object]:
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or len(values) == 0 or not np.isfinite(values).all():
        raise ValueError("router pair differences must be finite")
    rng = np.random.default_rng(int(seed))
    bootstrap = rng.choice(values, size=(int(draws), len(values)), replace=True).mean(axis=1)
    null = (
        rng.choice(np.array([-1.0, 1.0]), size=(int(draws), len(values))) * values
    ).mean(axis=1)
    observed = abs(float(values.mean()))
    return {
        "pairs": int(len(values)),
        "mean_difference": float(values.mean()),
        "bootstrap_95ci_low": float(np.quantile(bootstrap, 0.025)),
        "bootstrap_95ci_high": float(np.quantile(bootstrap, 0.975)),
        "sign_flip_p": float((1 + np.sum(np.abs(null) >= observed)) / (int(draws) + 1)),
        "positive_pairs": int(np.sum(values > 1e-12)),
        "negative_pairs": int(np.sum(values < -1e-12)),
        "tied_pairs": int(np.sum(np.abs(values) <= 1e-12)),
        "difference_sd": float(np.std(values, ddof=1)),
    }


def _outer_assignment(pair_ids: list[int], folds: int, seed: int) -> dict[int, int]:
    rng = np.random.default_rng(int(seed))
    shuffled = rng.permutation(np.asarray(sorted(pair_ids), dtype=int))
    mapping = {
        int(pair_id): int(position % int(folds)) + 1
        for position, pair_id in enumerate(shuffled.tolist())
    }
    counts = pd.Series(mapping).value_counts().sort_index()
    if counts.max() - counts.min() > 1:
        raise AssertionError("router outer pair-fold assignment is imbalanced")
    return mapping


def _pair_directories(pair_root: Path) -> dict[int, Path]:
    failures = list(pair_root.rglob("infrastructure_failure.json"))
    if failures:
        raise RuntimeError(f"router development source contains {len(failures)} infrastructure failures")
    out: dict[int, Path] = {}
    for path in pair_root.rglob("pair_summary.json"):
        summary = json.loads(path.read_text(encoding="utf-8"))
        pair_id = int(summary["pair_id"])
        if pair_id in out:
            raise RuntimeError(f"duplicate pair artifact: {pair_id}")
        if summary.get("verified_scientific_artifact") is not True:
            raise RuntimeError(f"pair {pair_id} is not a verified scientific artifact")
        if str(summary.get("protocol_fingerprint")) != EXPECTED_FRESH_PROTOCOL:
            raise RuntimeError(f"pair {pair_id} has an unexpected fresh protocol fingerprint")
        out[pair_id] = path.parent
    if sorted(out) != list(range(1, EXPECTED_PAIRS + 1)):
        raise RuntimeError(f"expected pair IDs 1..{EXPECTED_PAIRS}; found {len(out)}")
    return out


def _read_fold_status(pair_dir: Path, repeat: int) -> pd.Series:
    frame = pd.read_csv(pair_dir / "fold_comparison.csv")
    if len(frame) != EXPECTED_FOLDS:
        raise RuntimeError(f"{pair_dir} does not contain exactly {EXPECTED_FOLDS} fold rows")
    row = frame.loc[pd.to_numeric(frame["repeat"], errors="raise").eq(int(repeat))]
    if len(row) != 1:
        raise RuntimeError(f"repeat {repeat} is not unique in {pair_dir}")
    return row.iloc[0]


def _load_development_rows(pair_root: Path, radius_km: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    pair_dirs = _pair_directories(pair_root)
    complete_rows: list[dict[str, object]] = []
    fold_audit: list[dict[str, object]] = []
    for pair_id in range(1, EXPECTED_PAIRS + 1):
        pair_dir = pair_dirs[pair_id]
        summary = json.loads((pair_dir / "pair_summary.json").read_text(encoding="utf-8"))
        group = str(summary["taxon_group"])
        for repeat in range(1, EXPECTED_FOLDS + 1):
            status_row = _read_fold_status(pair_dir, repeat)
            status = str(status_row["fold_status"])
            if status == "explicit_scientific_zero":
                fold_audit.append({
                    "pair_id": pair_id,
                    "repeat": repeat,
                    "taxon_group": group,
                    "scientific_name": str(summary["scientific_name"]),
                    "region_name": str(summary["region_name"]),
                    "fold_status": status,
                    "v1_recovery_10km": 0.0,
                    "rescue_recovery_10km": 0.0,
                    "target_rescue_minus_v1": 0.0,
                })
                continue
            if status != "complete":
                raise RuntimeError(f"pair {pair_id} repeat {repeat} has unexpected status {status!r}")

            fold_dir = pair_dir / f"fold_{repeat:03d}"
            candidate_path = fold_dir / "candidate_pool_pre_outcome.csv"
            decision_path = fold_dir / "rescue_decision_pre_outcome.json"
            heldout_path = fold_dir / "held_out_occurrences.csv"
            if not candidate_path.exists() or not decision_path.exists() or not heldout_path.exists():
                raise RuntimeError(f"pair {pair_id} repeat {repeat} lacks a required frozen artifact")
            candidates = pd.read_csv(candidate_path)
            decision = json.loads(decision_path.read_text(encoding="utf-8"))
            if decision.get("outcomes_available_to_selector") is not False:
                raise RuntimeError("Rescue-v2 decision reports held-out outcome access")
            rescue_ids = list(map(str, decision["selected_ids"]))
            v1_ids = frozen_v1_ids(candidates, group)
            if len(v1_ids) != 5 or len(rescue_ids) != 5:
                raise RuntimeError("complete router fold does not contain two Top-5 decisions")

            features = build_router_features(candidates, group, v1_ids, rescue_ids).iloc[0].to_dict()
            heldout = pd.read_csv(heldout_path)
            coverage, all_ids = _coverage_sets(candidates, heldout, float(radius_km))
            v1_recovery = float(_recall(v1_ids, coverage, all_ids))
            rescue_recovery = float(_recall(rescue_ids, coverage, all_ids))
            stored_rescue = float(status_row["rescue_recovery_10km"])
            if not np.isclose(rescue_recovery, stored_rescue, atol=1e-12, rtol=0.0):
                raise RuntimeError(
                    f"Rescue-v2 reproduction drift for pair {pair_id} repeat {repeat}: "
                    f"computed={rescue_recovery} stored={stored_rescue}"
                )
            target = rescue_recovery - v1_recovery
            complete_rows.append({
                **features,
                "pair_id": pair_id,
                "repeat": repeat,
                "scientific_name_meta": str(summary["scientific_name"]),
                "region_name_meta": str(summary["region_name"]),
                "target_rescue_minus_v1": target,
            })
            fold_audit.append({
                "pair_id": pair_id,
                "repeat": repeat,
                "taxon_group": group,
                "scientific_name": str(summary["scientific_name"]),
                "region_name": str(summary["region_name"]),
                "fold_status": status,
                "v1_recovery_10km": v1_recovery,
                "rescue_recovery_10km": rescue_recovery,
                "target_rescue_minus_v1": target,
            })
    complete = pd.DataFrame(complete_rows)
    audit = pd.DataFrame(fold_audit)
    if len(audit) != EXPECTED_PAIRS * EXPECTED_FOLDS:
        raise RuntimeError("router source did not produce exactly 960 fold audit rows")
    return complete, audit


def run(pair_root: Path, protocol_path: Path, output: Path) -> dict[str, object]:
    protocol, fingerprint = _canonical_protocol(protocol_path)
    cfg = protocol["development_evaluation"]
    policy = SafeRescueRouterPolicy()
    complete, fold_audit = _load_development_rows(pair_root, float(cfg["recovery_radius_km"]))
    columns = [*ROUTER_NUMERIC_FEATURES, *ROUTER_CATEGORICAL_FEATURES]
    forbidden = ("heldout", "held_out", "scientific_name", "region_name", "grts", "target")
    bad = [column for column in columns if any(token in column.lower() for token in forbidden)]
    if bad:
        raise RuntimeError(f"router contains forbidden inference feature names: {bad}")

    assignment = _outer_assignment(
        list(range(1, EXPECTED_PAIRS + 1)),
        int(cfg["outer_pair_folds"]),
        int(cfg["pair_assignment_seed"]),
    )
    predictions: list[pd.DataFrame] = []
    for outer_fold in sorted(set(assignment.values())):
        train_pairs = {pair_id for pair_id, fold in assignment.items() if fold != outer_fold}
        test_pairs = {pair_id for pair_id, fold in assignment.items() if fold == outer_fold}
        train = complete[complete["pair_id"].astype(int).isin(train_pairs)].copy()
        test = complete[complete["pair_id"].astype(int).isin(test_pairs)].copy()
        estimator = make_router_estimator(policy)
        weights = router_training_weights(train["pair_id"])
        estimator.fit(
            train[columns],
            pd.to_numeric(train["target_rescue_minus_v1"], errors="raise").to_numpy(float),
            model__sample_weight=weights,
        )
        scored = test[[
            "pair_id", "repeat", "taxon_group", "scientific_name_meta", "region_name_meta",
            "target_rescue_minus_v1",
        ]].copy()
        scored["outer_fold"] = int(outer_fold)
        scored["predicted_rescue_minus_v1"] = estimator.predict(test[columns])
        scored["router_chosen_policy"] = [
            choose_router_policy(value, policy)
            for value in scored["predicted_rescue_minus_v1"]
        ]
        predictions.append(scored)
    prediction = pd.concat(predictions, ignore_index=True)

    fold = fold_audit.merge(
        prediction[["pair_id", "repeat", "outer_fold", "predicted_rescue_minus_v1", "router_chosen_policy"]],
        on=["pair_id", "repeat"],
        how="left",
        validate="one_to_one",
    )
    complete_mask = fold["fold_status"].eq("complete")
    if fold.loc[complete_mask, "predicted_rescue_minus_v1"].isna().any():
        raise RuntimeError("a complete router fold lacks an outer-held-out prediction")
    fold.loc[~complete_mask, "outer_fold"] = fold.loc[~complete_mask, "pair_id"].map(assignment)
    fold.loc[~complete_mask, "predicted_rescue_minus_v1"] = 0.0
    fold.loc[~complete_mask, "router_chosen_policy"] = "explicit_scientific_zero"
    fold["router_recovery_10km"] = np.where(
        fold["router_chosen_policy"].eq("frozen_rescue_v2"),
        pd.to_numeric(fold["rescue_recovery_10km"], errors="raise"),
        pd.to_numeric(fold["v1_recovery_10km"], errors="raise"),
    )
    fold.loc[~complete_mask, "router_recovery_10km"] = 0.0
    fold["router_minus_frozen_v1"] = (
        pd.to_numeric(fold["router_recovery_10km"], errors="raise")
        - pd.to_numeric(fold["v1_recovery_10km"], errors="raise")
    )

    pair = (
        fold.groupby(["pair_id", "taxon_group", "scientific_name", "region_name"], as_index=False)
        .agg(
            router_mean_recovery_10km=("router_recovery_10km", "mean"),
            frozen_v1_mean_recovery_10km=("v1_recovery_10km", "mean"),
            rescue_v2_mean_recovery_10km=("rescue_recovery_10km", "mean"),
            router_minus_frozen_v1=("router_minus_frozen_v1", "mean"),
            rescue_selected_folds=("router_chosen_policy", lambda x: int(pd.Series(x).eq("frozen_rescue_v2").sum())),
            complete_folds=("fold_status", lambda x: int(pd.Series(x).eq("complete").sum())),
            scientific_zero_folds=("fold_status", lambda x: int(pd.Series(x).eq("explicit_scientific_zero").sum())),
        )
        .sort_values("pair_id", kind="mergesort")
        .reset_index(drop=True)
    )
    if len(pair) != EXPECTED_PAIRS or pair["pair_id"].astype(int).tolist() != list(range(1, EXPECTED_PAIRS + 1)):
        raise RuntimeError("router development did not retain all 192 declared pairs")

    draws = int(cfg["bootstrap_draws"])
    seed = int(cfg["inference_seed"])
    primary = _inference(pair["router_minus_frozen_v1"].to_numpy(float), draws, seed)
    group_results: dict[str, object] = {}
    for group, subset in pair.groupby("taxon_group"):
        group_results[str(group)] = _inference(
            subset["router_minus_frozen_v1"].to_numpy(float),
            draws,
            seed + (1 if str(group) == "plant" else 2),
        )
    threshold = float(protocol["router"]["decision_threshold_absolute_recall"])
    primary_passed = bool(
        primary["mean_difference"] >= 0.015
        and primary["bootstrap_95ci_low"] > 0
        and primary["sign_flip_p"] < 0.05
    )
    group_guardrail_passed = all(
        result["mean_difference"] >= 0.015
        and result["bootstrap_95ci_low"] > 0
        and result["sign_flip_p"] < 0.05
        for result in group_results.values()
    )
    passed = bool(primary_passed and group_guardrail_passed)

    output.mkdir(parents=True, exist_ok=True)
    complete.to_csv(output / "router_training_rows.csv", index=False)
    fold.sort_values(["pair_id", "repeat"], kind="mergesort").to_csv(
        output / "fold_level_comparison.csv", index=False
    )
    pair.to_csv(output / "pair_level_comparison.csv", index=False)
    pd.DataFrame([
        {"pair_id": pair_id, "outer_fold": outer_fold}
        for pair_id, outer_fold in sorted(assignment.items())
    ]).to_csv(output / "outer_pair_assignment.csv", index=False)
    result = {
        "status": "vnext2_safe_router_development_evaluated",
        "protocol_fingerprint": fingerprint,
        "source_fresh_run_id": int(protocol["development_source"]["fresh_v2_run_id"]),
        "source_192_reclassified_as_development": True,
        "declared_pairs": EXPECTED_PAIRS,
        "evaluated_pairs": int(len(pair)),
        "evaluated_folds": int(len(fold)),
        "complete_training_rows": int(len(complete)),
        "scientific_zero_folds": int((~complete_mask).sum()),
        "router_threshold_absolute_recall": threshold,
        "router_rescue_selected_folds": int(fold["router_chosen_policy"].eq("frozen_rescue_v2").sum()),
        "router_v1_selected_folds": int(fold["router_chosen_policy"].eq("frozen_v1").sum()),
        "primary_inference": primary,
        "taxon_group_inference": group_results,
        "primary_gate_passed": primary_passed,
        "taxon_group_guardrail_passed": group_guardrail_passed,
        "development_gate_passed": passed,
        "candidate_frames_regenerated": False,
        "outcomes_available_to_router_at_test_inference": False,
        "new_untouched_confirmation_required": True,
    }
    (output / "development_manifest.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return result


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--pair-root", type=Path, required=True)
    command.add_argument("--protocol", dest="protocol_path", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    return command


if __name__ == "__main__":
    print(json.dumps(run(**vars(parser().parse_args())), indent=2, ensure_ascii=False))
