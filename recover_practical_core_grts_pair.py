#!/usr/bin/env python3
"""Recover only the frozen GRTS comparator from immutable source pair artifacts.

The source run already froze training occurrences, held-out occurrences, candidate
pools, ACSP decisions, random controls, and all scientific fingerprints. This QA
recovery never fetches GBIF data or rebuilds any of those objects. For eligible
folds it reruns only official GRTS from the frozen pre-outcome candidate CSV with
the original predeclared seeds, then attaches the already-frozen held-out outcome.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aggregate_practical_core_confirmation import _read_pair_artifact
from run_practical_core_confirmation_pair import (
    CONFIRMATION_PROTOCOL_PATH,
    CORE_PROTOCOL_PATH,
    EXPECTED_CONFIRMATION_PROTOCOL,
    EXPECTED_CORE_PROTOCOL,
    GRTS_METHODS,
    _canonical_fingerprint,
    _coverage_sets,
    _recall,
    _sha256,
    _split_ids,
)

SOURCE_RUN_ID = 31710136111
SOURCE_HEAD_SHA = "c7ff4ab5c0c85a8df7c389c62f44a07a11e4aa89"
RECOVERY_ADAPTER = Path("benchmark_methods/grts_batch_candidate_frame_recovery.R")
EXPECTED_PARSE_ERROR = "unexpected '='"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _run_grts(candidate_path: Path, output_path: Path, pair_id: int, repeat_id: int,
              protocol: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    grts = protocol["grts"]
    command = [
        "Rscript", str(RECOVERY_ADAPTER),
        "--input", str(candidate_path),
        "--output", str(output_path),
        "--draws", str(int(grts["draws_per_fold"])),
        "--seed-base", str(int(grts["seed_base"])),
        "--pair-id", str(int(pair_id)),
        "--repeat", str(int(repeat_id)),
        "--k", str(int(protocol["practical_core"]["top_k"])),
        "--replacements", str(int(grts["replacement_sites"])),
        "--score-col", "component_local_habitat_score",
    ]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    audit: dict[str, Any] = {
        "command": command,
        "returncode": int(completed.returncode),
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
        "outcomes_available_to_selector": False,
        "recovery_source_run_id": SOURCE_RUN_ID,
        "recovery_source_head_sha": SOURCE_HEAD_SHA,
        "candidate_regenerated": False,
        "heldout_regenerated": False,
        "outer_split_regenerated": False,
        "acsp_decision_regenerated": False,
    }
    if completed.returncode != 0 or not output_path.exists():
        audit["status"] = "grts_recovery_process_failure"
        return pd.DataFrame(), audit
    draws = pd.read_csv(output_path)
    audit["status"] = "ok"
    audit["rows"] = int(len(draws))
    audit["variants"] = sorted(draws["variant"].dropna().astype(str).unique().tolist())
    return draws, audit


def _score_grts(candidates: pd.DataFrame, heldout: pd.DataFrame, draws: pd.DataFrame,
                pair_meta: dict[str, Any], repeat_id: int,
                protocol: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    radius = float(protocol["practical_core"]["recovery_radius_km"])
    coverage, all_ids = _coverage_sets(candidates, heldout, radius)
    expected_draws = int(protocol["grts"]["draws_per_fold"])
    fold_rows: list[dict[str, Any]] = []
    scored_rows: list[dict[str, Any]] = []

    for variant in GRTS_METHODS:
        variant_rows = draws[draws["variant"].astype(str).eq(variant)].copy()
        recalls: list[float] = []
        successful = 0
        for draw_index in range(1, expected_draws + 1):
            selected = variant_rows[pd.to_numeric(variant_rows["draw_index"], errors="coerce").eq(draw_index)]
            if len(selected) == 1:
                row = selected.iloc[0].to_dict()
                ids = _split_ids(row.get("base_ids"))
                error_raw = row.get("error_message")
                error_message = "" if pd.isna(error_raw) else str(error_raw)
                value = _recall(ids, coverage, all_ids) if ids else 0.0
                if ids and not error_message:
                    successful += 1
            else:
                row = {
                    "pair_id": int(pair_meta["pair_id"]),
                    "repeat": int(repeat_id),
                    "variant": variant,
                    "draw_index": int(draw_index),
                    "seed": np.nan,
                    "base_count": 0,
                    "base_ids": "",
                    "replacement_count": 0,
                    "replacement_ids": "",
                    "warning_message": "",
                    "error_message": "missing_recovered_pre_outcome_draw",
                }
                value = 0.0
            row["heldout_recall"] = float(value)
            row["heldout_records"] = int(len(all_ids))
            row["outcome_attached_after_selection"] = True
            scored_rows.append(row)
            recalls.append(float(value))

        status = "ok" if successful == expected_draws else (
            "partial_grts_failure" if successful else "grts_failure"
        )
        fold_rows.append({
            "pair_id": int(pair_meta["pair_id"]),
            "repeat": int(repeat_id),
            "taxon_group": str(pair_meta["taxon_group"]),
            "scientific_name": str(pair_meta["scientific_name"]),
            "region_name": str(pair_meta["region_name"]),
            "decision_method": variant,
            "method_status": status,
            "heldout_recall": float(np.mean(recalls)) if recalls else 0.0,
            "heldout_records": int(len(all_ids)),
            "candidate_pool": int(len(candidates)),
            "selected_ids": "",
            "grts_successful_draws": int(successful),
            "grts_expected_draws": int(expected_draws),
        })
    return pd.DataFrame(fold_rows), pd.DataFrame(scored_rows)


def _replace_grts_rows(source: pd.DataFrame, recovered: pd.DataFrame) -> pd.DataFrame:
    out = source.copy()
    for _, row in recovered.iterrows():
        mask = (
            pd.to_numeric(out["repeat"], errors="coerce").eq(int(row["repeat"]))
            & out["decision_method"].astype(str).eq(str(row["decision_method"]))
        )
        if int(mask.sum()) != 1:
            raise ValueError(f"expected exactly one frozen GRTS result row for {row['repeat']} {row['decision_method']}")
        for column, value in row.items():
            if column not in out.columns:
                out[column] = np.nan
            out.loc[mask, column] = value
    return out


def run(args: argparse.Namespace) -> dict[str, Any]:
    _, core_fp = _canonical_fingerprint(CORE_PROTOCOL_PATH, "fingerprint")
    protocol, confirmation_fp = _canonical_fingerprint(CONFIRMATION_PROTOCOL_PATH, "protocol_fingerprint")
    if core_fp != EXPECTED_CORE_PROTOCOL or confirmation_fp != EXPECTED_CONFIRMATION_PROTOCOL:
        raise ValueError("recovery constants do not match frozen scientific protocols")

    cohort = pd.read_csv(args.cohort)
    selected = cohort[pd.to_numeric(cohort["pair_id"], errors="coerce").eq(args.pair_id)]
    if len(selected) != 1:
        raise ValueError(f"pair_id {args.pair_id} is not uniquely present in frozen cohort")
    pair = selected.iloc[0]
    pair_meta = {
        "pair_id": int(pair.pair_id),
        "scientific_name": str(pair.scientific_name),
        "taxon_group": str(pair.taxon_group),
        "region_name": str(pair.region_name),
    }

    source_pair = Path(args.source_root) / f"pair_{int(pair.pair_id):03d}"
    destination = Path(args.output) / f"pair_{int(pair.pair_id):03d}"
    if not source_pair.exists():
        raise FileNotFoundError(f"source pair artifact missing: {source_pair}")

    expected_repeats = int(protocol["outer_validation"]["repeats"])
    source_results, _ = _read_pair_artifact(source_pair, core_fp, confirmation_fp, expected_repeats)
    source_pair_manifest_sha = _sha256(source_pair / "pair_manifest.json")
    source_fold_results_sha = _sha256(source_pair / "fold_results.csv")

    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source_pair, destination)

    pair_manifest = json.loads((source_pair / "pair_manifest.json").read_text(encoding="utf-8"))
    recovered_pair_results = source_results.copy()
    recovered_folds = 0
    preserved_small_pool_folds = 0

    for repeat_id in range(1, expected_repeats + 1):
        source_fold = source_pair / f"fold_{repeat_id:03d}"
        dest_fold = destination / f"fold_{repeat_id:03d}"
        if not source_fold.exists():
            continue
        source_manifest = json.loads((source_fold / "fold_manifest.json").read_text(encoding="utf-8"))
        source_manifest_sha = _sha256(source_fold / "fold_manifest.json")
        candidate_source = source_fold / "candidate_pool_pre_outcome.csv"
        candidate_dest = dest_fold / "candidate_pool_pre_outcome.csv"
        if _sha256(candidate_source) != _sha256(candidate_dest):
            raise ValueError("candidate copy changed before GRTS recovery")
        candidates = pd.read_csv(candidate_dest)
        top_k = int(protocol["practical_core"]["top_k"])
        if len(candidates) < top_k:
            preserved_small_pool_folds += 1
            continue

        old_audit = json.loads((source_fold / "grts_process_audit.json").read_text(encoding="utf-8"))
        if old_audit.get("status") != "grts_process_failure" or EXPECTED_PARSE_ERROR not in str(old_audit.get("stderr_tail", "")):
            raise ValueError(f"fold {repeat_id} is not the predeclared reserved-word parser failure")

        # Operational recovery selection happens here, before this process reads
        # the already-frozen held-out table below.
        draw_path = dest_fold / "grts_draws_pre_outcome.csv"
        draws, recovery_audit = _run_grts(draw_path=draw_path, candidate_path=candidate_dest,
                                          pair_id=int(pair.pair_id), repeat_id=repeat_id,
                                          protocol=protocol)
        if recovery_audit.get("status") != "ok":
            raise RuntimeError(f"GRTS recovery process failed for pair {pair.pair_id}, repeat {repeat_id}: {recovery_audit}")
        expected_rows = 3 * int(protocol["grts"]["draws_per_fold"])
        if len(draws) != expected_rows:
            raise ValueError(f"recovered GRTS row count {len(draws)} != {expected_rows}")
        if not draws["outcomes_available_to_selector"].astype(str).str.lower().isin({"false", "0"}).all():
            raise ValueError("recovered GRTS pre-outcome table exposes outcomes")
        for variant in GRTS_METHODS:
            variant_rows = draws[draws["variant"].astype(str).eq(variant)]
            if len(variant_rows) != int(protocol["grts"]["draws_per_fold"]):
                raise ValueError(f"incomplete recovered draw set for {variant}")

        recovery_audit.update({
            "status": "ok",
            "source_grts_process_audit_sha256": _sha256(source_fold / "grts_process_audit.json"),
            "source_fold_manifest_sha256": source_manifest_sha,
            "candidate_pool_sha256": _sha256(candidate_dest),
            "written_from_frozen_pre_outcome_candidate": True,
            "source_failure_reason": "R reserved-word parser failure before any GRTS draw",
        })
        _write_json(dest_fold / "grts_process_audit.json", recovery_audit)

        # Only after GRTS choices are frozen do we read the source outcome table.
        heldout_dest = dest_fold / "held_out_occurrences.csv"
        heldout = pd.read_csv(heldout_dest)
        fold_grts, scored_grts = _score_grts(candidates, heldout, draws, pair_meta, repeat_id, protocol)
        scored_grts.to_csv(dest_fold / "grts_draws_scored.csv", index=False)

        source_fold_result = pd.read_csv(source_fold / "fold_result.csv")
        recovered_fold_result = _replace_grts_rows(source_fold_result, fold_grts)
        source_non_grts = source_fold_result[~source_fold_result["decision_method"].astype(str).isin(GRTS_METHODS)].reset_index(drop=True)
        recovered_non_grts = recovered_fold_result[~recovered_fold_result["decision_method"].astype(str).isin(GRTS_METHODS)].reset_index(drop=True)
        pd.testing.assert_frame_equal(source_non_grts, recovered_non_grts, check_dtype=False, check_exact=True)
        recovered_fold_result.to_csv(dest_fold / "fold_result.csv", index=False)
        recovered_pair_results = _replace_grts_rows(recovered_pair_results, fold_grts)

        manifest = json.loads((dest_fold / "fold_manifest.json").read_text(encoding="utf-8"))
        for key in ("training_occurrences", "candidate_pool_pre_outcome", "deterministic_decisions_pre_outcome", "held_out_occurrences"):
            source_record = source_manifest["files"][key]
            source_path = source_fold / source_record["path"]
            dest_path = dest_fold / source_record["path"]
            if _sha256(source_path) != _sha256(dest_path):
                raise ValueError(f"immutable source file changed during recovery: {key}")
        for key, filename in {
            "grts_draws_pre_outcome": "grts_draws_pre_outcome.csv",
            "grts_process_audit": "grts_process_audit.json",
            "fold_result": "fold_result.csv",
            "grts_draws_scored": "grts_draws_scored.csv",
        }.items():
            manifest["files"][key] = {"path": filename, "sha256": _sha256(dest_fold / filename)}
        manifest["grts_recovery"] = {
            "source_run_id": SOURCE_RUN_ID,
            "source_head_sha": SOURCE_HEAD_SHA,
            "source_fold_manifest_sha256": source_manifest_sha,
            "source_candidate_pool_sha256": _sha256(candidate_source),
            "source_heldout_sha256": _sha256(source_fold / "held_out_occurrences.csv"),
            "source_training_sha256": _sha256(source_fold / "training_occurrences.csv"),
            "candidate_regenerated": False,
            "heldout_regenerated": False,
            "training_regenerated": False,
            "outer_split_regenerated": False,
            "acsp_decision_regenerated": False,
            "recovery_selector_read_heldout_before_selection": False,
            "reason": "implementation-only recovery of R reserved-word parser failure",
        }
        _write_json(dest_fold / "fold_manifest.json", manifest)
        recovered_folds += 1

    source_non_grts = source_results[~source_results["decision_method"].astype(str).isin(GRTS_METHODS)].reset_index(drop=True)
    recovered_non_grts = recovered_pair_results[~recovered_pair_results["decision_method"].astype(str).isin(GRTS_METHODS)].reset_index(drop=True)
    pd.testing.assert_frame_equal(source_non_grts, recovered_non_grts, check_dtype=False, check_exact=True)
    recovered_pair_results.to_csv(destination / "fold_results.csv", index=False)

    recovered_pair_manifest = json.loads((destination / "pair_manifest.json").read_text(encoding="utf-8"))
    recovered_pair_manifest["fold_result_sha256"] = _sha256(destination / "fold_results.csv")
    recovered_pair_manifest["grts_recovery"] = {
        "source_run_id": SOURCE_RUN_ID,
        "source_head_sha": SOURCE_HEAD_SHA,
        "source_pair_manifest_sha256": source_pair_manifest_sha,
        "source_fold_results_sha256": source_fold_results_sha,
        "recovered_folds": int(recovered_folds),
        "preserved_small_candidate_pool_folds": int(preserved_small_pool_folds),
        "gbif_refetched": False,
        "candidate_pool_regenerated": False,
        "outer_split_regenerated": False,
        "acsp_decision_regenerated": False,
        "heldout_outcome_regenerated": False,
        "scientific_protocol_changed": False,
    }
    _write_json(destination / "pair_manifest.json", recovered_pair_manifest)

    # Full strict verification must still succeed on the recovered artifact.
    _read_pair_artifact(destination, core_fp, confirmation_fp, expected_repeats)
    recovery_manifest = {
        "pair_id": int(pair.pair_id),
        "status": "grts_recovery_complete",
        "source_run_id": SOURCE_RUN_ID,
        "source_head_sha": SOURCE_HEAD_SHA,
        "practical_core_fingerprint": core_fp,
        "confirmation_protocol_fingerprint": confirmation_fp,
        "recovered_folds": int(recovered_folds),
        "preserved_small_candidate_pool_folds": int(preserved_small_pool_folds),
        "gbif_refetched": False,
        "candidate_pool_regenerated": False,
        "outer_split_regenerated": False,
        "acsp_decision_regenerated": False,
        "heldout_outcome_regenerated": False,
        "non_grts_results_changed": False,
        "scientific_protocol_changed": False,
    }
    _write_json(destination / "grts_recovery_manifest.json", recovery_manifest)
    return recovery_manifest


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--pair-id", type=int, required=True)
    command.add_argument("--source-root", type=Path, required=True)
    command.add_argument("--cohort", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    return command


if __name__ == "__main__":
    print(json.dumps(run(parser().parse_args()), indent=2, ensure_ascii=False))
