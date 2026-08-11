#!/usr/bin/env python3
"""Reproduce grouped cross-taxon development validation for experimental ACSP v2.

This script consumes the exact reviewed 2026-07-24 standard-baseline artifacts.
It is development-only: model and selection hyperparameters were chosen while
these artifacts were available, so the result must never be presented as
independent confirmation.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from acsp.practical_v2 import (
    CandidateDecisionUtilityPolicy,
    V2_CATEGORICAL_FEATURES,
    V2_NUMERIC_FEATURES,
    V2_PROTOCOL_FINGERPRINT,
    build_candidate_decision_utility_features,
    development_protocol_fingerprint,
)

EARTH_RADIUS_KM = 6_371.0088


def _safe_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _ids(value: object) -> set[str]:
    if value is None or pd.isna(value):
        return set()
    return {item for item in str(value).split(";") if item and item.lower() != "nan"}


def _recovered_fraction(frame: pd.DataFrame, indices: list[int]) -> float:
    if frame.empty:
        return 0.0
    all_ids: set[str] = set()
    recovered: set[str] = set()
    if "all_heldout_ids" in frame.columns:
        for value in frame["all_heldout_ids"].dropna():
            all_ids |= _ids(value)
    if "covered_heldout_ids" in frame.columns:
        for index in indices:
            recovered |= _ids(frame.iloc[index]["covered_heldout_ids"])
    return len(recovered & all_ids) / len(all_ids) if all_ids else 0.0


def _haversine_matrix(frame: pd.DataFrame) -> np.ndarray:
    latitude = np.radians(pd.to_numeric(frame["latitude"], errors="coerce").to_numpy(float))
    longitude = np.radians(pd.to_numeric(frame["longitude"], errors="coerce").to_numpy(float))
    dlat = latitude[:, None] - latitude[None, :]
    dlon = longitude[:, None] - longitude[None, :]
    a = (
        np.sin(dlat / 2.0) ** 2
        + np.cos(latitude[:, None]) * np.cos(latitude[None, :]) * np.sin(dlon / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def _stable_ids(frame: pd.DataFrame) -> np.ndarray:
    for column in ("candidate_id", "site_id"):
        if column in frame.columns:
            return frame[column].astype(str).to_numpy()
    return np.array([f"candidate-{index + 1:06d}" for index in range(len(frame))], dtype=str)


def _select_from_scores(
    candidates: pd.DataFrame,
    scores: np.ndarray,
    policy: CandidateDecisionUtilityPolicy,
) -> list[int]:
    if candidates.empty:
        return []
    geographic = _haversine_matrix(candidates)
    stable_id = _stable_ids(candidates)
    selected: list[int] = []
    while len(selected) < min(policy.top_k, len(candidates)):
        best_index = None
        best_key = None
        for index in range(len(candidates)):
            if index in selected:
                continue
            if selected:
                nearest = float(np.min(geographic[index, selected]))
                representation = 1.0 - math.exp(-nearest / policy.geographic_scale_km)
            else:
                representation = policy.first_candidate_representation
            utility = (
                policy.candidate_utility_weight * float(scores[index])
                + policy.geographic_representation_weight * representation
            )
            # Deterministic tie order: utility, learned score, then stable id.
            key = (utility, float(scores[index]), str(stable_id[index]))
            if best_key is None or key > best_key:
                best_key = key
                best_index = index
        assert best_index is not None
        selected.append(int(best_index))
    return selected


def _cohort_name(root: Path) -> str:
    text = str(root).lower()
    if "mixed" in text:
        return "mixed"
    if "plant" in text:
        return "plants"
    raise ValueError(f"cannot infer development cohort from path: {root}")


def _load_artifact(root: Path) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    result_files = list(root.rglob("fold_method_comparison.csv"))
    if len(result_files) != 1:
        raise ValueError(f"expected one fold_method_comparison.csv under {root}, found {len(result_files)}")
    fold_results = pd.read_csv(result_files[0])
    cohort = _cohort_name(root)
    folds: list[dict[str, object]] = []
    candidate_files = sorted(root.rglob("candidates.csv"))
    pattern = re.compile(r"pair_(\d+).+fold_(\d+).+candidates\.csv$")
    for path in candidate_files:
        normalized = str(path).replace("\\", "/")
        match = pattern.search(normalized)
        if not match:
            continue
        pair_id = int(match.group(1))
        repeat = int(match.group(2))
        result = fold_results[
            fold_results["pair_id"].eq(pair_id) & fold_results["repeat"].eq(repeat)
        ]
        if result.empty:
            raise ValueError(f"missing fold result for {cohort} pair {pair_id} repeat {repeat}")
        taxon_group = str(result["taxon_group"].iloc[0])
        candidates = _safe_csv(path)
        folds.append({
            "cohort": cohort,
            "pair_id": pair_id,
            "repeat": repeat,
            "group_id": f"{cohort}_{pair_id}",
            "taxon_group": taxon_group,
            "candidates": candidates,
            "results": result.copy(),
        })
    return fold_results, folds


def _candidate_training_table(folds: list[dict[str, object]]) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for fold in folds:
        candidates = fold["candidates"]
        if not isinstance(candidates, pd.DataFrame) or candidates.empty:
            continue
        features = build_candidate_decision_utility_features(candidates, str(fold["taxon_group"]))
        if len(features) != len(candidates):
            raise ValueError("candidate feature builder unexpectedly dropped rows")
        target: list[int] = []
        for _, row in candidates.reset_index(drop=True).iterrows():
            all_ids = _ids(row.get("all_heldout_ids"))
            covered = _ids(row.get("covered_heldout_ids"))
            target.append(int(bool(covered & all_ids)))
        table = features[list(V2_NUMERIC_FEATURES) + list(V2_CATEGORICAL_FEATURES) + ["_source_index"]].copy()
        table["covered_any"] = target
        table["cohort"] = fold["cohort"]
        table["pair_id"] = fold["pair_id"]
        table["repeat"] = fold["repeat"]
        table["group_id"] = fold["group_id"]
        rows.append(table)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _model_pipeline(protocol: dict[str, object]) -> Pipeline:
    model = protocol["model"]
    categories = model["categories"]
    numeric = list(model["numeric_features"])
    categorical = list(model["categorical_features"])
    preprocess = ColumnTransformer([
        ("numeric", Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
        ]), numeric),
        ("categorical", OneHotEncoder(
            categories=[categories[name] for name in categorical],
            handle_unknown="ignore",
        ), categorical),
    ])
    return Pipeline([
        ("preprocess", preprocess),
        ("model", LogisticRegression(
            C=float(model["C"]),
            class_weight=model["class_weight"],
            max_iter=1000,
        )),
    ])


def _pair_inference(pair_table: pd.DataFrame) -> dict[str, float | int | list[float]]:
    difference = (
        pair_table["acsp_v2_candidate_utility"] - pair_table["frozen_acsp"]
    ).to_numpy(float)
    rng = np.random.default_rng(22)
    draws = 30_000
    bootstrap = rng.choice(difference, size=(draws, len(difference)), replace=True).mean(axis=1)
    null = (rng.choice(np.array([-1.0, 1.0]), size=(draws, len(difference))) * difference).mean(axis=1)
    observed = abs(float(difference.mean()))
    return {
        "pairs": int(len(difference)),
        "mean_difference": float(difference.mean()),
        "bootstrap_ci_low": float(np.quantile(bootstrap, 0.025)),
        "bootstrap_ci_high": float(np.quantile(bootstrap, 0.975)),
        "sign_flip_p": float((1 + np.sum(np.abs(null) >= observed)) / (draws + 1)),
        "positive_pairs": int(np.sum(difference > 0)),
        "negative_pairs": int(np.sum(difference < 0)),
        "tied_pairs": int(np.sum(difference == 0)),
    }


def run(roots: list[Path], protocol_path: Path, output: Path) -> dict[str, object]:
    protocol = json.loads(protocol_path.read_text())
    if development_protocol_fingerprint(protocol) != V2_PROTOCOL_FINGERPRINT:
        raise ValueError("v2 protocol fingerprint mismatch")
    if protocol["fingerprint"] != V2_PROTOCOL_FINGERPRINT:
        raise ValueError("committed v2 fingerprint mismatch")

    all_folds: list[dict[str, object]] = []
    for root in roots:
        _, folds = _load_artifact(root)
        all_folds.extend(folds)
    if len(all_folds) != 240:
        raise ValueError(f"expected 240 development folds, found {len(all_folds)}")
    group_ids = sorted({str(fold["group_id"]) for fold in all_folds})
    if len(group_ids) != 48:
        raise ValueError(f"expected 48 unique taxon-region pairs, found {len(group_ids)}")

    training = _candidate_training_table(all_folds)
    frozen_groups = {str(key): int(value) for key, value in protocol["development"]["outer_group_folds"].items()}
    if set(frozen_groups) != set(group_ids):
        raise ValueError("development group set differs from frozen eight-fold assignment")

    predictions = np.full(len(training), np.nan, dtype=float)
    for outer_fold in range(1, 9):
        test_groups = {group for group, fold in frozen_groups.items() if fold == outer_fold}
        train_mask = ~training["group_id"].isin(test_groups)
        test_mask = training["group_id"].isin(test_groups)
        estimator = _model_pipeline(protocol)
        estimator.fit(training.loc[train_mask], training.loc[train_mask, "covered_any"])
        predictions[test_mask.to_numpy()] = estimator.predict_proba(training.loc[test_mask])[:, 1]
    if not np.isfinite(predictions).all():
        raise ValueError("cross-fitted candidate predictions are incomplete")
    training["crossfit_score"] = predictions

    policy = CandidateDecisionUtilityPolicy()
    fold_rows: list[dict[str, object]] = []
    training_lookup = {
        (str(group), int(repeat)): table.copy()
        for (group, repeat), table in training.groupby(["group_id", "repeat"])
    }
    methods = [
        "frozen_acsp",
        "local_evidence_top_k",
        "geographic_maximin",
        "random_same_pool_mean",
    ]
    for fold in all_folds:
        candidates = fold["candidates"]
        group_id = str(fold["group_id"])
        repeat = int(fold["repeat"])
        v2_recall = 0.0
        selected_ids = ""
        if isinstance(candidates, pd.DataFrame) and not candidates.empty:
            scored = training_lookup[(group_id, repeat)].sort_values("_source_index")
            if len(scored) != len(candidates):
                raise ValueError("cross-fit candidate row count mismatch")
            indices = _select_from_scores(candidates.reset_index(drop=True), scored["crossfit_score"].to_numpy(float), policy)
            v2_recall = _recovered_fraction(candidates.reset_index(drop=True), indices)
            stable = _stable_ids(candidates.reset_index(drop=True))
            selected_ids = ";".join(stable[index] for index in indices)
        fold_rows.append({
            "cohort": fold["cohort"],
            "pair_id": fold["pair_id"],
            "repeat": repeat,
            "group_id": group_id,
            "taxon_group": fold["taxon_group"],
            "decision_method": "acsp_v2_candidate_utility",
            "heldout_recall": v2_recall,
            "selected_ids": selected_ids,
        })
        result = fold["results"]
        for method in methods:
            row = result[result["decision_method"].eq(method)]
            value = 0.0
            if not row.empty and str(row["status"].iloc[0]) == "ok":
                value = float(row["heldout_recall"].iloc[0])
            fold_rows.append({
                "cohort": fold["cohort"],
                "pair_id": fold["pair_id"],
                "repeat": repeat,
                "group_id": group_id,
                "taxon_group": fold["taxon_group"],
                "decision_method": method,
                "heldout_recall": value,
                "selected_ids": "",
            })

    fold_table = pd.DataFrame(fold_rows)
    pair_table = (
        fold_table.groupby(["group_id", "taxon_group", "decision_method"], as_index=False)["heldout_recall"]
        .mean()
        .pivot(index=["group_id", "taxon_group"], columns="decision_method", values="heldout_recall")
        .reset_index()
    )
    method_summary = (
        pair_table.drop(columns=["group_id"])
        .groupby("taxon_group", dropna=False)
        .mean(numeric_only=True)
        .reset_index()
    )
    overall = {
        column: float(pair_table[column].mean())
        for column in ["acsp_v2_candidate_utility", *methods]
    }
    inference = _pair_inference(pair_table)

    expected = protocol["development"]["development_result"]
    # These checks make the frozen development snapshot executable rather than
    # relying on a manually copied result. Small floating differences are okay.
    if not math.isclose(overall["acsp_v2_candidate_utility"], float(expected["v2_mean_recall"]), abs_tol=5e-4):
        raise ValueError(f"v2 development recall changed: {overall['acsp_v2_candidate_utility']}")
    if not math.isclose(overall["frozen_acsp"], float(expected["frozen_v1_mean_recall"]), abs_tol=5e-4):
        raise ValueError("frozen v1 development recall changed")
    if not math.isclose(inference["mean_difference"], float(expected["v2_minus_v1_mean"]), abs_tol=5e-4):
        raise ValueError("v2-minus-v1 development contrast changed")

    output.mkdir(parents=True, exist_ok=True)
    fold_table.to_csv(output / "fold_method_comparison.csv", index=False)
    pair_table.to_csv(output / "pair_level_comparison.csv", index=False)
    method_summary.to_csv(output / "taxon_group_method_summary.csv", index=False)
    manifest = {
        "status": "development_reproduced_pending_untouched_confirmation",
        "protocol_id": protocol["protocol_id"],
        "protocol_fingerprint": protocol["fingerprint"],
        "development_pairs": len(group_ids),
        "expected_folds": len(all_folds),
        "candidate_training_rows": int(len(training)),
        "overall_pair_mean_recall": overall,
        "v2_minus_v1_pair_inference": inference,
        "independent_confirmation_required": True,
        "claim_boundary": "development evidence only; hyperparameters were selected on these source artifacts",
    }
    (output / "development_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", action="append", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=Path("validation/acsp_v2_candidate_utility_protocol.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.artifact_root, args.protocol, args.output), indent=2))


if __name__ == "__main__":
    main()
