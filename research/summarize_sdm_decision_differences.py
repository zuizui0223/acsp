#!/usr/bin/env python3
"""Describe ACSP–SDM decision differences without using held-out outcomes.

This is a descriptive positioning diagnostic, not a superiority test. It reads frozen
pair artifacts after decisions have been produced and compares the selected Top-k sets,
the local-evidence and fitted-SDM score profiles of those selections, and their spatial
dispersion. Held-out coordinates and recovery columns are not read by this script.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

LOCAL_SCORE_COLUMNS = (
    "component_local_habitat_score",
    "habitat_score",
    "analogue_score",
)


def _ids_from_decisions(decisions: dict[str, Any], method: str) -> list[str]:
    methods = decisions.get("methods", {})
    values = methods.get(method, [])
    if not isinstance(values, list):
        return []
    return [str(value) for value in values if str(value) and str(value) != "nan"]


def _method_status(fold_result: pd.DataFrame, method: str) -> str:
    row = fold_result[fold_result["decision_method"].astype(str).eq(method)]
    if row.empty:
        return "missing"
    return str(row.iloc[0].get("method_status", "missing"))


def _local_score_column(candidates: pd.DataFrame) -> str | None:
    for column in LOCAL_SCORE_COLUMNS:
        if column in candidates.columns and pd.to_numeric(candidates[column], errors="coerce").notna().any():
            return column
    return None


def _spearman_from_ranks(x: pd.Series, y: pd.Series) -> float:
    frame = pd.DataFrame({"x": pd.to_numeric(x, errors="coerce"), "y": pd.to_numeric(y, errors="coerce")}).dropna()
    if len(frame) < 3 or frame["x"].nunique() < 2 or frame["y"].nunique() < 2:
        return float("nan")
    xr = frame["x"].rank(method="average")
    yr = frame["y"].rank(method="average")
    return float(xr.corr(yr))


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2.0) ** 2
    return 2.0 * radius * math.asin(min(1.0, math.sqrt(a)))


def _mean_pairwise_distance(candidates: pd.DataFrame, selected_ids: list[str]) -> float:
    required = {"candidate_id", "latitude", "longitude"}
    if not required.issubset(candidates.columns):
        return float("nan")
    indexed = candidates.drop_duplicates("candidate_id").set_index(candidates["candidate_id"].astype(str))
    rows = indexed.reindex(selected_ids)[["latitude", "longitude"]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(rows) < 2:
        return float("nan")
    distances = [
        _haversine_km(float(a.latitude), float(a.longitude), float(b.latitude), float(b.longitude))
        for a, b in itertools.combinations(rows.itertuples(index=False), 2)
    ]
    return float(np.mean(distances)) if distances else float("nan")


def _selected_mean(candidates: pd.DataFrame, selected_ids: list[str], column: str | None) -> float:
    if not column or "candidate_id" not in candidates.columns or column not in candidates.columns:
        return float("nan")
    subset = candidates[candidates["candidate_id"].astype(str).isin(selected_ids)]
    values = pd.to_numeric(subset[column], errors="coerce").dropna()
    return float(values.mean()) if len(values) else float("nan")


def describe_fold(pair_dir: Path, fold_dir: Path) -> dict[str, Any]:
    pair_manifest = json.loads((pair_dir / "pair_manifest.json").read_text(encoding="utf-8"))
    candidates = pd.read_csv(fold_dir / "candidate_pool_pre_outcome.csv")
    decisions = json.loads((fold_dir / "decision_sets.json").read_text(encoding="utf-8"))
    fold_result = pd.read_csv(fold_dir / "fold_result.csv")

    acsp_ids = _ids_from_decisions(decisions, "frozen_acsp")
    sdm_ids = _ids_from_decisions(decisions, "fitted_sdm_top_k")
    acsp_set = set(acsp_ids)
    sdm_set = set(sdm_ids)
    shared = acsp_set & sdm_set
    union = acsp_set | sdm_set
    local_col = _local_score_column(candidates)

    if local_col and "sdm_suitability" in candidates.columns:
        rank_corr = _spearman_from_ranks(candidates[local_col], candidates["sdm_suitability"])
    else:
        rank_corr = float("nan")

    return {
        "pair_id": int(pair_manifest["pair_id"]),
        "repeat": int(fold_dir.name.split("_")[1]),
        "taxon_group": str(pair_manifest.get("taxon_group", "")),
        "scientific_name": str(pair_manifest.get("scientific_name", "")),
        "region_name": str(pair_manifest.get("region_name", "")),
        "candidate_pool": int(len(candidates)),
        "acsp_status": _method_status(fold_result, "frozen_acsp"),
        "sdm_status": _method_status(fold_result, "fitted_sdm_top_k"),
        "acsp_selected_n": int(len(acsp_set)),
        "sdm_selected_n": int(len(sdm_set)),
        "shared_count": int(len(shared)),
        "union_count": int(len(union)),
        "jaccard_overlap": float(len(shared) / len(union)) if union else float("nan"),
        "exact_set_match": bool(acsp_set == sdm_set and len(acsp_set) > 0),
        "local_score_column": local_col or "",
        "local_sdm_rank_spearman": rank_corr,
        "acsp_mean_local_evidence": _selected_mean(candidates, acsp_ids, local_col),
        "sdm_mean_local_evidence": _selected_mean(candidates, sdm_ids, local_col),
        "acsp_mean_sdm_suitability": _selected_mean(candidates, acsp_ids, "sdm_suitability"),
        "sdm_mean_sdm_suitability": _selected_mean(candidates, sdm_ids, "sdm_suitability"),
        "acsp_mean_pairwise_distance_km": _mean_pairwise_distance(candidates, acsp_ids),
        "sdm_mean_pairwise_distance_km": _mean_pairwise_distance(candidates, sdm_ids),
    }


def _pair_summary(folds: pd.DataFrame) -> pd.DataFrame:
    evaluable = folds[folds["acsp_status"].eq("ok") & folds["sdm_status"].eq("ok")].copy()
    if evaluable.empty:
        return pd.DataFrame()
    grouped = evaluable.groupby(
        ["pair_id", "taxon_group", "scientific_name", "region_name"], as_index=False
    ).agg(
        evaluable_folds=("repeat", "nunique"),
        mean_shared_count=("shared_count", "mean"),
        mean_jaccard_overlap=("jaccard_overlap", "mean"),
        exact_set_match_fraction=("exact_set_match", "mean"),
        mean_local_sdm_rank_spearman=("local_sdm_rank_spearman", "mean"),
        mean_acsp_local_evidence=("acsp_mean_local_evidence", "mean"),
        mean_sdm_local_evidence=("sdm_mean_local_evidence", "mean"),
        mean_acsp_sdm_suitability=("acsp_mean_sdm_suitability", "mean"),
        mean_sdm_sdm_suitability=("sdm_mean_sdm_suitability", "mean"),
        mean_acsp_pairwise_distance_km=("acsp_mean_pairwise_distance_km", "mean"),
        mean_sdm_pairwise_distance_km=("sdm_mean_pairwise_distance_km", "mean"),
    )
    return grouped


def _group_summary(folds: pd.DataFrame) -> pd.DataFrame:
    evaluable = folds[folds["acsp_status"].eq("ok") & folds["sdm_status"].eq("ok")].copy()
    groups: list[tuple[str, pd.DataFrame]] = [("all", evaluable)]
    groups.extend((str(group), frame) for group, frame in evaluable.groupby("taxon_group", sort=True))
    rows = []
    for group, frame in groups:
        if frame.empty:
            continue
        rows.append({
            "taxon_group": group,
            "evaluable_folds": int(len(frame)),
            "evaluable_pairs": int(frame["pair_id"].nunique()),
            "mean_shared_count": float(frame["shared_count"].mean()),
            "mean_jaccard_overlap": float(frame["jaccard_overlap"].mean()),
            "exact_set_match_fraction": float(frame["exact_set_match"].mean()),
            "mean_local_sdm_rank_spearman": float(frame["local_sdm_rank_spearman"].mean()),
            "mean_acsp_local_evidence": float(frame["acsp_mean_local_evidence"].mean()),
            "mean_sdm_local_evidence": float(frame["sdm_mean_local_evidence"].mean()),
            "mean_acsp_sdm_suitability": float(frame["acsp_mean_sdm_suitability"].mean()),
            "mean_sdm_sdm_suitability": float(frame["sdm_mean_sdm_suitability"].mean()),
            "mean_acsp_pairwise_distance_km": float(frame["acsp_mean_pairwise_distance_km"].mean()),
            "mean_sdm_pairwise_distance_km": float(frame["sdm_mean_pairwise_distance_km"].mean()),
        })
    return pd.DataFrame(rows)


def run(pair_root: Path, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    pair_dirs = sorted(path for path in pair_root.glob("pair_[0-9][0-9][0-9]") if path.is_dir())
    for pair_dir in pair_dirs:
        for fold_dir in sorted(path for path in pair_dir.glob("fold_[0-9][0-9][0-9]") if path.is_dir()):
            rows.append(describe_fold(pair_dir, fold_dir))

    folds = pd.DataFrame(rows)
    folds.to_csv(output / "fold_decision_differences.csv", index=False)
    pairs = _pair_summary(folds) if not folds.empty else pd.DataFrame()
    pairs.to_csv(output / "pair_decision_differences.csv", index=False)
    summary = _group_summary(folds) if not folds.empty else pd.DataFrame()
    summary.to_csv(output / "decision_difference_summary.csv", index=False)

    result = {
        "status": "complete",
        "pair_artifacts_seen": int(len(pair_dirs)),
        "folds_seen": int(len(folds)),
        "sdm_evaluable_folds": int((folds["sdm_status"].eq("ok") & folds["acsp_status"].eq("ok")).sum()) if not folds.empty else 0,
        "interpretation": "Descriptive ACSP-SDM decision differentiation only; no held-out outcomes are read and no universal superiority claim is tested.",
        "outputs": [
            "fold_decision_differences.csv",
            "pair_decision_differences.csv",
            "decision_difference_summary.csv",
        ],
    }
    (output / "decision_difference_manifest.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.pair_root, args.output), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
