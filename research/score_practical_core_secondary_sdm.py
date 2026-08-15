#!/usr/bin/env python3
"""Attach the frozen production-aligned fitted-SDM decision as a secondary analysis.

This scorer never regenerates the candidate pool and never changes the primary
Practical Core-vs-GRTS result. For each already-frozen primary fold it reads only
training occurrences, the candidate pool, and the Practical Core decision,
freezes the fitted-SDM Top-5 decision, and only then opens the held-out occurrence
file to calculate recovery. Outputs are written to a separate secondary tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from acsp.automatic_sdm import select_sdm_top_k
import run_sdm_topk_pair as legacy_sdm
from run_practical_core_confirmation_pair import _coverage_sets, _recall


PROTOCOL_PATH = Path("validation/acsp_practical_core_secondary_sdm_protocol.json")
CORE_PROTOCOL_PATH = Path("validation/acsp_practical_core_protocol.json")
PRIMARY_PROTOCOL_PATH = Path(
    "validation/acsp_practical_core_untouched_confirmation_protocol.json"
)
EXECUTION_CONTRACT_PATH = Path("validation/sdm_topk_execution_contract.json")
EXPECTED_PROTOCOL = "50fac79ce26378a56aaf497564ce85574986580096275c4d26de67170e6f3d63"
EXPECTED_CORE = "3dafe65b6bef09b1878d688730d5feb64a8de58843b06ff9fb14a876512d4905"
EXPECTED_PRIMARY = "cd27dc5416057b574e58742bfe001307338a20aedb63ce1bac431588dc58eee9"
EXPECTED_SDM_CONTRACT = "1627009619716726e4af2e1ac7dc5ce47fa50dcfefa3bb042364c84b00884bd1"
FORBIDDEN_CANDIDATE_COLUMNS = {
    "_outer_occurrence_id",
    "_outer_block",
    "covered_heldout_ids",
    "heldout_distances_km",
    "all_heldout_ids",
    "heldout_recall",
}


def _canonical(path: Path, field: str, expected: str) -> tuple[dict[str, Any], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    stored = str(payload.pop(field, ""))
    actual = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if stored != actual or actual != expected:
        raise ValueError(
            f"fingerprint mismatch for {path}: stored={stored!r}, "
            f"actual={actual!r}, expected={expected!r}"
        )
    payload[field] = stored
    return payload, actual


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_ids(frame: pd.DataFrame) -> list[str]:
    if frame is None or frame.empty or "candidate_id" not in frame.columns:
        return []
    return frame["candidate_id"].astype(str).tolist()


def _jaccard(first: list[str], second: list[str]) -> float:
    a, b = set(map(str, first)), set(map(str, second))
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _verify_primary_preoutcome_inputs(
    primary_fold: Path,
    core_fp: str,
    primary_fp: str,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, Any]]:
    manifest_path = primary_fold / "fold_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"primary fold manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("practical_core_fingerprint") != core_fp:
        raise ValueError(f"primary Practical Core fingerprint mismatch: {manifest_path}")
    if manifest.get("confirmation_protocol_fingerprint") != primary_fp:
        raise ValueError(f"primary confirmation fingerprint mismatch: {manifest_path}")
    if manifest.get("outcomes_available_to_operational_selectors") is not False:
        raise ValueError(f"primary leakage flag failed: {manifest_path}")
    if manifest.get("pre_outcome_files_written_once") is not True:
        raise ValueError(f"primary pre-outcome write audit failed: {manifest_path}")

    files = manifest.get("files", {})
    needed = {
        "training_occurrences": primary_fold / "training_occurrences.csv",
        "candidate_pool_pre_outcome": primary_fold / "candidate_pool_pre_outcome.csv",
        "deterministic_decisions_pre_outcome": primary_fold
        / "deterministic_decisions_pre_outcome.json",
    }
    for name, path in needed.items():
        record = files.get(name)
        if not record:
            raise ValueError(f"primary manifest lacks {name}: {manifest_path}")
        if path.name != str(record.get("path")) or _sha256(path) != str(
            record.get("sha256")
        ):
            raise ValueError(f"primary pre-outcome hash mismatch: {path}")

    training = pd.read_csv(needed["training_occurrences"])
    candidates = pd.read_csv(needed["candidate_pool_pre_outcome"])
    forbidden = FORBIDDEN_CANDIDATE_COLUMNS & set(candidates.columns)
    if forbidden:
        raise ValueError(
            f"primary candidate artifact contains forbidden outcome columns: {sorted(forbidden)}"
        )
    decisions = json.loads(
        needed["deterministic_decisions_pre_outcome"].read_text(encoding="utf-8")
    )
    if decisions.get("outcomes_available_to_selectors") is not False:
        raise ValueError("primary deterministic-decision leakage flag failed")
    return training, candidates, decisions, manifest


def _freeze_sdm_decision(
    training: pd.DataFrame,
    candidates: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str], dict[str, Any], str]:
    if len(candidates) < 5:
        audit = {
            "status": "sdm_failure",
            "error_type": "SharedCandidateFailure",
            "error_message": "fewer than five frozen shared candidate rows",
            "finite_candidate_scores": 0,
        }
        scored = candidates.copy()
        scored["sdm_suitability"] = np.nan
        return scored, [], audit, "sdm_failure"
    try:
        scored, audit = legacy_sdm._fit_and_score_production_sdm(
            training.copy(), candidates.copy()
        )
        finite = scored[
            pd.to_numeric(scored["sdm_suitability"], errors="coerce").notna()
        ].copy()
        selected = select_sdm_top_k(finite, 5, id_col="candidate_id")
        return scored, _stable_ids(selected), audit, "sdm_ok"
    except Exception as exc:
        scored = candidates.copy()
        if "sdm_suitability" not in scored.columns:
            scored["sdm_suitability"] = np.nan
        audit = {
            "status": "sdm_failure",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "finite_candidate_scores": int(
                pd.to_numeric(scored["sdm_suitability"], errors="coerce")
                .notna()
                .sum()
            ),
        }
        return scored, [], audit, "sdm_failure"


def score_fold(
    primary_fold: Path,
    secondary_fold: Path,
    *,
    core_fp: str,
    primary_fp: str,
    secondary_fp: str,
) -> dict[str, Any]:
    training, candidates, primary_decisions, primary_manifest = (
        _verify_primary_preoutcome_inputs(primary_fold, core_fp, primary_fp)
    )
    secondary_fold.mkdir(parents=True, exist_ok=True)

    scored, sdm_ids, sdm_audit, sdm_status = _freeze_sdm_decision(
        training, candidates
    )
    practical_ids = list(
        primary_decisions.get("methods", {}).get("acsp_practical_core", [])
    )

    # Freeze all SDM-bearing artifacts before the held-out file is opened.
    scored_path = secondary_fold / "sdm_scored_candidates_pre_outcome.csv"
    decision_path = secondary_fold / "sdm_decision_pre_outcome.json"
    audit_path = secondary_fold / "sdm_audit_pre_outcome.json"
    scored.to_csv(scored_path, index=False)
    decision = {
        "status": sdm_status,
        "selected_candidate_ids": sdm_ids,
        "practical_core_candidate_ids": practical_ids,
        "top_k": 5,
        "outcomes_available_to_sdm_selector": False,
        "candidate_pool_sha256": _sha256(primary_fold / "candidate_pool_pre_outcome.csv"),
        "training_occurrences_sha256": _sha256(primary_fold / "training_occurrences.csv"),
    }
    decision_path.write_text(
        json.dumps(decision, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    audit_path.write_text(
        json.dumps(sdm_audit, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    preoutcome_hashes = {
        "sdm_scored_candidates_pre_outcome": _sha256(scored_path),
        "sdm_decision_pre_outcome": _sha256(decision_path),
        "sdm_audit_pre_outcome": _sha256(audit_path),
    }

    # Only now read held-out coordinates from the already verified primary fold.
    heldout_path = primary_fold / "held_out_occurrences.csv"
    heldout_record = primary_manifest.get("files", {}).get("held_out_occurrences")
    if not heldout_record or _sha256(heldout_path) != str(heldout_record.get("sha256")):
        raise ValueError(f"primary held-out artifact hash mismatch: {heldout_path}")
    heldout = pd.read_csv(heldout_path)
    coverage, all_ids = _coverage_sets(candidates, heldout, 10.0)
    sdm_recall = _recall(sdm_ids, coverage, all_ids) if sdm_status == "sdm_ok" else 0.0
    practical_recall = _recall(practical_ids, coverage, all_ids)
    overlap = _jaccard(sdm_ids, practical_ids) if sdm_status == "sdm_ok" else np.nan
    exact = bool(set(sdm_ids) == set(practical_ids)) if sdm_status == "sdm_ok" else False

    result = {
        "pair_id": int(primary_manifest["pair_id"]),
        "repeat": int(primary_manifest["repeat"]),
        "scientific_name": str(primary_manifest["scientific_name"]),
        "taxon_group": str(primary_manifest["taxon_group"]),
        "sdm_status": sdm_status,
        "heldout_records": int(len(all_ids)),
        "candidate_pool": int(len(candidates)),
        "practical_core_recall": float(practical_recall),
        "fitted_sdm_top_k_recall": float(sdm_recall),
        "practical_minus_sdm_recall": float(practical_recall - sdm_recall),
        "top5_jaccard": None if not np.isfinite(overlap) else float(overlap),
        "exact_set_agreement": exact,
        "practical_core_selected_ids": ";".join(practical_ids),
        "fitted_sdm_selected_ids": ";".join(sdm_ids),
    }
    result_path = secondary_fold / "sdm_fold_result.csv"
    pd.DataFrame([result]).to_csv(result_path, index=False)

    # Prove the SDM decision files were not rewritten after outcome attachment.
    after_hashes = {
        "sdm_scored_candidates_pre_outcome": _sha256(scored_path),
        "sdm_decision_pre_outcome": _sha256(decision_path),
        "sdm_audit_pre_outcome": _sha256(audit_path),
    }
    if preoutcome_hashes != after_hashes:
        raise AssertionError("secondary SDM pre-outcome artifact changed after scoring")

    manifest = {
        "pair_id": int(primary_manifest["pair_id"]),
        "repeat": int(primary_manifest["repeat"]),
        "secondary_sdm_protocol_fingerprint": secondary_fp,
        "practical_core_fingerprint": core_fp,
        "primary_confirmation_protocol_fingerprint": primary_fp,
        "source_primary_fold_manifest_sha256": _sha256(
            primary_fold / "fold_manifest.json"
        ),
        "sdm_status": sdm_status,
        "outcomes_available_to_sdm_selector": False,
        "preoutcome_files_not_rewritten_after_scoring": True,
        "preoutcome_sha256": preoutcome_hashes,
        "result_path": result_path.name,
        "result_sha256": _sha256(result_path),
    }
    (secondary_fold / "secondary_sdm_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def run(args: argparse.Namespace) -> dict[str, Any]:
    protocol, secondary_fp = _canonical(PROTOCOL_PATH, "fingerprint", EXPECTED_PROTOCOL)
    _, core_fp = _canonical(CORE_PROTOCOL_PATH, "fingerprint", EXPECTED_CORE)
    _, primary_fp = _canonical(
        PRIMARY_PROTOCOL_PATH, "protocol_fingerprint", EXPECTED_PRIMARY
    )
    _, contract_fp = _canonical(
        EXECUTION_CONTRACT_PATH, "contract_fingerprint", EXPECTED_SDM_CONTRACT
    )
    if protocol["practical_core_fingerprint"] != core_fp:
        raise ValueError("secondary SDM protocol points to different Practical Core")
    if protocol["primary_confirmation_protocol_fingerprint"] != primary_fp:
        raise ValueError("secondary SDM protocol points to different primary protocol")
    source = protocol["source_sdm_execution_contract"]
    if source["contract_fingerprint"] != contract_fp:
        raise ValueError("secondary SDM protocol points to different SDM execution contract")

    primary_pair = Path(args.primary_pair_root) / f"pair_{int(args.pair_id):03d}"
    if not primary_pair.exists():
        raise FileNotFoundError(f"primary pair artifact missing: {primary_pair}")
    secondary_pair = Path(args.output) / f"pair_{int(args.pair_id):03d}"
    secondary_pair.mkdir(parents=True, exist_ok=True)
    manifests = []
    for repeat in range(1, 6):
        primary_fold = primary_pair / f"fold_{repeat:03d}"
        if not primary_fold.exists():
            # Missing primary fold is not converted into a fitted model. It is
            # retained as an explicit secondary failure row.
            fold_dir = secondary_pair / f"fold_{repeat:03d}"
            fold_dir.mkdir(parents=True, exist_ok=True)
            result = pd.DataFrame([{
                "pair_id": int(args.pair_id),
                "repeat": repeat,
                "sdm_status": "primary_fold_missing",
                "practical_core_recall": np.nan,
                "fitted_sdm_top_k_recall": 0.0,
                "practical_minus_sdm_recall": np.nan,
                "top5_jaccard": np.nan,
                "exact_set_agreement": False,
            }])
            result_path = fold_dir / "sdm_fold_result.csv"
            result.to_csv(result_path, index=False)
            marker = {
                "pair_id": int(args.pair_id),
                "repeat": repeat,
                "secondary_sdm_protocol_fingerprint": secondary_fp,
                "sdm_status": "primary_fold_missing",
                "outcomes_available_to_sdm_selector": False,
                "result_sha256": _sha256(result_path),
            }
            (fold_dir / "secondary_sdm_manifest.json").write_text(
                json.dumps(marker, indent=2) + "\n", encoding="utf-8"
            )
            manifests.append(marker)
            continue
        manifests.append(
            score_fold(
                primary_fold,
                secondary_pair / f"fold_{repeat:03d}",
                core_fp=core_fp,
                primary_fp=primary_fp,
                secondary_fp=secondary_fp,
            )
        )

    rows = []
    for repeat in range(1, 6):
        path = secondary_pair / f"fold_{repeat:03d}" / "sdm_fold_result.csv"
        if path.exists():
            rows.append(pd.read_csv(path))
    fold_results = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    fold_results.to_csv(secondary_pair / "secondary_sdm_fold_results.csv", index=False)
    pair_manifest = {
        "pair_id": int(args.pair_id),
        "secondary_sdm_protocol_fingerprint": secondary_fp,
        "source_sdm_execution_contract_fingerprint": contract_fp,
        "expected_repeats": 5,
        "written_fold_manifests": int(len(manifests)),
        "sdm_ok_folds": int(
            fold_results.get("sdm_status", pd.Series(dtype=str)).astype(str).eq("sdm_ok").sum()
        ),
        "primary_result_unchanged": True,
        "superiority_gate": None,
        "fold_results_sha256": _sha256(
            secondary_pair / "secondary_sdm_fold_results.csv"
        ),
    }
    (secondary_pair / "secondary_sdm_pair_manifest.json").write_text(
        json.dumps(pair_manifest, indent=2) + "\n", encoding="utf-8"
    )
    return pair_manifest


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--pair-id", type=int, required=True)
    command.add_argument("--primary-pair-root", type=Path, required=True)
    command.add_argument(
        "--output", type=Path, default=Path("practical_core_secondary_sdm")
    )
    return command


if __name__ == "__main__":
    args = parser().parse_args()
    print(json.dumps(run(args), indent=2, ensure_ascii=False))
