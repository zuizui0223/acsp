#!/usr/bin/env python3
"""Aggregate the frozen ACSP Practical Core confirmation artifacts.

The taxon-region pair is the inference unit. Missing declared pair artifacts are
retained as zero recovery for operational same-pool methods. Existing artifacts
must pass their recorded SHA-256 and leakage audits; corrupted artifacts abort
aggregation rather than being converted into favorable or unfavorable outcomes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


CORE_PROTOCOL_PATH = Path("validation/acsp_practical_core_protocol.json")
CONFIRMATION_PROTOCOL_PATH = Path(
    "validation/acsp_practical_core_untouched_confirmation_protocol.json"
)
EXPECTED_CORE_PROTOCOL = (
    "3dafe65b6bef09b1878d688730d5feb64a8de58843b06ff9fb14a876512d4905"
)
EXPECTED_CONFIRMATION_PROTOCOL = (
    "cd27dc5416057b574e58742bfe001307338a20aedb63ce1bac431588dc58eee9"
)
PRIMARY = "acsp_practical_core"
PRIMARY_COMPARATOR = "official_grts_proportional_local_mindis10km"
OPTIONAL_SDM = "fitted_sdm_top_k_when_eligible"
NONOPERATIONAL = "heldout_greedy_oracle_nonoperational"
FORBIDDEN_PRE_OUTCOME_COLUMNS = {
    "_outer_occurrence_id",
    "_outer_block",
    "covered_heldout_ids",
    "heldout_distances_km",
    "all_heldout_ids",
    "heldout_recall",
}


def _canonical_fingerprint(path: Path, field: str) -> tuple[dict[str, Any], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = str(payload.pop(field, ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if not expected or expected != calculated:
        raise ValueError(
            f"fingerprint mismatch for {path}: file={expected!r}, calculated={calculated!r}"
        )
    payload[field] = expected
    return payload, calculated


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_fold_artifact(
    fold_dir: Path,
    core_fp: str,
    confirmation_fp: str,
) -> dict[str, Any]:
    manifest_path = fold_dir / "fold_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"existing fold directory lacks manifest: {fold_dir}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("practical_core_fingerprint") != core_fp:
        raise ValueError(f"Practical Core fingerprint mismatch in {manifest_path}")
    if manifest.get("confirmation_protocol_fingerprint") != confirmation_fp:
        raise ValueError(f"confirmation fingerprint mismatch in {manifest_path}")
    if manifest.get("outcomes_available_to_operational_selectors") is not False:
        raise ValueError(f"leakage flag is not false in {manifest_path}")

    files = manifest.get("files", {})
    for name, record in files.items():
        path = fold_dir / str(record["path"])
        if not path.exists():
            raise FileNotFoundError(f"manifested file missing: {path}")
        actual = _sha256(path)
        if actual != str(record["sha256"]):
            raise ValueError(
                f"artifact SHA-256 mismatch for {path}: "
                f"manifest={record['sha256']}, actual={actual}"
            )

    candidate_path = fold_dir / "candidate_pool_pre_outcome.csv"
    if candidate_path.exists() and candidate_path.stat().st_size:
        candidates = pd.read_csv(candidate_path)
        forbidden = FORBIDDEN_PRE_OUTCOME_COLUMNS & set(candidates.columns)
        if forbidden:
            raise ValueError(
                f"pre-outcome candidate pool contains forbidden outcome columns "
                f"{sorted(forbidden)} in {candidate_path}"
            )

    decision_path = fold_dir / "deterministic_decisions_pre_outcome.json"
    if decision_path.exists():
        decisions = json.loads(decision_path.read_text(encoding="utf-8"))
        if decisions.get("outcomes_available_to_selectors") is not False:
            raise ValueError(f"deterministic decision leakage flag failed: {decision_path}")

    grts_path = fold_dir / "grts_draws_pre_outcome.csv"
    grts_rows = 0
    grts_false_flags = True
    if grts_path.exists() and grts_path.stat().st_size:
        grts = pd.read_csv(grts_path)
        grts_rows = int(len(grts))
        if "outcomes_available_to_selector" in grts.columns:
            values = (
                grts["outcomes_available_to_selector"]
                .astype(str)
                .str.strip()
                .str.lower()
            )
            grts_false_flags = bool(values.isin({"false", "0"}).all())
        if not grts_false_flags:
            raise ValueError(f"GRTS pre-outcome leakage flag failed: {grts_path}")
        forbidden = FORBIDDEN_PRE_OUTCOME_COLUMNS & set(grts.columns)
        if forbidden:
            raise ValueError(
                f"pre-outcome GRTS table contains forbidden outcome columns "
                f"{sorted(forbidden)} in {grts_path}"
            )

    return {
        "pair_id": int(manifest["pair_id"]),
        "repeat": int(manifest["repeat"]),
        "fold_dir": str(fold_dir),
        "artifact_status": "verified",
        "candidate_pool": int(manifest.get("candidate_pool", 0)),
        "training_records": int(manifest.get("training_records", 0)),
        "heldout_records": int(manifest.get("heldout_records", 0)),
        "grts_pre_outcome_rows": grts_rows,
        "grts_outcome_flags_false": grts_false_flags,
    }


def _read_pair_artifact(
    pair_dir: Path,
    core_fp: str,
    confirmation_fp: str,
    expected_repeats: int,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    pair_manifest_path = pair_dir / "pair_manifest.json"
    fold_results_path = pair_dir / "fold_results.csv"
    if not pair_manifest_path.exists() or not fold_results_path.exists():
        raise FileNotFoundError(f"pair artifact is incomplete: {pair_dir}")
    pair_manifest = json.loads(pair_manifest_path.read_text(encoding="utf-8"))
    if pair_manifest.get("practical_core_fingerprint") != core_fp:
        raise ValueError(f"pair core fingerprint mismatch: {pair_manifest_path}")
    if pair_manifest.get("confirmation_protocol_fingerprint") != confirmation_fp:
        raise ValueError(f"pair confirmation fingerprint mismatch: {pair_manifest_path}")
    if _sha256(fold_results_path) != pair_manifest.get("fold_result_sha256"):
        raise ValueError(f"pair fold-results hash mismatch: {fold_results_path}")

    audits = []
    for repeat in range(1, expected_repeats + 1):
        fold_dir = pair_dir / f"fold_{repeat:03d}"
        if fold_dir.exists():
            audits.append(_verify_fold_artifact(fold_dir, core_fp, confirmation_fp))
    results = pd.read_csv(fold_results_path)
    return results, audits


def _operational_methods(protocol: dict[str, Any]) -> list[str]:
    methods = []
    for method in protocol["same_pool_methods"]:
        if method == NONOPERATIONAL:
            continue
        methods.append(str(method))
    return methods


def build_pair_level_table(
    cohort: pd.DataFrame,
    pair_root: Path,
    protocol: dict[str, Any],
    core_fp: str,
    confirmation_fp: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    expected_repeats = int(protocol["outer_validation"]["repeats"])
    operational = _operational_methods(protocol)
    pair_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    fold_frames: list[pd.DataFrame] = []

    for _, pair in cohort.sort_values("pair_id").iterrows():
        pair_id = int(pair.pair_id)
        pair_dir = pair_root / f"pair_{pair_id:03d}"
        if pair_dir.exists():
            results, audits = _read_pair_artifact(
                pair_dir, core_fp, confirmation_fp, expected_repeats
            )
            audit_rows.extend(audits)
            results["artifact_pair_present"] = True
            fold_frames.append(results)
        else:
            results = pd.DataFrame()
            audit_rows.append(
                {
                    "pair_id": pair_id,
                    "repeat": np.nan,
                    "fold_dir": "",
                    "artifact_status": "missing_pair_artifact_scored_zero",
                    "candidate_pool": 0,
                    "training_records": 0,
                    "heldout_records": 0,
                    "grts_pre_outcome_rows": 0,
                    "grts_outcome_flags_false": True,
                }
            )

        for method in operational:
            if method == OPTIONAL_SDM:
                method_rows = (
                    results[results["decision_method"].astype(str).eq(method)].copy()
                    if not results.empty
                    else pd.DataFrame()
                )
                finite = (
                    pd.to_numeric(method_rows.get("heldout_recall"), errors="coerce")
                    .dropna()
                    if not method_rows.empty
                    else pd.Series(dtype=float)
                )
                pair_recall = float(finite.mean()) if len(finite) else np.nan
                repeats_observed = int(len(finite))
            else:
                method_rows = (
                    results[results["decision_method"].astype(str).eq(method)].copy()
                    if not results.empty
                    else pd.DataFrame()
                )
                by_repeat = {}
                if not method_rows.empty:
                    for repeat, frame in method_rows.groupby("repeat", sort=False):
                        values = pd.to_numeric(
                            frame["heldout_recall"], errors="coerce"
                        ).dropna()
                        by_repeat[int(repeat)] = float(values.iloc[0]) if len(values) else 0.0
                recalls = [
                    by_repeat.get(repeat, 0.0)
                    for repeat in range(1, expected_repeats + 1)
                ]
                pair_recall = float(np.mean(recalls))
                repeats_observed = int(len(by_repeat))

            pair_rows.append(
                {
                    "pair_id": pair_id,
                    "scientific_name": str(pair.scientific_name),
                    "taxon_group": str(pair.taxon_group),
                    "geographic_stratum": str(pair.geographic_stratum),
                    "region_name": str(pair.region_name),
                    "record_count_stratum": int(pair.record_count_stratum),
                    "decision_method": method,
                    "pair_mean_recall": pair_recall,
                    "expected_repeats": expected_repeats,
                    "observed_repeats": repeats_observed,
                    "pair_artifact_present": bool(pair_dir.exists()),
                }
            )

    pair_level = pd.DataFrame(pair_rows)
    audit = pd.DataFrame(audit_rows)
    folds = pd.concat(fold_frames, ignore_index=True) if fold_frames else pd.DataFrame()
    return pair_level, audit, folds


def paired_inference(
    pair_level: pd.DataFrame,
    method_a: str,
    method_b: str,
    *,
    bootstrap_draws: int,
    sign_flip_draws: int,
    seed: int,
) -> dict[str, Any]:
    pivot = pair_level.pivot(
        index="pair_id", columns="decision_method", values="pair_mean_recall"
    )
    if method_a not in pivot.columns or method_b not in pivot.columns:
        raise ValueError(f"contrast unavailable: {method_a} - {method_b}")
    data = pivot[[method_a, method_b]].dropna()
    diff = (data[method_a] - data[method_b]).to_numpy(float)
    if len(diff) == 0:
        return {
            "method_a": method_a,
            "method_b": method_b,
            "pairs": 0,
            "mean_difference": np.nan,
            "bootstrap_95ci_low": np.nan,
            "bootstrap_95ci_high": np.nan,
            "sign_flip_p": np.nan,
        }

    observed = float(np.mean(diff))
    rng = np.random.default_rng(int(seed))
    if bootstrap_draws > 0:
        samples = rng.integers(0, len(diff), size=(int(bootstrap_draws), len(diff)))
        boot = diff[samples].mean(axis=1)
        low, high = np.quantile(boot, [0.025, 0.975])
    else:
        low = high = np.nan

    if sign_flip_draws > 0:
        signs = rng.choice(
            np.array([-1.0, 1.0]),
            size=(int(sign_flip_draws), len(diff)),
            replace=True,
        )
        permuted = (signs * diff[None, :]).mean(axis=1)
        p_value = (1.0 + float(np.sum(np.abs(permuted) >= abs(observed)))) / (
            int(sign_flip_draws) + 1.0
        )
    else:
        p_value = np.nan

    return {
        "method_a": method_a,
        "method_b": method_b,
        "pairs": int(len(diff)),
        "mean_method_a": float(data[method_a].mean()),
        "mean_method_b": float(data[method_b].mean()),
        "mean_difference": observed,
        "bootstrap_95ci_low": float(low),
        "bootstrap_95ci_high": float(high),
        "sign_flip_p": float(p_value),
        "positive_pairs": int(np.sum(diff > 0)),
        "negative_pairs": int(np.sum(diff < 0)),
        "tied_pairs": int(np.sum(np.isclose(diff, 0.0))),
        "difference_sd": float(np.std(diff, ddof=1)) if len(diff) > 1 else 0.0,
    }


def method_summary(pair_level: pd.DataFrame) -> pd.DataFrame:
    return (
        pair_level.groupby("decision_method", as_index=False)
        .agg(
            declared_pairs=("pair_id", "nunique"),
            finite_pairs=(
                "pair_mean_recall",
                lambda values: int(pd.Series(values).notna().sum()),
            ),
            mean_pair_recall=("pair_mean_recall", "mean"),
            median_pair_recall=("pair_mean_recall", "median"),
            pair_artifacts_present=("pair_artifact_present", "sum"),
        )
        .sort_values("decision_method")
        .reset_index(drop=True)
    )


def stratum_summary(pair_level: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for dimension in (
        "taxon_group",
        "geographic_stratum",
        "region_name",
        "record_count_stratum",
    ):
        summary = (
            pair_level.groupby([dimension, "decision_method"], as_index=False)
            .agg(
                pairs=("pair_id", "nunique"),
                mean_pair_recall=("pair_mean_recall", "mean"),
            )
            .rename(columns={dimension: "stratum_value"})
        )
        summary.insert(0, "stratum_dimension", dimension)
        frames.append(summary)
    return pd.concat(frames, ignore_index=True)


def run(args: argparse.Namespace) -> dict[str, Any]:
    _, core_fp = _canonical_fingerprint(CORE_PROTOCOL_PATH, "fingerprint")
    protocol, confirmation_fp = _canonical_fingerprint(
        CONFIRMATION_PROTOCOL_PATH, "protocol_fingerprint"
    )
    if core_fp != EXPECTED_CORE_PROTOCOL or confirmation_fp != EXPECTED_CONFIRMATION_PROTOCOL:
        raise ValueError("aggregator constants do not match frozen protocols")
    cohort = pd.read_csv(args.cohort)
    if len(cohort) != int(protocol["cohort"]["pair_count"]):
        raise ValueError(
            f"cohort has {len(cohort)} rows, expected {protocol['cohort']['pair_count']}"
        )
    if cohort["scientific_name"].astype(str).duplicated().any():
        raise ValueError("confirmation cohort contains duplicate scientific names")

    pair_level, artifact_audit, folds = build_pair_level_table(
        cohort,
        Path(args.pair_root),
        protocol,
        core_fp,
        confirmation_fp,
    )
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    pair_level.to_csv(output / "pair_level_recall.csv", index=False)
    artifact_audit.to_csv(output / "artifact_audit.csv", index=False)
    folds.to_csv(output / "all_fold_results.csv", index=False)
    summaries = method_summary(pair_level)
    summaries.to_csv(output / "method_summary.csv", index=False)
    strata = stratum_summary(pair_level)
    strata.to_csv(output / "stratum_summary.csv", index=False)

    inference_cfg = protocol["inference"]
    bootstrap_draws = int(inference_cfg["bootstrap_draws"])
    sign_flip_draws = int(inference_cfg["sign_flip_draws"])
    seed = int(protocol["cohort"]["seed"])
    contrasts = [
        (PRIMARY, PRIMARY_COMPARATOR),
        (PRIMARY, "official_grts_proportional_local"),
        (PRIMARY, "official_grts_equal"),
        (PRIMARY, "frozen_acsp_v1_historical"),
        (PRIMARY, "same_pool_random_mean"),
    ]
    contrast_rows = [
        paired_inference(
            pair_level,
            first,
            second,
            bootstrap_draws=bootstrap_draws,
            sign_flip_draws=sign_flip_draws,
            seed=seed + index,
        )
        for index, (first, second) in enumerate(contrasts)
    ]
    contrast_table = pd.DataFrame(contrast_rows)
    contrast_table.to_csv(output / "pair_level_inference.csv", index=False)

    primary = contrast_rows[0]
    minimum_gain = float(inference_cfg["minimum_practical_absolute_recall_gain"])
    gate_passed = bool(
        np.isfinite(primary["mean_difference"])
        and primary["mean_difference"] >= minimum_gain
        and primary["bootstrap_95ci_low"] > 0.0
        and primary["sign_flip_p"] < 0.05
        and int(primary["pairs"]) == int(protocol["cohort"]["pair_count"])
    )
    primary_gate = {
        **primary,
        "minimum_practical_absolute_recall_gain": minimum_gain,
        "all_declared_pairs_in_contrast": int(primary["pairs"])
        == int(protocol["cohort"]["pair_count"]),
        "gate_passed": gate_passed,
        "claim_if_failed": (
            "No same-pool superiority claim; retain negative/equivalent result and "
            "do not retune on this cohort."
        ),
    }
    (output / "primary_gate.json").write_text(
        json.dumps(primary_gate, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    missing_pairs = sorted(
        set(cohort["pair_id"].astype(int))
        - set(
            artifact_audit.loc[
                artifact_audit["artifact_status"].eq("verified"), "pair_id"
            ]
            .dropna()
            .astype(int)
        )
    )
    manifest = {
        "status": "primary_confirmation_aggregated",
        "practical_core_fingerprint": core_fp,
        "confirmation_protocol_fingerprint": confirmation_fp,
        "declared_pairs": int(len(cohort)),
        "pair_level_rows": int(len(pair_level)),
        "primary_method": PRIMARY,
        "primary_comparator": PRIMARY_COMPARATOR,
        "primary_gate_passed": gate_passed,
        "primary_gate": primary_gate,
        "missing_or_no_verified_fold_pairs": missing_pairs,
        "missing_or_no_verified_fold_pair_count": int(len(missing_pairs)),
        "existing_artifacts_hash_verified": True,
        "heldout_leakage_audit_passed": True,
        "fitted_sdm_secondary_stage_complete": bool(
            pair_level.loc[
                pair_level["decision_method"].eq(OPTIONAL_SDM), "pair_mean_recall"
            ]
            .notna()
            .all()
        ),
        "no_retuning_after_outcome": bool(protocol["no_retuning_after_outcome"]),
    }
    (output / "confirmation_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--cohort", type=Path, required=True)
    command.add_argument("--pair-root", type=Path, required=True)
    command.add_argument(
        "--output",
        type=Path,
        default=Path("practical_core_confirmation_aggregate"),
    )
    return command


if __name__ == "__main__":
    print(json.dumps(run(parser().parse_args()), indent=2, ensure_ascii=False))
