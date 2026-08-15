#!/usr/bin/env python3
"""Aggregate the frozen secondary fitted-SDM positioning analysis.

This analysis never changes the primary Practical Core-vs-GRTS gate. It reports
both an all-declared SDM estimand (SDM failures score zero) and a paired
evaluable-only estimand using only folds with status `sdm_ok`. Set overlap is
summarized only for evaluable folds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aggregate_practical_core_confirmation import paired_inference
from score_practical_core_secondary_sdm import (
    EXPECTED_CORE,
    EXPECTED_PRIMARY,
    EXPECTED_PROTOCOL,
    PROTOCOL_PATH,
    _canonical,
    _sha256,
)


CORE = "acsp_practical_core"
SDM = "fitted_sdm_top_k"
EXPECTED_REPEATS = 5


def _read_verified_secondary_fold(fold_dir: Path) -> pd.Series:
    manifest_path = fold_dir / "secondary_sdm_manifest.json"
    result_path = fold_dir / "sdm_fold_result.csv"
    if not manifest_path.exists() or not result_path.exists():
        raise FileNotFoundError(f"incomplete secondary SDM fold: {fold_dir}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("secondary_sdm_protocol_fingerprint") != EXPECTED_PROTOCOL:
        raise ValueError(f"secondary SDM fingerprint mismatch: {manifest_path}")
    if manifest.get("outcomes_available_to_sdm_selector") is not False:
        raise ValueError(f"secondary SDM leakage flag failed: {manifest_path}")
    if _sha256(result_path) != str(manifest.get("result_sha256")):
        raise ValueError(f"secondary SDM result hash mismatch: {result_path}")

    for name, digest in manifest.get("preoutcome_sha256", {}).items():
        path = fold_dir / {
            "sdm_scored_candidates_pre_outcome": "sdm_scored_candidates_pre_outcome.csv",
            "sdm_decision_pre_outcome": "sdm_decision_pre_outcome.json",
            "sdm_audit_pre_outcome": "sdm_audit_pre_outcome.json",
        }[name]
        if not path.exists() or _sha256(path) != str(digest):
            raise ValueError(f"secondary SDM pre-outcome hash mismatch: {path}")
    if manifest.get("preoutcome_sha256") and manifest.get(
        "preoutcome_files_not_rewritten_after_scoring"
    ) is not True:
        raise ValueError(f"secondary SDM write-order audit failed: {manifest_path}")

    frame = pd.read_csv(result_path)
    if len(frame) != 1:
        raise ValueError(f"secondary SDM fold result must contain one row: {result_path}")
    row = frame.iloc[0].copy()
    row["secondary_fold_verified"] = True
    return row


def _primary_core_pair_means(primary_aggregate: Path) -> pd.DataFrame:
    path = primary_aggregate / "pair_level_recall.csv"
    manifest_path = primary_aggregate / "confirmation_manifest.json"
    if not path.exists() or not manifest_path.exists():
        raise FileNotFoundError("primary aggregate outputs are incomplete")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("practical_core_fingerprint") != EXPECTED_CORE:
        raise ValueError("primary aggregate Practical Core fingerprint mismatch")
    if manifest.get("confirmation_protocol_fingerprint") != EXPECTED_PRIMARY:
        raise ValueError("primary aggregate confirmation fingerprint mismatch")
    frame = pd.read_csv(path)
    core = frame[frame["decision_method"].astype(str).eq(CORE)].copy()
    if core["pair_id"].astype(int).duplicated().any():
        raise ValueError("primary aggregate has duplicate Practical Core pair rows")
    return core[["pair_id", "pair_mean_recall"]].rename(
        columns={"pair_mean_recall": "practical_core_all_declared_recall"}
    )


def build_tables(
    cohort: pd.DataFrame,
    secondary_root: Path,
    primary_aggregate: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    core_pair = _primary_core_pair_means(primary_aggregate)
    cohort_ids = cohort[[
        "pair_id",
        "scientific_name",
        "taxon_group",
        "geographic_stratum",
        "region_name",
        "record_count_stratum",
    ]].copy()
    all_rows = []
    evaluable_rows = []
    fold_rows = []

    for _, pair in cohort_ids.sort_values("pair_id").iterrows():
        pair_id = int(pair.pair_id)
        pair_dir = secondary_root / f"pair_{pair_id:03d}"
        sdm_recalls = []
        ok_core = []
        ok_sdm = []
        ok_jaccard = []
        ok_exact = []
        verified_folds = 0
        sdm_ok_folds = 0
        for repeat in range(1, EXPECTED_REPEATS + 1):
            fold_dir = pair_dir / f"fold_{repeat:03d}"
            if not fold_dir.exists():
                sdm_recalls.append(0.0)
                fold_rows.append({
                    "pair_id": pair_id,
                    "repeat": repeat,
                    "sdm_status": "secondary_fold_missing",
                    "practical_core_recall": np.nan,
                    "fitted_sdm_top_k_recall": 0.0,
                    "top5_jaccard": np.nan,
                    "exact_set_agreement": False,
                    "secondary_fold_verified": False,
                })
                continue
            row = _read_verified_secondary_fold(fold_dir)
            verified_folds += 1
            status = str(row.get("sdm_status", "unknown"))
            sdm_recall = pd.to_numeric(
                pd.Series([row.get("fitted_sdm_top_k_recall")]), errors="coerce"
            ).iloc[0]
            sdm_recall = float(sdm_recall) if np.isfinite(sdm_recall) else 0.0
            sdm_recalls.append(sdm_recall)
            fold_rows.append(row.to_dict())
            if status == "sdm_ok":
                sdm_ok_folds += 1
                core_value = pd.to_numeric(
                    pd.Series([row.get("practical_core_recall")]), errors="coerce"
                ).iloc[0]
                if not np.isfinite(core_value):
                    raise ValueError(
                        f"sdm_ok fold lacks finite Practical Core recall: {fold_dir}"
                    )
                ok_core.append(float(core_value))
                ok_sdm.append(float(sdm_recall))
                jaccard = pd.to_numeric(
                    pd.Series([row.get("top5_jaccard")]), errors="coerce"
                ).iloc[0]
                if np.isfinite(jaccard):
                    ok_jaccard.append(float(jaccard))
                exact = str(row.get("exact_set_agreement", "False")).strip().lower()
                ok_exact.append(exact in {"true", "1"})

        all_rows.append({
            **pair.to_dict(),
            "fitted_sdm_all_declared_recall": float(np.mean(sdm_recalls)),
            "secondary_verified_folds": int(verified_folds),
            "sdm_ok_folds": int(sdm_ok_folds),
        })
        if sdm_ok_folds:
            evaluable_rows.append({
                **pair.to_dict(),
                "sdm_ok_folds": int(sdm_ok_folds),
                "practical_core_evaluable_recall": float(np.mean(ok_core)),
                "fitted_sdm_evaluable_recall": float(np.mean(ok_sdm)),
                "mean_top5_jaccard": float(np.mean(ok_jaccard)) if ok_jaccard else np.nan,
                "median_top5_jaccard": float(np.median(ok_jaccard)) if ok_jaccard else np.nan,
                "exact_set_agreement_rate": float(np.mean(ok_exact)) if ok_exact else np.nan,
            })

    all_declared = pd.DataFrame(all_rows).merge(
        core_pair, on="pair_id", how="left", validate="one_to_one"
    )
    if all_declared["practical_core_all_declared_recall"].isna().any():
        missing = all_declared.loc[
            all_declared["practical_core_all_declared_recall"].isna(), "pair_id"
        ].astype(int).tolist()
        raise ValueError(f"primary aggregate missing Practical Core pair means: {missing}")
    all_declared["practical_minus_sdm_all_declared"] = (
        all_declared["practical_core_all_declared_recall"]
        - all_declared["fitted_sdm_all_declared_recall"]
    )
    evaluable = pd.DataFrame(evaluable_rows)
    if not evaluable.empty:
        evaluable["practical_minus_sdm_evaluable"] = (
            evaluable["practical_core_evaluable_recall"]
            - evaluable["fitted_sdm_evaluable_recall"]
        )
    folds = pd.DataFrame(fold_rows)
    return all_declared, evaluable, folds


def _inference_frame(
    frame: pd.DataFrame,
    core_col: str,
    sdm_col: str,
    *,
    bootstrap_draws: int,
    sign_flip_draws: int,
    seed: int,
) -> dict[str, Any]:
    if frame.empty:
        return {
            "pairs": 0,
            "mean_difference": np.nan,
            "bootstrap_95ci_low": np.nan,
            "bootstrap_95ci_high": np.nan,
            "sign_flip_p": np.nan,
        }
    pair_level = pd.concat([
        frame[["pair_id", core_col]].rename(columns={core_col: "pair_mean_recall"}).assign(
            decision_method=CORE
        ),
        frame[["pair_id", sdm_col]].rename(columns={sdm_col: "pair_mean_recall"}).assign(
            decision_method=SDM
        ),
    ], ignore_index=True)
    return paired_inference(
        pair_level,
        CORE,
        SDM,
        bootstrap_draws=bootstrap_draws,
        sign_flip_draws=sign_flip_draws,
        seed=seed,
    )


def run(args: argparse.Namespace) -> dict[str, Any]:
    protocol, protocol_fp = _canonical(
        PROTOCOL_PATH, "fingerprint", EXPECTED_PROTOCOL
    )
    cohort = pd.read_csv(args.cohort)
    if len(cohort) != 192 or cohort["scientific_name"].astype(str).nunique() != 192:
        raise ValueError("secondary SDM cohort must be the frozen 192-pair cohort")
    all_declared, evaluable, folds = build_tables(
        cohort, Path(args.secondary_root), Path(args.primary_aggregate)
    )
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    all_declared.to_csv(output / "sdm_all_declared_pairs.csv", index=False)
    evaluable.to_csv(output / "sdm_evaluable_pairs.csv", index=False)
    folds.to_csv(output / "sdm_fold_results.csv", index=False)

    reporting = protocol["reporting"]
    all_inference = _inference_frame(
        all_declared,
        "practical_core_all_declared_recall",
        "fitted_sdm_all_declared_recall",
        bootstrap_draws=int(reporting["bootstrap_draws"]),
        sign_flip_draws=int(reporting["sign_flip_draws"]),
        seed=20260811,
    )
    evaluable_inference = _inference_frame(
        evaluable,
        "practical_core_evaluable_recall",
        "fitted_sdm_evaluable_recall",
        bootstrap_draws=int(reporting["bootstrap_draws"]),
        sign_flip_draws=int(reporting["sign_flip_draws"]),
        seed=20260812,
    )
    inference = {
        "all_declared": all_inference,
        "sdm_evaluable_only": evaluable_inference,
        "superiority_gate": None,
        "interpretation": reporting["claim_rule"],
    }
    (output / "sdm_pair_level_inference.json").write_text(
        json.dumps(inference, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    ok_folds = folds[folds.get("sdm_status", pd.Series(dtype=str)).astype(str).eq("sdm_ok")]
    jaccard = pd.to_numeric(ok_folds.get("top5_jaccard"), errors="coerce").dropna()
    exact = (
        ok_folds.get("exact_set_agreement", pd.Series(dtype=object))
        .astype(str)
        .str.lower()
        .isin({"true", "1"})
    )
    overlap = {
        "sdm_ok_folds": int(len(ok_folds)),
        "folds_with_finite_jaccard": int(len(jaccard)),
        "mean_top5_jaccard": float(jaccard.mean()) if len(jaccard) else None,
        "median_top5_jaccard": float(jaccard.median()) if len(jaccard) else None,
        "exact_set_agreement_folds": int(exact.sum()) if len(ok_folds) else 0,
        "exact_set_agreement_rate": float(exact.mean()) if len(ok_folds) else None,
    }
    (output / "sdm_set_overlap.json").write_text(
        json.dumps(overlap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    manifest = {
        "status": "secondary_sdm_positioning_aggregated",
        "secondary_sdm_protocol_fingerprint": protocol_fp,
        "declared_pairs": int(len(all_declared)),
        "sdm_evaluable_pairs": int(len(evaluable)),
        "sdm_ok_folds": int(overlap["sdm_ok_folds"]),
        "primary_result_modified": False,
        "superiority_gate": None,
        "all_declared_inference": all_inference,
        "sdm_evaluable_inference": evaluable_inference,
        "set_overlap": overlap,
        "no_retuning_after_outcome": True,
    }
    (output / "secondary_sdm_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--cohort", type=Path, required=True)
    command.add_argument("--secondary-root", type=Path, required=True)
    command.add_argument("--primary-aggregate", type=Path, required=True)
    command.add_argument(
        "--output", type=Path, default=Path("practical_core_secondary_sdm_aggregate")
    )
    return command


if __name__ == "__main__":
    args = parser().parse_args()
    print(json.dumps(run(args), indent=2, ensure_ascii=False))
