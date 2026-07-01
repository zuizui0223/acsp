"""Spatially honest retrospective validation for ACSP candidate builders."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score

from .modeling import DEFAULT_ENSEMBLE_ALGORITHMS, make_classifier

from .planning import EARTH_RADIUS_M, integrated_candidate_scores


CALIBRATABLE_DISTANCE_FREE_COMPONENTS = (
    "local_habitat",
    "macro_model",
    "access",
    "field_validation",
)


def _resolve_occurrence_coordinate_columns(
    occurrences: pd.DataFrame, latitude_col: str, longitude_col: str
) -> tuple[str, str]:
    if latitude_col in occurrences.columns and longitude_col in occurrences.columns:
        return latitude_col, longitude_col
    for latitude, longitude in (
        ("_latitude", "_longitude"),
        ("decimalLatitude", "decimalLongitude"),
        ("lat", "lon"),
        ("lat", "lng"),
    ):
        if latitude in occurrences.columns and longitude in occurrences.columns:
            return latitude, longitude
    missing = {latitude_col, longitude_col}.difference(occurrences.columns)
    raise ValueError(f"Occurrence table is missing: {', '.join(sorted(missing))}")


def _nearest_distances_km(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    if len(source) == 0 or len(target) == 0:
        return np.full(len(target), np.inf, dtype=float)
    lat1 = np.radians(target[:, 0])[:, None]
    lon1 = np.radians(target[:, 1])[:, None]
    lat2 = np.radians(source[:, 0])[None, :]
    lon2 = np.radians(source[:, 1])[None, :]
    a = np.sin((lat2 - lat1) / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2.0) ** 2
    distances = 2.0 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
    return distances.min(axis=1) / 1000.0


def _probability_metrics(labels: np.ndarray, probabilities: np.ndarray, train_labels: np.ndarray, train_probabilities: np.ndarray) -> dict[str, float]:
    clipped = np.clip(np.asarray(probabilities, dtype=float), 1e-6, 1 - 1e-6)
    train_clipped = np.clip(np.asarray(train_probabilities, dtype=float), 1e-6, 1 - 1e-6)
    labels = np.asarray(labels, dtype=int)
    train_labels = np.asarray(train_labels, dtype=int)
    thresholds = np.unique(np.quantile(train_clipped, np.linspace(0.05, 0.95, 19)))
    best_threshold = 0.5
    best_tss = -np.inf
    for threshold in thresholds:
        predicted = train_clipped >= threshold
        sensitivity = float(predicted[train_labels == 1].mean()) if np.any(train_labels == 1) else 0.0
        specificity = float((~predicted[train_labels == 0]).mean()) if np.any(train_labels == 0) else 0.0
        if sensitivity + specificity - 1.0 > best_tss:
            best_tss = sensitivity + specificity - 1.0
            best_threshold = float(threshold)
    predicted = clipped >= best_threshold
    sensitivity = float(predicted[labels == 1].mean())
    specificity = float((~predicted[labels == 0]).mean())
    logits = np.log(clipped / (1.0 - clipped)).reshape(-1, 1)
    try:
        calibration = LogisticRegression(C=1e6).fit(logits, labels)
        calibration_slope = float(calibration.coef_[0, 0])
        calibration_intercept = float(calibration.intercept_[0])
    except Exception:
        calibration_slope = np.nan
        calibration_intercept = np.nan
    bins = pd.qcut(pd.Series(clipped).rank(method="first"), min(10, len(clipped)), labels=False, duplicates="drop")
    boyce_frame = pd.DataFrame({"probability": clipped, "presence": labels, "bin": bins})
    grouped = boyce_frame.groupby("bin", observed=True).agg(midpoint=("probability", "mean"), presences=("presence", "sum"), total=("presence", "size"))
    expected = grouped["total"] / grouped["total"].sum()
    observed = grouped["presences"] / max(1, grouped["presences"].sum())
    ratio = observed / expected.replace(0, np.nan)
    boyce = float(grouped["midpoint"].corr(ratio, method="spearman")) if len(grouped) >= 3 else np.nan
    return {
        "roc_auc": float(roc_auc_score(labels, clipped)),
        "pr_auc": float(average_precision_score(labels, clipped)),
        "brier": float(brier_score_loss(labels, clipped)),
        "log_loss": float(log_loss(labels, clipped, labels=[0, 1])),
        "tss": sensitivity + specificity - 1.0,
        "threshold_from_training": best_threshold,
        "calibration_slope": calibration_slope,
        "calibration_intercept": calibration_intercept,
        "boyce_spearman": boyce,
    }


def spatial_model_accuracy_benchmark(
    table: pd.DataFrame,
    variables: list[str],
    *,
    algorithms: tuple[str, ...] = DEFAULT_ENSEMBLE_ALGORITHMS,
    latitude_col: str = "latitude",
    longitude_col: str = "longitude",
    label_col: str = "presence",
    block_degrees: float = 0.25,
    repeats: int = 5,
    holdout_fraction: float = 0.20,
    random_state: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Evaluate SDM probabilities with repeated spatial-block holdout.

    Thresholds are learned on training predictions only. Fold predictions are
    returned for audit and pooled alternatives; no final all-data fit is used in
    validation metrics.
    """
    required = {latitude_col, longitude_col, label_col, *variables}
    missing = required.difference(table.columns)
    if missing:
        raise ValueError(f"Model benchmark table is missing: {', '.join(sorted(missing))}")
    work = table.copy().reset_index(drop=True)
    work[label_col] = pd.to_numeric(work[label_col], errors="coerce")
    for column in [latitude_col, longitude_col, *variables]:
        work[column] = pd.to_numeric(work[column], errors="coerce")
    work = work.dropna(subset=[latitude_col, longitude_col, label_col, *variables]).reset_index(drop=True)
    if work[label_col].nunique() < 2:
        raise ValueError("Model benchmark requires both presence and background rows.")
    block = max(1e-6, float(block_degrees))
    work["_model_block"] = (
        np.floor(work[latitude_col] / block).astype(int).astype(str) + ":"
        + np.floor(work[longitude_col] / block).astype(int).astype(str)
    )
    blocks = work["_model_block"].drop_duplicates().to_numpy()
    if len(blocks) < 3:
        raise ValueError("Model benchmark requires at least three occupied spatial blocks.")
    rng = np.random.default_rng(int(random_state))
    metric_rows: list[dict[str, Any]] = []
    prediction_rows: list[pd.DataFrame] = []
    holdout_count = min(len(blocks) - 1, max(1, int(round(len(blocks) * float(holdout_fraction)))))
    attempts = 0
    completed = 0
    while completed < max(1, int(repeats)) and attempts < max(20, int(repeats) * 20):
        attempts += 1
        held_blocks = set(rng.choice(blocks, size=holdout_count, replace=False).tolist())
        test_mask = work["_model_block"].isin(held_blocks)
        train = work[~test_mask]
        test = work[test_mask]
        if train[label_col].nunique() < 2 or test[label_col].nunique() < 2 or len(test) < 4:
            continue
        completed += 1
        X_train, y_train = train[variables], train[label_col].astype(int).to_numpy()
        X_test, y_test = test[variables], test[label_col].astype(int).to_numpy()
        test_predictions: dict[str, np.ndarray] = {}
        train_predictions: dict[str, np.ndarray] = {}
        for algorithm in algorithms:
            model = make_classifier(algorithm, random_state=int(random_state) + completed)
            model.fit(X_train, y_train)
            train_predictions[algorithm] = model.predict_proba(X_train)[:, 1]
            test_predictions[algorithm] = model.predict_proba(X_test)[:, 1]
        train_predictions["Equal-weight ensemble"] = np.mean(np.vstack(list(train_predictions.values())), axis=0)
        test_predictions["Equal-weight ensemble"] = np.mean(np.vstack(list(test_predictions.values())), axis=0)
        for algorithm, probabilities in test_predictions.items():
            metrics = _probability_metrics(y_test, probabilities, y_train, train_predictions[algorithm])
            metric_rows.append({
                "repeat": completed, "algorithm": algorithm,
                "training_rows": len(train), "test_rows": len(test),
                "training_presences": int(y_train.sum()), "test_presences": int(y_test.sum()),
                "heldout_blocks": ";".join(sorted(held_blocks)), **metrics,
            })
            prediction_rows.append(pd.DataFrame({
                "repeat": completed, "algorithm": algorithm, "row_id": test.index,
                "label": y_test, "probability": probabilities,
                "latitude": test[latitude_col].to_numpy(), "longitude": test[longitude_col].to_numpy(),
                "spatial_block": test["_model_block"].to_numpy(),
            }))
    if completed < max(1, int(repeats)):
        raise ValueError(f"Only {completed} valid spatial folds could be formed after {attempts} attempts.")
    return pd.DataFrame(metric_rows), pd.concat(prediction_rows, ignore_index=True)


def calibrate_model_ensemble_weights(
    predictions: pd.DataFrame,
    metrics: pd.DataFrame,
    *,
    taxon_col: str = "benchmark_taxon",
    search_draws: int = 2000,
    train_fraction: float = 0.70,
    random_state: int = 42,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Select ensemble weights and probability shrinkage on calibration taxa."""
    base_algorithms = list(DEFAULT_ENSEMBLE_ALGORITHMS)
    required = {taxon_col, "repeat", "row_id", "label", "algorithm", "probability"}
    missing = required.difference(predictions.columns)
    if missing:
        raise ValueError(f"Model predictions are missing: {', '.join(sorted(missing))}")
    taxa = predictions[taxon_col].dropna().astype(str).drop_duplicates().to_numpy()
    if len(taxa) < 10:
        raise ValueError("At least ten taxa are required for held-out ensemble calibration.")
    wide = predictions[predictions["algorithm"].isin(base_algorithms)].pivot_table(
        index=[taxon_col, "repeat", "row_id", "label"], columns="algorithm", values="probability", aggfunc="first"
    ).dropna(subset=base_algorithms).reset_index()
    prevalence = metrics[metrics["algorithm"].eq(base_algorithms[0])][
        [taxon_col, "repeat", "training_presences", "training_rows"]
    ].drop_duplicates([taxon_col, "repeat"])
    prevalence["training_prevalence"] = prevalence["training_presences"] / prevalence["training_rows"]
    wide = wide.merge(prevalence[[taxon_col, "repeat", "training_prevalence"]], on=[taxon_col, "repeat"], how="left")
    rng = np.random.default_rng(int(random_state))
    shuffled = rng.permutation(taxa)
    n_train = min(len(taxa) - 3, max(7, int(round(len(taxa) * float(train_fraction)))))
    calibration_taxa = set(shuffled[:n_train])
    evaluation_taxa = set(shuffled[n_train:])
    equal = np.full(len(base_algorithms), 1.0 / len(base_algorithms))
    weight_vectors = np.vstack([equal, rng.dirichlet(np.ones(len(base_algorithms)), max(1, int(search_draws)))])
    shrinkages = np.linspace(0.35, 1.0, 14)

    def fold_arrays(selected_taxa: set[str]) -> list[tuple[np.ndarray, np.ndarray, np.ndarray]]:
        subset = wide[wide[taxon_col].astype(str).isin(selected_taxa)]
        return [
            (
                fold[base_algorithms].to_numpy(float),
                fold["training_prevalence"].fillna(fold["label"].mean()).to_numpy(float),
                fold["label"].to_numpy(int),
            )
            for _, fold in subset.groupby([taxon_col, "repeat"], sort=False)
        ]

    calibration_folds = fold_arrays(calibration_taxa)
    evaluation_folds = fold_arrays(evaluation_taxa)

    calibration_predictions = np.vstack([fold[0] for fold in calibration_folds])
    calibration_priors = np.concatenate([fold[1] for fold in calibration_folds])
    calibration_labels = np.concatenate([fold[2] for fold in calibration_folds])
    calibration_row_weights = np.concatenate([
        np.full(len(fold[2]), 1.0 / (len(calibration_folds) * len(fold[2])))
        for fold in calibration_folds
    ])

    def evaluate(weights: np.ndarray, shrinkage: float, folds: list[tuple[np.ndarray, np.ndarray, np.ndarray]]) -> tuple[float, float, float]:
        fold_scores = []
        for algorithm_predictions, prior, labels in folds:
            raw = algorithm_predictions @ weights
            probability = np.clip(prior + float(shrinkage) * (raw - prior), 1e-6, 1 - 1e-6)
            fold_scores.append((
                float(log_loss(labels, probability, labels=[0, 1])),
                float(brier_score_loss(labels, probability)),
                float(roc_auc_score(labels, probability)),
            ))
        return tuple(np.mean(fold_scores, axis=0)) if fold_scores else (np.nan, np.nan, np.nan)

    rows = []
    for weight_index, weights in enumerate(weight_vectors):
        raw = calibration_predictions @ weights
        for shrinkage in shrinkages:
            probability = np.clip(
                calibration_priors + float(shrinkage) * (raw - calibration_priors), 1e-6, 1 - 1e-6
            )
            point_log_loss = -(
                calibration_labels * np.log(probability)
                + (1 - calibration_labels) * np.log(1 - probability)
            )
            calibration_log_loss = float(np.sum(calibration_row_weights * point_log_loss))
            calibration_brier = float(np.sum(calibration_row_weights * (probability - calibration_labels) ** 2))
            rows.append({
                "weight_set": weight_index, "probability_shrinkage": float(shrinkage),
                **{f"weight_{name}": float(value) for name, value in zip(base_algorithms, weights)},
                "calibration_log_loss": calibration_log_loss, "calibration_brier": calibration_brier,
            })
    search = pd.DataFrame(rows).sort_values(["calibration_log_loss", "calibration_brier"], kind="mergesort").reset_index(drop=True)
    best = search.iloc[0]
    selected_weights = np.array([best[f"weight_{name}"] for name in base_algorithms], dtype=float)
    selected_eval = evaluate(selected_weights, float(best["probability_shrinkage"]), evaluation_folds)
    equal_eval = evaluate(equal, 1.0, evaluation_folds)
    summary = {
        "design": "ensemble weights and probability shrinkage selected on calibration taxa; reported on unseen taxa",
        "calibration_taxa": sorted(calibration_taxa), "heldout_evaluation_taxa": sorted(evaluation_taxa),
        "selected_weights": {name: round(float(value), 6) for name, value in zip(base_algorithms, selected_weights)},
        "selected_probability_shrinkage": round(float(best["probability_shrinkage"]), 6),
        "heldout_log_loss": round(float(selected_eval[0]), 6), "equal_weight_heldout_log_loss": round(float(equal_eval[0]), 6),
        "heldout_brier": round(float(selected_eval[1]), 6), "equal_weight_heldout_brier": round(float(equal_eval[1]), 6),
        "heldout_roc_auc": round(float(selected_eval[2]), 6), "equal_weight_heldout_roc_auc": round(float(equal_eval[2]), 6),
        "recommend_change": bool(selected_eval[0] < equal_eval[0] - 0.01 and selected_eval[1] < equal_eval[1]),
        "random_state": int(random_state),
    }
    return search, summary


def spatial_block_recovery_validation(
    occurrences: pd.DataFrame,
    candidate_builder: Callable[[pd.DataFrame], pd.DataFrame],
    *,
    latitude_col: str = "latitude",
    longitude_col: str = "longitude",
    block_degrees: float = 0.25,
    repeats: int = 10,
    holdout_fraction: float = 0.20,
    top_k: int = 10,
    hit_radius_km: float = 5.0,
    random_draws: int = 100,
    random_state: int = 42,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Test whether distance-excluded candidate evidence recovers held-out occurrences.

    `candidate_builder` receives training occurrences only. It must rebuild local
    environment profiles and optional SDM support without consulting held-out
    coordinates. Known-location candidates and direct occurrence/distance-derived
    score components are removed before ranking. Random controls draw from the
    same candidate pool, controlling for its geographic and access envelope.
    """
    latitude_col, longitude_col = _resolve_occurrence_coordinate_columns(
        occurrences, latitude_col, longitude_col
    )
    work = occurrences.copy()
    work[latitude_col] = pd.to_numeric(work[latitude_col], errors="coerce")
    work[longitude_col] = pd.to_numeric(work[longitude_col], errors="coerce")
    work = work.dropna(subset=[latitude_col, longitude_col]).reset_index(drop=True)
    if len(work) < 4:
        raise ValueError("At least four occurrence records are required for spatial recovery validation.")
    block = max(1e-6, float(block_degrees))
    work["_validation_block"] = (
        np.floor(pd.to_numeric(work[latitude_col], errors="coerce") / block).astype(int).astype(str)
        + ":"
        + np.floor(pd.to_numeric(work[longitude_col], errors="coerce") / block).astype(int).astype(str)
    )
    blocks = work["_validation_block"].drop_duplicates().to_numpy()
    if len(blocks) < 2:
        raise ValueError("Occurrences occupy fewer than two spatial blocks; reduce block_degrees or use leave-one-cluster-out validation.")
    rng = np.random.default_rng(int(random_state))
    rows: list[dict[str, Any]] = []
    n_holdout_blocks = min(len(blocks) - 1, max(1, int(round(len(blocks) * float(holdout_fraction)))))
    for repeat in range(1, max(1, int(repeats)) + 1):
        held_blocks = set(rng.choice(blocks, size=n_holdout_blocks, replace=False).tolist())
        heldout = work[work["_validation_block"].isin(held_blocks)].copy()
        training = work[~work["_validation_block"].isin(held_blocks)].drop(columns="_validation_block").copy()
        candidates = candidate_builder(training)
        if candidates is None or candidates.empty:
            rows.append({"repeat": repeat, "status": "no_candidates", "training_records": len(training), "heldout_records": len(heldout)})
            continue
        candidates = candidates.dropna(subset=["latitude", "longitude"]).copy().reset_index(drop=True)
        candidate_type = candidates.get("candidate_type", pd.Series("", index=candidates.index)).astype(str)
        candidates = candidates[
            ~candidate_type.str.contains("occurrence-supported|known-location|known anchor", case=False, na=False)
        ].reset_index(drop=True)
        scored = integrated_candidate_scores(candidates, exclude_occurrence_derived=True)
        scored = scored.sort_values("integrated_support_score", ascending=False, kind="mergesort").reset_index(drop=True)
        selected = scored.head(min(max(1, int(top_k)), len(scored)))
        if selected.empty:
            rows.append({"repeat": repeat, "status": "no_distance_free_candidates", "training_records": len(training), "heldout_records": len(heldout)})
            continue
        held_coords = heldout[[latitude_col, longitude_col]].to_numpy(dtype=float)
        selected_coords = selected[["latitude", "longitude"]].to_numpy(dtype=float)
        nearest = _nearest_distances_km(selected_coords, held_coords)
        model_recall = float(np.mean(nearest <= float(hit_radius_km)))
        random_recalls = []
        random_medians = []
        random_k = len(selected)
        pool_coords = scored[["latitude", "longitude"]].to_numpy(dtype=float)
        for _ in range(max(1, int(random_draws))):
            indices = rng.choice(len(pool_coords), size=random_k, replace=False)
            random_nearest = _nearest_distances_km(pool_coords[indices], held_coords)
            random_recalls.append(float(np.mean(random_nearest <= float(hit_radius_km))))
            random_medians.append(float(np.median(random_nearest)))
        random_recall = float(np.mean(random_recalls))
        rows.append({
            "repeat": repeat,
            "status": "ok",
            "heldout_blocks": ";".join(sorted(held_blocks)),
            "training_records": int(len(training)),
            "heldout_records": int(len(heldout)),
            "candidate_pool": int(len(scored)),
            "top_k": int(len(selected)),
            "hit_radius_km": float(hit_radius_km),
            "distance_excluded_recall": round(model_recall, 6),
            "random_same_pool_recall": round(random_recall, 6),
            "recall_lift_over_random": round(model_recall - random_recall, 6),
            "median_nearest_candidate_km": round(float(np.median(nearest)), 6),
            "random_median_nearest_km": round(float(np.mean(random_medians)), 6),
        })
    folds = pd.DataFrame(rows)
    valid = folds[folds.get("status", pd.Series(dtype=str)).eq("ok")]
    summary = {
        "validation_design": "repeated random spatial-block holdout; candidate builder receives training records only",
        "distance_excluded_components": "observed support, known-location candidates, survey-gap, environmental novelty, and distance-to-known evidence",
        "valid_repeats": int(len(valid)),
        "mean_distance_excluded_recall": None if valid.empty else round(float(valid["distance_excluded_recall"].mean()), 6),
        "mean_random_same_pool_recall": None if valid.empty else round(float(valid["random_same_pool_recall"].mean()), 6),
        "mean_recall_lift_over_random": None if valid.empty else round(float(valid["recall_lift_over_random"].mean()), 6),
        "random_state": int(random_state),
    }
    return folds, summary


def spatial_block_candidate_benchmark(
    occurrences: pd.DataFrame,
    candidate_builder: Callable[[pd.DataFrame], pd.DataFrame],
    **kwargs: Any,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Return candidate-level evidence and held-out coverage for weight studies.

    This is the auditable counterpart of ``spatial_block_recovery_validation``.
    Each candidate row records the held-out occurrence indices recovered within
    the declared radius, allowing alternative weights to be evaluated without
    rebuilding expensive environmental layers for every weight vector.
    """
    latitude_col = str(kwargs.pop("latitude_col", "latitude"))
    longitude_col = str(kwargs.pop("longitude_col", "longitude"))
    block_degrees = max(1e-6, float(kwargs.pop("block_degrees", 0.25)))
    repeats = max(1, int(kwargs.pop("repeats", 10)))
    holdout_fraction = float(kwargs.pop("holdout_fraction", 0.20))
    top_k = max(1, int(kwargs.pop("top_k", 10)))
    hit_radius_km = float(kwargs.pop("hit_radius_km", 5.0))
    random_draws = max(1, int(kwargs.pop("random_draws", 100)))
    random_state = int(kwargs.pop("random_state", 42))
    if kwargs:
        raise TypeError(f"Unexpected benchmark arguments: {', '.join(sorted(kwargs))}")
    latitude_col, longitude_col = _resolve_occurrence_coordinate_columns(
        occurrences, latitude_col, longitude_col
    )
    work = occurrences.copy().reset_index(drop=True)
    work["_benchmark_occurrence_id"] = np.arange(len(work), dtype=int)
    work[latitude_col] = pd.to_numeric(work[latitude_col], errors="coerce")
    work[longitude_col] = pd.to_numeric(work[longitude_col], errors="coerce")
    work = work.dropna(subset=[latitude_col, longitude_col]).reset_index(drop=True)
    if len(work) < 4:
        raise ValueError("At least four occurrence records are required for spatial recovery validation.")
    work["_validation_block"] = (
        np.floor(work[latitude_col] / block_degrees).astype(int).astype(str)
        + ":" + np.floor(work[longitude_col] / block_degrees).astype(int).astype(str)
    )
    blocks = work["_validation_block"].drop_duplicates().to_numpy()
    if len(blocks) < 2:
        raise ValueError("Occurrences occupy fewer than two spatial blocks; reduce block_degrees or use leave-one-cluster-out validation.")
    rng = np.random.default_rng(random_state)
    n_holdout = min(len(blocks) - 1, max(1, int(round(len(blocks) * holdout_fraction))))
    candidate_rows: list[pd.DataFrame] = []
    fold_rows: list[dict[str, Any]] = []
    for repeat in range(1, repeats + 1):
        held_blocks = set(rng.choice(blocks, size=n_holdout, replace=False).tolist())
        heldout = work[work["_validation_block"].isin(held_blocks)].copy()
        training = work[~work["_validation_block"].isin(held_blocks)].drop(
            columns=["_validation_block", "_benchmark_occurrence_id"]
        )
        candidates = candidate_builder(training.copy())
        if candidates is None or candidates.empty:
            fold_rows.append({"repeat": repeat, "status": "no_candidates", "training_records": len(training), "heldout_records": len(heldout)})
            continue
        candidates = candidates.dropna(subset=["latitude", "longitude"]).copy().reset_index(drop=True)
        candidate_type = candidates.get("candidate_type", pd.Series("", index=candidates.index)).astype(str)
        candidates = candidates[~candidate_type.str.contains(
            "occurrence-supported|known-location|known anchor", case=False, na=False
        )].reset_index(drop=True)
        scored = integrated_candidate_scores(candidates, exclude_occurrence_derived=True)
        if scored.empty:
            fold_rows.append({"repeat": repeat, "status": "no_distance_free_candidates", "training_records": len(training), "heldout_records": len(heldout)})
            continue
        held_coords = heldout[[latitude_col, longitude_col]].to_numpy(float)
        candidate_coords = scored[["latitude", "longitude"]].to_numpy(float)
        lat1 = np.radians(held_coords[:, 0])[:, None]
        lon1 = np.radians(held_coords[:, 1])[:, None]
        lat2 = np.radians(candidate_coords[:, 0])[None, :]
        lon2 = np.radians(candidate_coords[:, 1])[None, :]
        a = np.sin((lat2 - lat1) / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2.0) ** 2
        distances = 2.0 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0))) / 1000.0
        held_ids = heldout["_benchmark_occurrence_id"].astype(str).to_numpy()
        covered = [";".join(held_ids[distances[:, index] <= hit_radius_km]) for index in range(len(scored))]
        scored["repeat"] = repeat
        scored["benchmark_candidate_id"] = np.arange(len(scored), dtype=int)
        scored["covered_heldout_ids"] = covered
        scored["all_heldout_ids"] = ";".join(held_ids)
        scored["heldout_distances_km"] = [
            ";".join(f"{value:.8f}" for value in distances[:, index])
            for index in range(len(scored))
        ]
        scored["nearest_heldout_km"] = distances.min(axis=0)
        candidate_rows.append(scored)
        default_top = scored.nlargest(min(top_k, len(scored)), "integrated_support_score")
        recovered = set(filter(None, ";".join(default_top["covered_heldout_ids"]).split(";")))
        random_recalls = []
        for _ in range(random_draws):
            chosen = rng.choice(len(scored), size=min(top_k, len(scored)), replace=False)
            random_ids = set(filter(None, ";".join(scored.iloc[chosen]["covered_heldout_ids"]).split(";")))
            random_recalls.append(len(random_ids) / len(heldout))
        fold_rows.append({
            "repeat": repeat, "status": "ok", "training_records": len(training),
            "heldout_records": len(heldout), "candidate_pool": len(scored),
            "top_k": min(top_k, len(scored)), "hit_radius_km": hit_radius_km,
            "default_recall": len(recovered) / len(heldout),
            "random_same_pool_recall": float(np.mean(random_recalls)),
        })
    candidates_out = pd.concat(candidate_rows, ignore_index=True) if candidate_rows else pd.DataFrame()
    folds = pd.DataFrame(fold_rows)
    valid = folds[folds.get("status", pd.Series(dtype=str)).eq("ok")]
    summary = {
        "validation_design": "candidate-level repeated spatial-block holdout; training-only rebuilding",
        "valid_repeats": int(len(valid)), "random_state": random_state,
        "mean_default_recall": None if valid.empty else round(float(valid["default_recall"].mean()), 6),
        "mean_random_same_pool_recall": None if valid.empty else round(float(valid["random_same_pool_recall"].mean()), 6),
    }
    return candidates_out, folds, summary


def stratified_random_taxa(
    taxon_summary: pd.DataFrame,
    n_taxa: int,
    *,
    taxon_col: str = "scientific_name",
    count_col: str = "coordinate_records",
    strata: int = 3,
    random_state: int = 42,
) -> pd.DataFrame:
    """Seeded sampling across occurrence-count strata, not merely common taxa."""
    required = {taxon_col, count_col}
    missing = required.difference(taxon_summary.columns)
    if missing:
        raise ValueError(f"Taxon summary is missing: {', '.join(sorted(missing))}")
    work = taxon_summary.dropna(subset=[taxon_col]).copy()
    work[count_col] = pd.to_numeric(work[count_col], errors="coerce")
    work = work.dropna(subset=[count_col]).drop_duplicates(taxon_col).reset_index(drop=True)
    if work.empty or n_taxa < 1:
        return work.iloc[0:0].copy()
    bins = min(max(1, int(strata)), work[count_col].nunique(), len(work))
    work["benchmark_count_stratum"] = pd.qcut(work[count_col].rank(method="first"), bins, labels=False)
    rng = np.random.default_rng(int(random_state))
    order = []
    grouped = {key: group.index.to_numpy() for key, group in work.groupby("benchmark_count_stratum", sort=True)}
    while len(order) < min(int(n_taxa), len(work)):
        progressed = False
        for key in sorted(grouped):
            remaining = np.setdiff1d(grouped[key], np.asarray(order, dtype=int), assume_unique=False)
            if len(remaining):
                order.append(int(rng.choice(remaining)))
                progressed = True
                if len(order) >= min(int(n_taxa), len(work)):
                    break
        if not progressed:
            break
    return work.loc[order].reset_index(drop=True)


def calibrate_candidate_weights(
    benchmark_candidates: pd.DataFrame,
    *,
    taxon_col: str = "benchmark_taxon",
    top_k: int = 10,
    search_draws: int = 500,
    train_fraction: float = 0.70,
    random_state: int = 42,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Tune distance-free weights on taxa and evaluate on unseen taxa.

    The result is a recommendation, never an automatic production-weight edit.
    At least four taxa are required so both calibration and evaluation contain
    multiple taxa. Access and detectability still require prospective field data.
    """
    required = {taxon_col, "repeat", "covered_heldout_ids", "all_heldout_ids"}
    required.update(f"component_{name}_score" for name in CALIBRATABLE_DISTANCE_FREE_COMPONENTS)
    missing = required.difference(benchmark_candidates.columns)
    if missing:
        raise ValueError(f"Benchmark candidates are missing: {', '.join(sorted(missing))}")
    taxa = benchmark_candidates[taxon_col].dropna().astype(str).drop_duplicates().to_numpy()
    if len(taxa) < 4:
        raise ValueError("At least four benchmark taxa are required for taxon-held-out weight calibration.")
    rng = np.random.default_rng(int(random_state))
    shuffled = rng.permutation(taxa)
    n_train = min(len(taxa) - 2, max(2, int(round(len(taxa) * float(train_fraction)))))
    train_taxa = set(shuffled[:n_train])
    eval_taxa = set(shuffled[n_train:])
    defaults = np.array([0.25, 0.15, 0.10, 0.05], dtype=float)
    defaults /= defaults.sum()
    weight_vectors = np.vstack([defaults, rng.dirichlet(np.ones(len(defaults)), size=max(1, int(search_draws)))])

    def score_weights(weights: np.ndarray, selected_taxa: set[str]) -> float:
        recalls = []
        subset = benchmark_candidates[benchmark_candidates[taxon_col].astype(str).isin(selected_taxa)]
        for _, fold in subset.groupby([taxon_col, "repeat"], sort=False):
            values = fold[[f"component_{name}_score" for name in CALIBRATABLE_DISTANCE_FREE_COMPONENTS]].apply(pd.to_numeric, errors="coerce").to_numpy(float)
            available = np.isfinite(values)
            denominator = available @ weights
            scores = np.divide(np.nan_to_num(values) @ weights, denominator, out=np.zeros(len(fold)), where=denominator > 0)
            chosen = np.argsort(-scores, kind="stable")[:min(max(1, int(top_k)), len(fold))]
            all_ids = set(filter(None, str(fold["all_heldout_ids"].iloc[0]).split(";")))
            hit_ids = set(filter(None, ";".join(fold.iloc[chosen]["covered_heldout_ids"].astype(str)).split(";")))
            if all_ids:
                recalls.append(len(hit_ids) / len(all_ids))
        return float(np.mean(recalls)) if recalls else float("nan")

    def random_same_pool_score(selected_taxa: set[str], draws: int = 100) -> float:
        recalls = []
        subset = benchmark_candidates[benchmark_candidates[taxon_col].astype(str).isin(selected_taxa)]
        baseline_rng = np.random.default_rng(int(random_state) + 1_000_003)
        for _, fold in subset.groupby([taxon_col, "repeat"], sort=False):
            all_ids = set(filter(None, str(fold["all_heldout_ids"].iloc[0]).split(";")))
            if not all_ids:
                continue
            k = min(max(1, int(top_k)), len(fold))
            fold_recalls = []
            for _ in range(max(1, int(draws))):
                chosen = baseline_rng.choice(len(fold), size=k, replace=False)
                hit_ids = set(filter(None, ";".join(fold.iloc[chosen]["covered_heldout_ids"].astype(str)).split(";")))
                fold_recalls.append(len(hit_ids) / len(all_ids))
            recalls.append(float(np.mean(fold_recalls)))
        return float(np.mean(recalls)) if recalls else float("nan")

    rows = []
    for index, weights in enumerate(weight_vectors):
        rows.append({
            "weight_set": index,
            **{f"weight_{name}": float(value) for name, value in zip(CALIBRATABLE_DISTANCE_FREE_COMPONENTS, weights)},
            "calibration_taxa_recall": score_weights(weights, train_taxa),
            "heldout_taxa_recall": score_weights(weights, eval_taxa),
        })
    search = pd.DataFrame(rows).sort_values("calibration_taxa_recall", ascending=False, kind="mergesort").reset_index(drop=True)
    best = search.iloc[0]
    default = search[search["weight_set"].eq(0)].iloc[0]
    calibration_range = float(search["calibration_taxa_recall"].max() - search["calibration_taxa_recall"].min())
    calibration_informative = bool(np.isfinite(calibration_range) and calibration_range > 1e-9)
    heldout_lift = float(best["heldout_taxa_recall"] - default["heldout_taxa_recall"])
    random_heldout = random_same_pool_score(eval_taxa)
    local_only = score_weights(np.array([1.0, 0.0, 0.0, 0.0]), eval_taxa)
    macro_only = score_weights(np.array([0.0, 1.0, 0.0, 0.0]), eval_taxa)
    summary = {
        "design": "seeded taxon-held-out calibration with within-taxon spatial-block recovery",
        "calibration_taxa": sorted(train_taxa), "heldout_evaluation_taxa": sorted(eval_taxa),
        "selected_weights": {name: round(float(best[f"weight_{name}"]), 6) for name in CALIBRATABLE_DISTANCE_FREE_COMPONENTS},
        "selected_calibration_recall": round(float(best["calibration_taxa_recall"]), 6),
        "selected_heldout_recall": round(float(best["heldout_taxa_recall"]), 6),
        "default_heldout_recall": round(float(default["heldout_taxa_recall"]), 6),
        "heldout_lift_over_default": round(heldout_lift, 6),
        "calibration_informative": calibration_informative,
        "calibration_recall_range": round(calibration_range, 6),
        "random_same_pool_heldout_recall": round(float(random_heldout), 6),
        "local_only_heldout_recall": round(float(local_only), 6),
        "macro_only_heldout_recall": round(float(macro_only), 6),
        "recommend_production_change": bool(
            calibration_informative and len(taxa) >= 10 and heldout_lift > 0.02
            and float(best["heldout_taxa_recall"]) > random_heldout
        ),
        "limitation": "GBIF recovery cannot calibrate accessibility or detectability; confirm those terms with prospective field validation.",
        "random_state": int(random_state),
    }
    return search, summary


def multi_taxon_weight_benchmark(
    taxon_occurrences: dict[str, pd.DataFrame],
    candidate_builder: Callable[[str, pd.DataFrame], pd.DataFrame],
    *,
    benchmark_kwargs: dict[str, Any] | None = None,
    calibration_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one reproducible spatial benchmark across a predeclared taxon sample.

    Taxon sampling should be performed before this call, preferably with
    ``stratified_random_taxa``. Failures are retained in ``taxon_status`` rather
    than silently replacing difficult taxa with convenient successful ones.
    """
    benchmark_options = dict(benchmark_kwargs or {})
    base_seed = int(benchmark_options.pop("random_state", 42))
    candidate_frames: list[pd.DataFrame] = []
    fold_frames: list[pd.DataFrame] = []
    statuses: list[dict[str, Any]] = []
    for taxon_index, (taxon, occurrences) in enumerate(taxon_occurrences.items()):
        try:
            candidates, folds, summary = spatial_block_candidate_benchmark(
                occurrences,
                lambda training, name=str(taxon): candidate_builder(name, training),
                random_state=base_seed + taxon_index,
                **benchmark_options,
            )
            if not candidates.empty:
                candidates["benchmark_taxon"] = str(taxon)
                candidate_frames.append(candidates)
            folds["benchmark_taxon"] = str(taxon)
            fold_frames.append(folds)
            statuses.append({"benchmark_taxon": str(taxon), "status": "ok", **summary})
        except Exception as exc:
            statuses.append({"benchmark_taxon": str(taxon), "status": "failed", "reason": str(exc)})
    all_candidates = pd.concat(candidate_frames, ignore_index=True) if candidate_frames else pd.DataFrame()
    all_folds = pd.concat(fold_frames, ignore_index=True) if fold_frames else pd.DataFrame()
    status = pd.DataFrame(statuses)
    successful_taxa = int(all_candidates.get("benchmark_taxon", pd.Series(dtype=str)).nunique())
    if successful_taxa < 4:
        return {
            "candidate_benchmark": all_candidates, "fold_metrics": all_folds,
            "weight_search": pd.DataFrame(), "taxon_status": status,
            "calibration_summary": {
                "status": "insufficient_taxa",
                "successful_taxa": successful_taxa,
                "required_taxa": 4,
                "recommend_production_change": False,
            },
        }
    search, calibration = calibrate_candidate_weights(
        all_candidates, random_state=base_seed, **dict(calibration_kwargs or {})
    )
    calibration["status"] = "ok" if calibration.get("calibration_informative") else "uninformative"
    calibration["successful_taxa"] = successful_taxa
    calibration["failed_taxa"] = int(status["status"].eq("failed").sum())
    return {
        "candidate_benchmark": all_candidates, "fold_metrics": all_folds,
        "weight_search": search, "taxon_status": status,
        "calibration_summary": calibration,
    }
