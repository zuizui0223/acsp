#!/usr/bin/env python3
"""Leakage-audited entry point for one Practical Core confirmation pair.

This executor reuses pure helper functions from run_practical_core_confirmation_pair
but owns the artifact write order. Pre-outcome files are written exactly once
before held-out recovery is calculated. Outcome-bearing files are written only
after all operational selections have been frozen.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from benchmark_general_random_taxa_regions import fetch_occurrences
from run_practical_core_confirmation_pair import (
    CONFIRMATION_PROTOCOL_PATH,
    CORE_PROTOCOL_PATH,
    DEFAULT_COHORT_PATH,
    EXPECTED_CONFIRMATION_PROTOCOL,
    EXPECTED_CORE_PROTOCOL,
    _canonical_fingerprint,
    _coord_columns,
    _failure_rows,
    _json_default,
    _sha256,
    build_candidate_pool,
    build_deterministic_decisions,
    run_grts_pre_outcome,
    score_frozen_decisions,
)

GRTS_PRE_OUTCOME_COLUMNS = [
    "pair_id",
    "repeat",
    "variant",
    "draw_index",
    "seed",
    "requested_k",
    "base_count",
    "base_ids",
    "requested_replacements",
    "replacement_count",
    "replacement_ids",
    "realized_min_distance_km",
    "warning_message",
    "error_message",
    "spsurvey_version",
    "outcomes_available_to_selector",
]


def _empty_grts_draws() -> pd.DataFrame:
    return pd.DataFrame(columns=GRTS_PRE_OUTCOME_COLUMNS)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=_json_default) + "\n",
        encoding="utf-8",
    )


def _write_pre_outcome_artifacts(
    fold_dir: Path,
    training: pd.DataFrame,
    candidates: pd.DataFrame,
    deterministic: dict[str, list[str]],
    deterministic_status: dict[str, str],
    random_sets: list[list[str]],
) -> dict[str, Path]:
    """Write all deterministic Python selection inputs/outputs before outcomes."""
    paths = {
        "training_occurrences": fold_dir / "training_occurrences.csv",
        "candidate_pool_pre_outcome": fold_dir / "candidate_pool_pre_outcome.csv",
        "deterministic_decisions_pre_outcome": fold_dir
        / "deterministic_decisions_pre_outcome.json",
    }
    training.to_csv(paths["training_occurrences"], index=False)
    candidates.to_csv(paths["candidate_pool_pre_outcome"], index=False)
    _write_json(
        paths["deterministic_decisions_pre_outcome"],
        {
            "methods": deterministic,
            "method_status": deterministic_status,
            "random_same_pool_draws": random_sets,
            "outcomes_available_to_selectors": False,
            "written_before_grts": True,
            "written_before_heldout_scoring": True,
        },
    )
    return paths


def _freeze_grts_artifacts(
    fold_dir: Path,
    candidates: pd.DataFrame,
    pair: pd.Series,
    repeat: int,
    confirmation: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Path]]:
    """Freeze official GRTS draws and process audit before held-out scoring."""
    draw_path = fold_dir / "grts_draws_pre_outcome.csv"
    audit_path = fold_dir / "grts_process_audit.json"
    if len(candidates) >= int(confirmation["practical_core"]["top_k"]):
        draws, audit = run_grts_pre_outcome(
            fold_dir / "candidate_pool_pre_outcome.csv",
            draw_path,
            pair,
            repeat,
            confirmation,
        )
        if not draw_path.exists():
            # Keep a parseable, schema-fixed pre-outcome artifact even when the
            # external R process fails before writing any draws.
            draws = _empty_grts_draws()
            draws.to_csv(draw_path, index=False)
    else:
        draws = _empty_grts_draws()
        draws.to_csv(draw_path, index=False)
        audit = {
            "status": "shared_candidate_failure",
            "returncode": None,
            "stdout_tail": "",
            "stderr_tail": "",
            "outcomes_available_to_selector": False,
        }
    audit = {
        **audit,
        "written_before_heldout_scoring": True,
        "candidate_pool_sha256": _sha256(fold_dir / "candidate_pool_pre_outcome.csv"),
    }
    _write_json(audit_path, audit)
    return draws, audit, {
        "grts_draws_pre_outcome": draw_path,
        "grts_process_audit": audit_path,
    }


def _finalize_fold(
    fold_dir: Path,
    pre_paths: dict[str, Path],
    grts_paths: dict[str, Path],
    heldout: pd.DataFrame,
    fold_results: pd.DataFrame,
    grts_scored: pd.DataFrame,
    oracle_ids: list[str],
    pair: pd.Series,
    repeat: int,
    held_blocks: set[str],
    core_fp: str,
    confirmation_fp: str,
    training_records: int,
    candidate_pool: int,
) -> dict[str, Any]:
    """Write outcome-bearing artifacts after selections; never rewrite pre-outcome files."""
    outcome_paths = {
        "held_out_occurrences": fold_dir / "held_out_occurrences.csv",
        "fold_result": fold_dir / "fold_result.csv",
        "grts_draws_scored": fold_dir / "grts_draws_scored.csv",
    }
    heldout.to_csv(outcome_paths["held_out_occurrences"], index=False)
    fold_results.to_csv(outcome_paths["fold_result"], index=False)
    grts_scored.to_csv(outcome_paths["grts_draws_scored"], index=False)

    files = {**pre_paths, **grts_paths, **outcome_paths}
    manifest = {
        "pair_id": int(pair.pair_id),
        "repeat": int(repeat),
        "scientific_name": str(pair.scientific_name),
        "taxon_group": str(pair.taxon_group),
        "heldout_blocks": sorted(held_blocks),
        "training_records": int(training_records),
        "heldout_records": int(len(heldout)),
        "candidate_pool": int(candidate_pool),
        "practical_core_fingerprint": core_fp,
        "confirmation_protocol_fingerprint": confirmation_fp,
        "outcomes_available_to_operational_selectors": False,
        "pre_outcome_files_written_once": True,
        "pre_outcome_files_not_rewritten_after_scoring": True,
        "oracle_selected_after_outcome_attachment": oracle_ids,
        "files": {
            name: {"path": path.name, "sha256": _sha256(path)}
            for name, path in files.items()
        },
    }
    _write_json(fold_dir / "fold_manifest.json", manifest)
    return manifest


def run(args: argparse.Namespace) -> dict[str, Any]:
    _, core_fp = _canonical_fingerprint(CORE_PROTOCOL_PATH, "fingerprint")
    confirmation, confirmation_fp = _canonical_fingerprint(
        CONFIRMATION_PROTOCOL_PATH, "protocol_fingerprint"
    )
    if core_fp != EXPECTED_CORE_PROTOCOL:
        raise ValueError("Practical Core fingerprint differs from executor constant")
    if confirmation_fp != EXPECTED_CONFIRMATION_PROTOCOL:
        raise ValueError("confirmation fingerprint differs from executor constant")
    if confirmation["practical_core"]["protocol_fingerprint"] != core_fp:
        raise ValueError("confirmation protocol does not point to frozen Practical Core")

    cohort = pd.read_csv(args.cohort)
    selected = cohort[pd.to_numeric(cohort["pair_id"], errors="coerce").eq(args.pair_id)]
    if len(selected) != 1:
        raise ValueError(f"pair_id {args.pair_id} is not uniquely present in cohort")
    pair = selected.iloc[0]

    root = Path(args.output) / f"pair_{int(pair.pair_id):03d}"
    root.mkdir(parents=True, exist_ok=True)
    manifests: list[dict[str, Any]] = []
    all_fold_results: list[pd.DataFrame] = []
    pair_status = "complete"
    pair_error = ""

    try:
        occurrences = fetch_occurrences(
            pair, int(confirmation["cohort"]["records_per_pair"])
        )
        latitude_col, longitude_col = _coord_columns(occurrences)
        work = occurrences.copy().reset_index(drop=True)
        work[latitude_col] = pd.to_numeric(work[latitude_col], errors="coerce")
        work[longitude_col] = pd.to_numeric(work[longitude_col], errors="coerce")
        work = work.dropna(subset=[latitude_col, longitude_col]).reset_index(drop=True)
        if len(work) < 4:
            raise ValueError("fewer than four valid occurrence coordinates")
        work["_outer_occurrence_id"] = [
            f"pair{int(pair.pair_id):03d}-occurrence{index + 1:05d}"
            for index in range(len(work))
        ]
        block = float(confirmation["outer_validation"]["block_degrees"])
        work["_outer_block"] = (
            np.floor(work[latitude_col] / block).astype(int).astype(str)
            + ":"
            + np.floor(work[longitude_col] / block).astype(int).astype(str)
        )
        blocks = work["_outer_block"].drop_duplicates().to_numpy()
        if len(blocks) < 2:
            raise ValueError("occurrences occupy fewer than two outer spatial blocks")

        rng = np.random.default_rng(
            int(confirmation["outer_validation"]["fold_seed_base"])
            + int(pair.pair_id)
        )
        n_holdout = min(
            len(blocks) - 1,
            max(
                1,
                int(
                    round(
                        len(blocks)
                        * float(confirmation["outer_validation"]["holdout_fraction"])
                    )
                ),
            ),
        )

        for repeat in range(
            1, int(confirmation["outer_validation"]["repeats"]) + 1
        ):
            fold_dir = root / f"fold_{repeat:03d}"
            fold_dir.mkdir(parents=True, exist_ok=True)
            held_blocks = set(
                rng.choice(blocks, size=n_holdout, replace=False).tolist()
            )
            heldout = work[work["_outer_block"].isin(held_blocks)].copy().reset_index(
                drop=True
            )
            training = (
                work[~work["_outer_block"].isin(held_blocks)]
                .drop(columns=["_outer_block", "_outer_occurrence_id"])
                .copy()
                .reset_index(drop=True)
            )

            candidates = build_candidate_pool(training, pair, repeat)
            deterministic, random_sets, deterministic_status = (
                build_deterministic_decisions(candidates, pair, repeat, confirmation)
            )

            # Phase A: write Python selections and candidate frame exactly once.
            pre_paths = _write_pre_outcome_artifacts(
                fold_dir,
                training,
                candidates,
                deterministic,
                deterministic_status,
                random_sets,
            )

            # Phase B: official GRTS reads only the frozen candidate CSV. Its
            # draws and process audit are also written before held-out scoring.
            grts_pre, _, grts_paths = _freeze_grts_artifacts(
                fold_dir, candidates, pair, repeat, confirmation
            )

            # Phase C: only now attach held-out outcomes to the frozen choices.
            fold_results, grts_scored, oracle_ids = score_frozen_decisions(
                candidates,
                heldout,
                deterministic,
                deterministic_status,
                random_sets,
                grts_pre,
                pair,
                repeat,
                confirmation,
            )
            all_fold_results.append(fold_results)
            manifests.append(
                _finalize_fold(
                    fold_dir,
                    pre_paths,
                    grts_paths,
                    heldout,
                    fold_results,
                    grts_scored,
                    oracle_ids,
                    pair,
                    repeat,
                    held_blocks,
                    core_fp,
                    confirmation_fp,
                    len(training),
                    len(candidates),
                )
            )
    except Exception as exc:
        pair_status = "pair_setup_failure"
        pair_error = f"{type(exc).__name__}: {exc}"
        all_fold_results = [
            _failure_rows(
                pair,
                int(confirmation["outer_validation"]["repeats"]),
                pair_error,
            )
        ]

    fold_results = pd.concat(all_fold_results, ignore_index=True)
    fold_results.to_csv(root / "fold_results.csv", index=False)
    pair_manifest = {
        "pair_id": int(pair.pair_id),
        "scientific_name": str(pair.scientific_name),
        "taxon_group": str(pair.taxon_group),
        "region_name": str(pair.region_name),
        "pair_status": pair_status,
        "pair_error": pair_error,
        "practical_core_fingerprint": core_fp,
        "confirmation_protocol_fingerprint": confirmation_fp,
        "expected_repeats": int(confirmation["outer_validation"]["repeats"]),
        "written_fold_manifests": len(manifests),
        "primary_stage_only": True,
        "fitted_sdm_deferred_to_secondary_stage": True,
        "pre_outcome_files_written_once": True,
        "fold_result_sha256": _sha256(root / "fold_results.csv"),
    }
    _write_json(root / "pair_manifest.json", pair_manifest)
    return pair_manifest


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--pair-id", type=int, required=True)
    command.add_argument("--cohort", type=Path, default=DEFAULT_COHORT_PATH)
    command.add_argument(
        "--output", type=Path, default=Path("practical_core_confirmation_pairs")
    )
    return command


if __name__ == "__main__":
    print(json.dumps(run(parser().parse_args()), indent=2, ensure_ascii=False))
