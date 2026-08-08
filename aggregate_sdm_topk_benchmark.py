#!/usr/bin/env python3
"""Aggregate untouched fitted-SDM Top-k pair artifacts with pair-level inference."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from run_sdm_topk_pair import (
    COHORT_PATH,
    CONTRACT_PATH,
    EXPECTED_CONTRACT,
    EXPECTED_PROTOCOL,
    METHODS,
    PROTOCOL_PATH,
    _canonical_fingerprint,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_pair(pair_dir: Path, protocol_fp: str, contract_fp: str) -> dict[str, Any]:
    manifest_path = pair_dir / "pair_manifest.json"
    result_path = pair_dir / "fold_results.csv"
    if not manifest_path.exists() or not result_path.exists():
        raise FileNotFoundError(f"pair artifact incomplete: {pair_dir}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("protocol_fingerprint") != protocol_fp:
        raise ValueError(f"protocol mismatch in {pair_dir}")
    if manifest.get("execution_contract_fingerprint") != contract_fp:
        raise ValueError(f"execution contract mismatch in {pair_dir}")
    if manifest.get("fold_result_sha256") != _sha256(result_path):
        raise ValueError(f"fold result checksum mismatch in {pair_dir}")
    for fold_dir in sorted(pair_dir.glob("fold_*")):
        fold_manifest_path = fold_dir / "fold_manifest.json"
        if not fold_manifest_path.exists():
            raise FileNotFoundError(f"missing fold manifest: {fold_dir}")
        fold_manifest = json.loads(fold_manifest_path.read_text(encoding="utf-8"))
        if fold_manifest.get("protocol_fingerprint") != protocol_fp:
            raise ValueError(f"fold protocol mismatch: {fold_dir}")
        if fold_manifest.get("execution_contract_fingerprint") != contract_fp:
            raise ValueError(f"fold contract mismatch: {fold_dir}")
        for metadata in fold_manifest.get("files", {}).values():
            path = fold_dir / str(metadata["path"])
            if not path.exists() or _sha256(path) != metadata.get("sha256"):
                raise ValueError(f"fold checksum mismatch: {path}")
    return manifest


def _expected_rows(cohort: pd.DataFrame, repeats: int) -> pd.DataFrame:
    rows = []
    for pair in cohort.itertuples(index=False):
        for repeat in range(1, repeats + 1):
            for method in METHODS:
                rows.append({
                    "pair_id": int(pair.pair_id),
                    "repeat": repeat,
                    "taxon_group": str(pair.taxon_group),
                    "scientific_name": str(pair.scientific_name),
                    "region_name": str(pair.region_name),
                    "decision_method": method,
                })
    return pd.DataFrame(rows)


def _complete_fold_table(raw: pd.DataFrame, cohort: pd.DataFrame, repeats: int) -> pd.DataFrame:
    expected = _expected_rows(cohort, repeats)
    keys = ["pair_id", "repeat", "decision_method"]
    if raw.empty:
        merged = expected.copy()
    else:
        raw = raw.copy()
        raw["pair_id"] = pd.to_numeric(raw["pair_id"], errors="coerce").astype("Int64")
        raw["repeat"] = pd.to_numeric(raw["repeat"], errors="coerce").astype("Int64")
        if raw.duplicated(keys).any():
            duplicated = raw.loc[raw.duplicated(keys, keep=False), keys]
            raise ValueError(f"duplicate fold-method rows:\n{duplicated}")
        merged = expected.merge(
            raw.drop(columns=[c for c in ("taxon_group", "scientific_name", "region_name") if c in raw.columns]),
            on=keys,
            how="left",
        )
    merged["heldout_recall"] = pd.to_numeric(merged.get("heldout_recall"), errors="coerce").fillna(0.0)
    merged["method_status"] = merged.get("method_status", pd.Series(index=merged.index, dtype=str)).fillna("artifact_missing")
    merged["heldout_records"] = pd.to_numeric(merged.get("heldout_records"), errors="coerce").fillna(0).astype(int)
    merged["candidate_pool"] = pd.to_numeric(merged.get("candidate_pool"), errors="coerce").fillna(0).astype(int)
    merged["sdm_fold_ok"] = merged.get("sdm_fold_ok", pd.Series(False, index=merged.index)).fillna(False).astype(bool)
    merged["selected_ids"] = merged.get("selected_ids", pd.Series("", index=merged.index)).fillna("").astype(str)
    return merged.sort_values(keys, kind="mergesort").reset_index(drop=True)


def _primary_pair_table(folds: pd.DataFrame, cohort: pd.DataFrame, repeats: int) -> pd.DataFrame:
    means = folds.groupby(["pair_id", "decision_method"], as_index=False).agg(
        observed_fold_rows=("repeat", "size"),
        summed_recall=("heldout_recall", "sum"),
    )
    means["pair_mean_recall"] = means["summed_recall"] / float(repeats)
    metadata = cohort[["pair_id", "taxon_group", "scientific_name", "region_name", "geographic_stratum"]].copy()
    return means.merge(metadata, on="pair_id", how="left").drop(columns="summed_recall")


def _sdm_evaluable_pair_table(folds: pd.DataFrame, cohort: pd.DataFrame) -> pd.DataFrame:
    sdm_ok = folds[
        folds["decision_method"].eq("fitted_sdm_top_k")
        & folds["method_status"].eq("ok")
    ][["pair_id", "repeat"]].drop_duplicates()
    if sdm_ok.empty:
        return pd.DataFrame()
    restricted = folds.merge(sdm_ok, on=["pair_id", "repeat"], how="inner")
    means = restricted.groupby(["pair_id", "decision_method"], as_index=False).agg(
        sdm_evaluable_folds=("repeat", "nunique"),
        pair_mean_recall=("heldout_recall", "mean"),
    )
    metadata = cohort[["pair_id", "taxon_group", "scientific_name", "region_name", "geographic_stratum"]].copy()
    return means.merge(metadata, on="pair_id", how="left")


def _contrast_rows(
    pair_table: pd.DataFrame,
    *,
    estimand: str,
    bootstrap_draws: int,
    sign_flip_draws: int,
    seed: int,
) -> list[dict[str, Any]]:
    contrasts = (
        ("frozen_acsp", "fitted_sdm_top_k"),
        ("local_evidence_top_k", "fitted_sdm_top_k"),
        ("fitted_sdm_top_k", "random_same_pool_mean"),
        ("geographic_maximin", "fitted_sdm_top_k"),
    )
    rows: list[dict[str, Any]] = []
    if pair_table.empty:
        return rows
    group_specs = [("all", pair_table)]
    group_specs.extend((str(group), frame) for group, frame in pair_table.groupby("taxon_group", sort=True))
    for group_name, frame in group_specs:
        wide = frame.pivot(index="pair_id", columns="decision_method", values="pair_mean_recall")
        for numerator, denominator in contrasts:
            if numerator not in wide.columns or denominator not in wide.columns:
                continue
            paired = wide[[numerator, denominator]].dropna()
            if paired.empty:
                continue
            differences = (paired[numerator] - paired[denominator]).to_numpy(float)
            n = len(differences)
            rng = np.random.default_rng(int(seed) + sum(ord(ch) for ch in f"{estimand}:{group_name}:{numerator}:{denominator}"))
            bootstrap = rng.choice(differences, size=(int(bootstrap_draws), n), replace=True).mean(axis=1)
            signs = rng.choice(np.array([-1.0, 1.0]), size=(int(sign_flip_draws), n))
            null = (signs * differences).mean(axis=1)
            observed = abs(float(differences.mean()))
            rows.append({
                "estimand": estimand,
                "taxon_group": group_name,
                "numerator_method": numerator,
                "denominator_method": denominator,
                "paired_taxon_region_pairs": n,
                "mean_pair_difference": float(differences.mean()),
                "bootstrap_ci_low": float(np.quantile(bootstrap, 0.025)),
                "bootstrap_ci_high": float(np.quantile(bootstrap, 0.975)),
                "bootstrap_probability_positive": float(np.mean(bootstrap > 0)),
                "sign_flip_p": float((1 + np.sum(np.abs(null) >= observed)) / (int(sign_flip_draws) + 1)),
            })
    return rows


def run(args: argparse.Namespace) -> dict[str, Any]:
    protocol_fp = _canonical_fingerprint(PROTOCOL_PATH, "protocol_fingerprint")
    contract_fp = _canonical_fingerprint(CONTRACT_PATH, "contract_fingerprint")
    if protocol_fp != EXPECTED_PROTOCOL or contract_fp != EXPECTED_CONTRACT:
        raise ValueError("frozen protocol/contract fingerprint differs from aggregate constants")
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    cohort = pd.read_csv(COHORT_PATH)
    cohort = cohort[cohort["status"].eq("predeclared")].copy()
    root = Path(args.pair_root)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    raw_frames: list[pd.DataFrame] = []
    pair_audits: list[dict[str, Any]] = []
    for pair in cohort.itertuples(index=False):
        pair_dir = root / f"pair_{int(pair.pair_id):03d}"
        try:
            manifest = _verify_pair(pair_dir, protocol_fp, contract_fp)
            frame = pd.read_csv(pair_dir / "fold_results.csv")
            pair_audits.append({
                "pair_id": int(pair.pair_id),
                "artifact_status": "verified",
                "pair_status": manifest.get("pair_status", "unknown"),
                "sdm_ok_folds": int(manifest.get("sdm_ok_folds", 0)),
            })
            raw_frames.append(frame)
        except Exception as exc:
            pair_audits.append({
                "pair_id": int(pair.pair_id),
                "artifact_status": "verification_failure",
                "pair_status": "artifact_failure",
                "sdm_ok_folds": 0,
                "error": f"{type(exc).__name__}: {exc}",
            })
    raw = pd.concat(raw_frames, ignore_index=True) if raw_frames else pd.DataFrame()
    repeats = int(protocol["outer_validation"]["repeats"])
    folds = _complete_fold_table(raw, cohort, repeats)
    folds.to_csv(output / "all_fold_results.csv", index=False)

    primary = _primary_pair_table(folds, cohort, repeats)
    primary.to_csv(output / "pair_level_intention_to_evaluate.csv", index=False)
    secondary = _sdm_evaluable_pair_table(folds, cohort)
    secondary.to_csv(output / "pair_level_sdm_evaluable.csv", index=False)

    inference_rows = []
    inference_rows.extend(_contrast_rows(
        primary,
        estimand="all_declared_intention_to_evaluate",
        bootstrap_draws=int(protocol["inference"]["bootstrap_draws"]),
        sign_flip_draws=int(protocol["inference"]["sign_flip_draws"]),
        seed=int(protocol["cohort"]["seed"]),
    ))
    inference_rows.extend(_contrast_rows(
        secondary,
        estimand="sdm_evaluable_folds_only",
        bootstrap_draws=int(protocol["inference"]["bootstrap_draws"]),
        sign_flip_draws=int(protocol["inference"]["sign_flip_draws"]),
        seed=int(protocol["cohort"]["seed"]) + 1,
    ))
    inference = pd.DataFrame(inference_rows)
    inference.to_csv(output / "pair_level_inference.csv", index=False)

    method_summary = primary.groupby(["taxon_group", "decision_method"], as_index=False).agg(
        declared_pairs=("pair_id", "nunique"),
        mean_pair_recall=("pair_mean_recall", "mean"),
        median_pair_recall=("pair_mean_recall", "median"),
    )
    method_summary.to_csv(output / "method_summary.csv", index=False)
    audit = pd.DataFrame(pair_audits).sort_values("pair_id")
    audit.to_csv(output / "pair_artifact_audit.csv", index=False)

    sdm_method_rows = folds[folds["decision_method"].eq("fitted_sdm_top_k")]
    result: dict[str, Any] = {
        "status": "complete",
        "protocol_fingerprint": protocol_fp,
        "execution_contract_fingerprint": contract_fp,
        "declared_pairs": int(len(cohort)),
        "verified_pair_artifacts": int(audit["artifact_status"].eq("verified").sum()),
        "artifact_verification_failures": int(audit["artifact_status"].ne("verified").sum()),
        "expected_fold_method_rows": int(len(cohort) * repeats * len(METHODS)),
        "written_fold_method_rows": int(len(folds)),
        "sdm_ok_folds": int(sdm_method_rows["method_status"].eq("ok").sum()),
        "sdm_failed_or_missing_folds": int(sdm_method_rows["method_status"].ne("ok").sum()),
        "pairs_with_at_least_one_sdm_ok_fold": int(
            secondary.loc[secondary["decision_method"].eq("fitted_sdm_top_k"), "pair_id"].nunique()
        ) if not secondary.empty else 0,
        "method_summary": method_summary.to_dict("records"),
        "inference": inference.to_dict("records"),
        "claim_guardrail": "No manuscript or claim-matrix change is implied until this untouched benchmark is reviewed; negative, equivalent, or SDM-superior outcomes must be retained.",
    }
    (output / "benchmark_manifest.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return result


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--pair-root", default="sdm_topk_pairs")
    command.add_argument("--output", default="sdm_topk_aggregate")
    return command


if __name__ == "__main__":
    print(json.dumps(run(parser().parse_args()), indent=2, ensure_ascii=False))
