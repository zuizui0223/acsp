#!/usr/bin/env python3
"""Strict production aggregator for Practical Core untouched confirmation.

Infrastructure-only failure markers are retained as zero-recovery declared pairs.
Any pair that purports to contain a scientific artifact must pass all hashes and
leakage audits; incomplete/corrupted scientific artifacts abort aggregation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aggregate_practical_core_confirmation import (
    CONFIRMATION_PROTOCOL_PATH,
    CORE_PROTOCOL_PATH,
    EXPECTED_CONFIRMATION_PROTOCOL,
    EXPECTED_CORE_PROTOCOL,
    NONOPERATIONAL,
    OPTIONAL_SDM,
    PRIMARY,
    PRIMARY_COMPARATOR,
    _canonical_fingerprint,
    _operational_methods,
    _read_pair_artifact,
    method_summary,
    paired_inference,
    stratum_summary,
)


def build_pair_level_table_strict(
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
        scientific_pair_present = False

        if not pair_dir.exists():
            results = pd.DataFrame()
            artifact_status = "missing_pair_artifact_scored_zero"
        else:
            pair_manifest = pair_dir / "pair_manifest.json"
            fold_results = pair_dir / "fold_results.csv"
            infrastructure_marker = pair_dir / "unexpected_workflow_failure.json"
            if infrastructure_marker.exists() and not pair_manifest.exists() and not fold_results.exists():
                marker = json.loads(infrastructure_marker.read_text(encoding="utf-8"))
                if int(marker.get("pair_id", -1)) != pair_id:
                    raise ValueError(f"infrastructure failure marker pair mismatch: {infrastructure_marker}")
                results = pd.DataFrame()
                artifact_status = "unexpected_workflow_failure_scored_zero"
            else:
                # Any other existing directory claims to be a scientific pair
                # artifact and therefore must pass the full strict reader.
                results, audits = _read_pair_artifact(
                    pair_dir, core_fp, confirmation_fp, expected_repeats
                )
                scientific_pair_present = True
                artifact_status = "scientific_pair_artifact_present"
                audit_rows.extend(audits)
                results["artifact_pair_present"] = True
                fold_frames.append(results)

        if not scientific_pair_present:
            audit_rows.append(
                {
                    "pair_id": pair_id,
                    "repeat": np.nan,
                    "fold_dir": "",
                    "artifact_status": artifact_status,
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
                    pd.to_numeric(method_rows.get("heldout_recall"), errors="coerce").dropna()
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
                by_repeat: dict[int, float] = {}
                if not method_rows.empty:
                    for repeat, frame in method_rows.groupby("repeat", sort=False):
                        values = pd.to_numeric(frame["heldout_recall"], errors="coerce").dropna()
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
                    "pair_artifact_present": scientific_pair_present,
                    "pair_artifact_status": artifact_status,
                }
            )

    pair_level = pd.DataFrame(pair_rows)
    audit = pd.DataFrame(audit_rows)
    folds = pd.concat(fold_frames, ignore_index=True) if fold_frames else pd.DataFrame()
    return pair_level, audit, folds


def _incomplete_verified_pairs(
    cohort: pd.DataFrame,
    audit: pd.DataFrame,
    expected_repeats: int,
) -> list[int]:
    verified = audit[audit["artifact_status"].eq("verified")].copy()
    counts = verified.groupby("pair_id")["repeat"].nunique().to_dict() if not verified.empty else {}
    return sorted(
        int(pair_id)
        for pair_id in cohort["pair_id"].astype(int)
        if int(counts.get(int(pair_id), 0)) < int(expected_repeats)
    )


def run(args: argparse.Namespace) -> dict[str, Any]:
    _, core_fp = _canonical_fingerprint(CORE_PROTOCOL_PATH, "fingerprint")
    protocol, confirmation_fp = _canonical_fingerprint(
        CONFIRMATION_PROTOCOL_PATH, "protocol_fingerprint"
    )
    if core_fp != EXPECTED_CORE_PROTOCOL or confirmation_fp != EXPECTED_CONFIRMATION_PROTOCOL:
        raise ValueError("production aggregator constants do not match frozen protocols")

    cohort = pd.read_csv(args.cohort)
    if len(cohort) != int(protocol["cohort"]["pair_count"]):
        raise ValueError(
            f"cohort has {len(cohort)} rows, expected {protocol['cohort']['pair_count']}"
        )
    if cohort["scientific_name"].astype(str).duplicated().any():
        raise ValueError("confirmation cohort contains duplicate scientific names")

    pair_level, artifact_audit, folds = build_pair_level_table_strict(
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
    method_summary(pair_level).to_csv(output / "method_summary.csv", index=False)
    stratum_summary(pair_level).to_csv(output / "stratum_summary.csv", index=False)

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
    pd.DataFrame(contrast_rows).to_csv(output / "pair_level_inference.csv", index=False)

    primary = contrast_rows[0]
    minimum_gain = float(inference_cfg["minimum_practical_absolute_recall_gain"])
    all_declared = int(primary["pairs"]) == int(protocol["cohort"]["pair_count"])
    gate_passed = bool(
        np.isfinite(primary["mean_difference"])
        and primary["mean_difference"] >= minimum_gain
        and primary["bootstrap_95ci_low"] > 0.0
        and primary["sign_flip_p"] < 0.05
        and all_declared
    )
    primary_gate = {
        **primary,
        "minimum_practical_absolute_recall_gain": minimum_gain,
        "all_declared_pairs_in_contrast": all_declared,
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

    incomplete_pairs = _incomplete_verified_pairs(
        cohort,
        artifact_audit,
        int(protocol["outer_validation"]["repeats"]),
    )
    marker_pairs = sorted(
        artifact_audit.loc[
            artifact_audit["artifact_status"].eq(
                "unexpected_workflow_failure_scored_zero"
            ),
            "pair_id",
        ]
        .dropna()
        .astype(int)
        .unique()
        .tolist()
    )
    absent_pairs = sorted(
        artifact_audit.loc[
            artifact_audit["artifact_status"].eq("missing_pair_artifact_scored_zero"),
            "pair_id",
        ]
        .dropna()
        .astype(int)
        .unique()
        .tolist()
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
        "pairs_with_fewer_than_all_verified_fold_artifacts": incomplete_pairs,
        "pairs_with_fewer_than_all_verified_fold_artifact_count": int(len(incomplete_pairs)),
        "unexpected_workflow_failure_pairs_scored_zero": marker_pairs,
        "missing_pair_artifact_pairs_scored_zero": absent_pairs,
        "existing_scientific_artifacts_hash_verified": True,
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
