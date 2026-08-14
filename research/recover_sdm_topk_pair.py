#!/usr/bin/env python3
"""Recover fitted-SDM decisions from frozen untouched pair artifacts.

The original run fitted/scored SDMs but failed at the final candidate merge because
`potential_candidates` already contained an all-missing `sdm_suitability` placeholder.
This recovery reuses the exact frozen training, held-out, and shared candidate tables,
drops only that empty placeholder before calling the unchanged production SDM helper,
and updates only the fitted-SDM decision/result fields.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import run_sdm_topk_pair as core
from acsp.automatic_sdm import select_sdm_top_k
from reaggregate_sdm_topk_benchmark import verify_pair_strict

SOURCE_RUN_ID = 31236963484
BUG_ID = "empty_sdm_suitability_placeholder_merge_collision"


def prepare_sdm_scoring_input(candidates: pd.DataFrame) -> pd.DataFrame:
    """Remove only the known empty production placeholder before SDM scoring."""
    out = candidates.copy()
    if "sdm_suitability" in out.columns:
        existing = pd.to_numeric(out["sdm_suitability"], errors="coerce")
        if existing.notna().any():
            raise ValueError("source candidate artifact already contains non-missing SDM suitability")
        out = out.drop(columns="sdm_suitability")
    return out


def is_empty_shared_candidate_fold(
    candidates: pd.DataFrame,
    fold_result: pd.DataFrame,
) -> bool:
    """Identify a pre-existing shared-candidate failure without inventing candidates.

    Empty candidate folds are part of the frozen intention-to-evaluate benchmark. They
    must remain failures for every method rather than being repaired by regenerating a
    candidate pool solely to make the fitted-SDM comparator evaluable.
    """
    if not candidates.empty:
        return False
    if "candidate_pool" in fold_result.columns:
        pool_sizes = pd.to_numeric(fold_result["candidate_pool"], errors="coerce").fillna(0)
        if pool_sizes.ne(0).any():
            raise ValueError("empty candidate artifact conflicts with non-zero candidate_pool result")
    return True


def update_sdm_fold_result(
    fold_result: pd.DataFrame,
    *,
    status: str,
    recall: float,
    selected_ids: list[str],
) -> pd.DataFrame:
    """Update fitted-SDM fields while preserving every other method's recall."""
    out = fold_result.copy()
    mask = out["decision_method"].astype(str).eq("fitted_sdm_top_k")
    if int(mask.sum()) != 1:
        raise ValueError("fold result must contain exactly one fitted_sdm_top_k row")
    original_other = out.loc[~mask, ["decision_method", "heldout_recall"]].copy().reset_index(drop=True)

    # CSV round-trips can infer an all-empty selected_ids column as float64. Explicitly
    # restore string/object semantics so a genuine SDM failure can be serialized as an
    # empty selection rather than crashing the recovery job under newer pandas versions.
    if "selected_ids" not in out.columns:
        out["selected_ids"] = pd.Series("", index=out.index, dtype="string")
    else:
        out["selected_ids"] = out["selected_ids"].astype("string")
    out["method_status"] = out["method_status"].astype("string")

    out.loc[mask, "method_status"] = status
    out.loc[mask, "heldout_recall"] = float(recall)
    out.loc[mask, "selected_ids"] = ";".join(map(str, selected_ids))
    out["sdm_fold_ok"] = bool(status == "ok")
    after_other = out.loc[~mask, ["decision_method", "heldout_recall"]].copy().reset_index(drop=True)
    pd.testing.assert_frame_equal(original_other, after_other, check_dtype=False)
    return out


def recover_pair(source_pair: Path, output_pair: Path) -> dict[str, Any]:
    protocol_fp = core._canonical_fingerprint(core.PROTOCOL_PATH, "protocol_fingerprint")
    contract_fp = core._canonical_fingerprint(core.CONTRACT_PATH, "contract_fingerprint")
    source_manifest = verify_pair_strict(source_pair, protocol_fp, contract_fp)
    pair_id = int(source_manifest["pair_id"])
    output_pair.mkdir(parents=True, exist_ok=True)
    recovered_folds = []

    for fold_dir in sorted(path for path in source_pair.glob("fold_[0-9][0-9][0-9]") if path.is_dir()):
        repeat = int(fold_dir.name.split("_")[1])
        training = pd.read_csv(fold_dir / "training_occurrences.csv")
        heldout = pd.read_csv(fold_dir / "held_out_occurrences.csv")
        candidates = pd.read_csv(fold_dir / "candidate_pool_pre_outcome.csv")
        decisions = json.loads((fold_dir / "decision_sets.json").read_text(encoding="utf-8"))
        fold_result = pd.read_csv(fold_dir / "fold_result.csv")

        recovery_audit: dict[str, Any] = {
            "recovery_status": "started",
            "source_run_id": SOURCE_RUN_ID,
            "source_pair_id": pair_id,
            "repeat": repeat,
            "bug_id": BUG_ID,
            "source_candidate_rows": int(len(candidates)),
            "source_sdm_placeholder_present": "sdm_suitability" in candidates.columns,
            "scientific_method_changed": False,
            "gbif_refetched": False,
            "outer_split_regenerated": False,
            "candidate_pool_regenerated": False,
        }

        selected_ids: list[str] = []
        if is_empty_shared_candidate_fold(candidates, fold_result):
            # The original frozen benchmark had no common candidate pool in this fold.
            # Preserve the original all-method failure exactly; do not synthesize a pool
            # merely to make the SDM comparator run.
            candidates_out = candidates
            recovery_audit.update({
                "recovery_status": "preserved_shared_candidate_failure",
                "reason": "source shared candidate pool is empty",
                "selected_ids": [],
            })
        else:
            try:
                scoring_input = prepare_sdm_scoring_input(candidates)
                scored, sdm_audit = core._fit_and_score_production_sdm(training, scoring_input)
                finite = scored[pd.to_numeric(scored["sdm_suitability"], errors="coerce").notna()].copy()
                selected = select_sdm_top_k(finite, 5, id_col="candidate_id")
                selected_ids = selected["candidate_id"].astype(str).tolist()
                coverage, all_ids = core._coverage_sets(
                    scored,
                    heldout,
                    radius_km=float(json.loads(core.PROTOCOL_PATH.read_text())["outer_validation"]["recovery_radius_km"]),
                )
                recall = core._recall(selected_ids, coverage, all_ids)
                fold_result = update_sdm_fold_result(
                    fold_result, status="ok", recall=recall, selected_ids=selected_ids
                )
                decisions.setdefault("methods", {})["fitted_sdm_top_k"] = selected_ids
                candidates_out = scored
                recovery_audit.update({
                    "recovery_status": "sdm_ok",
                    "selected_ids": selected_ids,
                    "heldout_recall": float(recall),
                    "production_sdm_audit": sdm_audit,
                })
            except Exception as exc:
                fold_result = update_sdm_fold_result(
                    fold_result, status="sdm_failure_after_recovery", recall=0.0, selected_ids=[]
                )
                decisions.setdefault("methods", {})["fitted_sdm_top_k"] = []
                candidates_out = candidates
                recovery_audit.update({
                    "recovery_status": "sdm_failure_after_recovery",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                })

        out_fold = output_pair / fold_dir.name
        state = {
            "method_status": {
                str(row.decision_method): str(row.method_status)
                for row in fold_result.itertuples(index=False)
            },
            "sdm_audit": recovery_audit,
        }
        oracle_row = fold_result[fold_result["decision_method"].eq("heldout_greedy_oracle")]
        oracle_ids = [] if oracle_row.empty else [
            item for item in str(oracle_row.iloc[0].get("selected_ids", "")).split(";") if item and item != "nan"
        ]
        held_blocks = set(json.loads((fold_dir / "fold_manifest.json").read_text())["heldout_blocks"])
        core._write_fold(
            out_fold,
            training,
            heldout,
            candidates_out,
            decisions,
            state,
            fold_result,
            oracle_ids,
            pair=pd.Series({
                "pair_id": pair_id,
                "scientific_name": source_manifest["scientific_name"],
                "taxon_group": source_manifest["taxon_group"],
            }),
            repeat=repeat,
            held_blocks=held_blocks,
            protocol_fp=protocol_fp,
            contract_fp=contract_fp,
        )
        recovered_folds.append(fold_result)

    all_results = pd.concat(recovered_folds, ignore_index=True)
    all_results.to_csv(output_pair / "fold_results.csv", index=False)
    pair_manifest = {
        "pair_id": pair_id,
        "scientific_name": source_manifest["scientific_name"],
        "taxon_group": source_manifest["taxon_group"],
        "region_name": source_manifest["region_name"],
        "pair_status": "recovered_from_frozen_source_artifact",
        "pair_error": "",
        "protocol_fingerprint": protocol_fp,
        "execution_contract_fingerprint": contract_fp,
        "expected_repeats": int(source_manifest["expected_repeats"]),
        "written_fold_manifests": int(source_manifest["expected_repeats"]),
        "sdm_ok_folds": int(
            all_results.loc[all_results["decision_method"].eq("fitted_sdm_top_k"), "method_status"].eq("ok").sum()
        ),
        "source_run_id": SOURCE_RUN_ID,
        "source_pair_artifact_reused": True,
        "bug_id": BUG_ID,
        "scientific_method_changed": False,
        "fold_result_sha256": core._sha256(output_pair / "fold_results.csv"),
    }
    (output_pair / "pair_manifest.json").write_text(
        json.dumps(pair_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return pair_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair-id", type=int, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_pair = args.source_root / f"pair_{args.pair_id:03d}"
    output_pair = args.output / f"pair_{args.pair_id:03d}"
    print(json.dumps(recover_pair(source_pair, output_pair), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
