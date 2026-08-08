#!/usr/bin/env python3
"""Fold-resilient orchestration for one untouched fitted-SDM Top-k pair."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import run_sdm_topk_pair as core
from benchmark_general_random_taxa_regions import fetch_occurrences


def _fold_failure_rows(pair: pd.Series, repeat: int, heldout_records: int, reason: str) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "pair_id": int(pair.pair_id),
            "repeat": int(repeat),
            "taxon_group": str(pair.taxon_group),
            "scientific_name": str(pair.scientific_name),
            "region_name": str(pair.region_name),
            "decision_method": method,
            "method_status": "fold_execution_failure",
            "heldout_recall": 0.0,
            "heldout_records": int(heldout_records),
            "candidate_pool": 0,
            "sdm_fold_ok": False,
            "selected_ids": "",
            "failure_reason": reason,
        }
        for method in core.METHODS
    ])


def run(args: argparse.Namespace) -> dict[str, Any]:
    protocol_fp = core._canonical_fingerprint(core.PROTOCOL_PATH, "protocol_fingerprint")
    contract_fp = core._canonical_fingerprint(core.CONTRACT_PATH, "contract_fingerprint")
    if protocol_fp != core.EXPECTED_PROTOCOL or contract_fp != core.EXPECTED_CONTRACT:
        raise ValueError("frozen protocol/contract fingerprint differs from executor constants")
    protocol = json.loads(core.PROTOCOL_PATH.read_text(encoding="utf-8"))
    cohort = pd.read_csv(core.COHORT_PATH)
    selected = cohort[cohort["pair_id"].astype(int).eq(int(args.pair_id))]
    if len(selected) != 1:
        raise ValueError(f"pair_id {args.pair_id} is not uniquely present in frozen cohort")
    pair = selected.iloc[0]
    root = Path(args.output) / f"pair_{int(pair.pair_id):03d}"
    root.mkdir(parents=True, exist_ok=True)
    manifests: list[dict[str, Any]] = []
    repeats = int(protocol["outer_validation"]["repeats"])

    try:
        occurrences = fetch_occurrences(pair, int(protocol["cohort"]["records_per_pair"]))
        latitude_col, longitude_col = core._coord_columns(occurrences)
        work = occurrences.copy().reset_index(drop=True)
        work[latitude_col] = pd.to_numeric(work[latitude_col], errors="coerce")
        work[longitude_col] = pd.to_numeric(work[longitude_col], errors="coerce")
        work = work.dropna(subset=[latitude_col, longitude_col]).reset_index(drop=True)
        if len(work) < 4:
            raise ValueError("fewer than four valid occurrence coordinates")
        work["_outer_occurrence_id"] = [
            f"pair{int(pair.pair_id):03d}-occurrence{index + 1:05d}" for index in range(len(work))
        ]
        block = float(protocol["outer_validation"]["block_degrees"])
        work["_outer_block"] = (
            np.floor(work[latitude_col] / block).astype(int).astype(str)
            + ":" + np.floor(work[longitude_col] / block).astype(int).astype(str)
        )
        blocks = work["_outer_block"].drop_duplicates().to_numpy()
        if len(blocks) < 2:
            raise ValueError("occurrences occupy fewer than two outer spatial blocks")
        rng = np.random.default_rng(int(protocol["outer_validation"]["fold_seed_base"]) + int(pair.pair_id))
        n_holdout = min(
            len(blocks) - 1,
            max(1, int(round(len(blocks) * float(protocol["outer_validation"]["holdout_fraction"])))),
        )
        all_results: list[pd.DataFrame] = []
        for repeat in range(1, repeats + 1):
            held_blocks = set(rng.choice(blocks, size=n_holdout, replace=False).tolist())
            heldout = work[work["_outer_block"].isin(held_blocks)].copy().reset_index(drop=True)
            training = work[~work["_outer_block"].isin(held_blocks)].drop(
                columns=["_outer_block", "_outer_occurrence_id"]
            ).copy().reset_index(drop=True)
            try:
                candidates, decisions, state = core.build_operational_decisions(
                    training, pair, repeat, protocol=protocol
                )
                result, oracle_ids = core.attach_outcomes(
                    candidates,
                    heldout,
                    decisions,
                    state,
                    pair,
                    repeat,
                    radius_km=float(protocol["outer_validation"]["recovery_radius_km"]),
                )
            except Exception as exc:
                reason = f"{type(exc).__name__}: {exc}"
                candidates = pd.DataFrame(columns=["candidate_id", "latitude", "longitude", "sdm_suitability"])
                decisions = {
                    "pair_id": int(pair.pair_id),
                    "repeat": int(repeat),
                    "outcomes_available_to_operational_selectors": False,
                    "methods": {},
                    "random_same_pool_draws": [],
                    "fold_execution_failure": reason,
                }
                state = {
                    "method_status": {method: "fold_execution_failure" for method in core.METHODS},
                    "sdm_audit": {"status": "not_run_due_to_fold_failure", "error": reason},
                }
                result = _fold_failure_rows(pair, repeat, len(heldout), reason)
                oracle_ids = []
            all_results.append(result)
            manifests.append(core._write_fold(
                root / f"fold_{repeat:03d}",
                training,
                heldout,
                candidates,
                decisions,
                state,
                result,
                oracle_ids,
                pair=pair,
                repeat=repeat,
                held_blocks=held_blocks,
                protocol_fp=protocol_fp,
                contract_fp=contract_fp,
            ))
        fold_results = pd.concat(all_results, ignore_index=True)
        pair_status = "complete" if all(
            manifest.get("method_status", {}).get("frozen_acsp") != "fold_execution_failure"
            for manifest in manifests
        ) else "complete_with_fold_failures"
        pair_error = ""
    except Exception as exc:
        fold_results = core._failure_rows(pair, repeats, f"{type(exc).__name__}: {exc}")
        pair_status = "pair_setup_failure"
        pair_error = f"{type(exc).__name__}: {exc}"

    fold_results.to_csv(root / "fold_results.csv", index=False)
    pair_manifest = {
        "pair_id": int(pair.pair_id),
        "scientific_name": str(pair.scientific_name),
        "taxon_group": str(pair.taxon_group),
        "region_name": str(pair.region_name),
        "pair_status": pair_status,
        "pair_error": pair_error,
        "protocol_fingerprint": protocol_fp,
        "execution_contract_fingerprint": contract_fp,
        "expected_repeats": repeats,
        "written_fold_manifests": len(manifests),
        "sdm_ok_folds": int(
            fold_results.loc[
                fold_results["decision_method"].eq("fitted_sdm_top_k"), "method_status"
            ].eq("ok").sum()
        ),
        "fold_execution_failures": int(
            fold_results.loc[
                fold_results["decision_method"].eq("frozen_acsp"), "method_status"
            ].eq("fold_execution_failure").sum()
        ),
        "fold_result_sha256": core._sha256(root / "fold_results.csv"),
    }
    (root / "pair_manifest.json").write_text(
        json.dumps(pair_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return pair_manifest


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--pair-id", type=int, required=True)
    command.add_argument("--output", default="sdm_topk_pair_results")
    return command


if __name__ == "__main__":
    print(json.dumps(run(parser().parse_args()), indent=2, ensure_ascii=False))
