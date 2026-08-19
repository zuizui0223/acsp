#!/usr/bin/env python3
"""Development-only inverse learning from the Campanula patch oracle.

2026 field outcomes define an oracle patch set only after the full-island patch
universe and all inference-time features are frozen. A small region-agnostic
logistic model then learns which outcome-blind patch attributes distinguish the
oracle choices. Campanula remains development data; the fitted utility is not a
validation result and must be frozen before any untouched-taxon test.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import campanula_patch_policy as base
import campanula_patch_policy_spatial as spatial
from campanula_patch_policy_fast import cached_prefix, json_safe_oracle
from campanula_worldcover_discovery import haversine_km

SUPPORT_FRACTION = 0.05
FEATURE_COLUMNS = [
    "support",
    "area_cost",
    "survey_gap",
    "prototype_mean",
    "prototype_max",
    "prototype_effective_n",
    "prototype_rarity",
    "nearest_patch_distance_norm",
    "component_patch_count_inv",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--microterrain-universe", type=Path, required=True)
    parser.add_argument("--gbif-prototypes", type=Path, required=True)
    parser.add_argument("--ndvi", type=Path, required=True)
    parser.add_argument("--detections", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def _effective_n(matrix: np.ndarray) -> np.ndarray:
    total = matrix.sum(axis=1, keepdims=True)
    probabilities = np.divide(matrix, total, out=np.zeros_like(matrix), where=total > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        entropy = -np.sum(np.where(probabilities > 0, probabilities * np.log(probabilities), 0.0), axis=1)
    return np.exp(entropy)


def _nearest_patch_distance_norm(zones: pd.DataFrame) -> np.ndarray:
    result = np.zeros(len(zones), dtype=float)
    areas = zones["survey_area_id"].astype(str).to_numpy()
    lat = zones["latitude"].to_numpy(float)
    lon = zones["longitude"].to_numpy(float)
    for area in sorted(set(areas)):
        idx = np.flatnonzero(areas == area)
        if len(idx) <= 1:
            result[idx] = 1.0
            continue
        raw = np.zeros(len(idx), dtype=float)
        for local, pos in enumerate(idx):
            others = idx[idx != pos]
            raw[local] = float(np.min(haversine_km(lat[pos], lon[pos], lat[others], lon[others])))
        scale = max(float(np.quantile(raw, 0.95)), 1e-6)
        result[idx] = np.clip(raw / scale, 0.0, 1.0)
    return result


def build_feature_table(
    zones: pd.DataFrame,
    matrix: np.ndarray,
    support: np.ndarray,
    area_cost: np.ndarray,
    gap: np.ndarray,
) -> pd.DataFrame:
    prevalence = np.maximum(matrix.mean(axis=0), 1e-6)
    rarity = (matrix / prevalence[None, :]).max(axis=1) if matrix.shape[1] else np.zeros(len(zones))
    if np.max(rarity) > 0:
        rarity = rarity / np.max(rarity)
    component_counts = zones["survey_area_id"].astype(str).value_counts().to_dict()
    features = zones[["zone_id", "survey_area_id", "latitude", "longitude"]].copy().reset_index(drop=True)
    features["support"] = support
    features["area_cost"] = area_cost
    features["survey_gap"] = gap
    features["prototype_mean"] = matrix.mean(axis=1) if matrix.shape[1] else 0.0
    features["prototype_max"] = matrix.max(axis=1) if matrix.shape[1] else 0.0
    features["prototype_effective_n"] = _effective_n(matrix)
    features["prototype_rarity"] = rarity
    features["nearest_patch_distance_norm"] = _nearest_patch_distance_norm(zones)
    features["component_patch_count_inv"] = [1.0 / component_counts[str(x)] for x in features["survey_area_id"]]
    return features


def component_first_order(features: pd.DataFrame, score_col: str) -> list[int]:
    """Guarantee one patch per disconnected component, then rank globally."""
    chosen: list[int] = []
    for area, group in features.groupby("survey_area_id", sort=True):
        best = group.sort_values([score_col, "zone_id"], ascending=[False, True], kind="mergesort").index[0]
        chosen.append(int(best))
    remaining = [i for i in features.sort_values([score_col, "zone_id"], ascending=[False, True], kind="mergesort").index if int(i) not in chosen]
    return [*chosen, *map(int, remaining)]


def ranked_zones(zones: pd.DataFrame, features: pd.DataFrame, score_col: str) -> pd.DataFrame:
    order = component_first_order(features, score_col)
    ranked = zones.iloc[order].copy().reset_index(drop=True)
    values = features.loc[order, score_col].to_numpy(float)
    # cached_prefix sorts by zone_score descending, so preserve the chosen order
    # with a tiny deterministic rank term while keeping the learned score auditable.
    ranked["learned_patch_utility"] = values
    ranked["zone_score"] = np.arange(len(ranked), 0, -1, dtype=float)
    ranked["policy_rank"] = np.arange(1, len(ranked) + 1)
    return ranked


def fit_inverse(features: pd.DataFrame, labels: np.ndarray, train_mask: np.ndarray) -> object:
    y = labels[train_mask]
    if len(np.unique(y)) < 2:
        raise ValueError("inverse training fold needs both oracle and non-oracle patches")
    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(C=1.0, class_weight="balanced", max_iter=5000, random_state=20260819),
    )
    model.fit(features.loc[train_mask, FEATURE_COLUMNS], y)
    return model


def main() -> None:
    args = parse_args()
    universe = pd.read_csv(args.microterrain_universe)
    prototypes = pd.read_csv(args.gbif_prototypes)
    with rasterio.open(args.ndvi) as _:
        pass
    universe, prototypes = base.attach_ndvi(universe, prototypes, args.ndvi)
    responsibility, support_rank, proto_rows, kernel_scale = base.environmental_geometry(universe, prototypes)
    _, zones = base.make_zones(universe, support_rank, SUPPORT_FRACTION)
    matrix, support, area_cost, islands = base.patch_responsibilities(zones, responsibility, support_rank)
    gap, _, _, _, _ = spatial.patch_spatial_features(zones, proto_rows)

    # Everything above is outcome-blind. Field outcomes become visible only here.
    detections = pd.read_csv(args.detections)
    oracle = json_safe_oracle(universe, zones, detections, 1.0)
    if oracle is None:
        raise RuntimeError("0.05 support patch universe cannot cover all Campanula development clusters")
    oracle_ids = set(map(str, oracle["selected_zone_ids"]))

    features = build_feature_table(zones, matrix, support, area_cost, gap)
    features["oracle_selected"] = features["zone_id"].astype(str).isin(oracle_ids).astype(int)
    labels = features["oracle_selected"].to_numpy(int)

    # Leave one island/component out: the model never sees oracle labels from the
    # component whose patch utilities it predicts.
    features["crossfit_utility"] = np.nan
    fold_rows = []
    areas = features["survey_area_id"].astype(str).to_numpy()
    for area in sorted(set(areas)):
        test = areas == area
        train = ~test
        model = fit_inverse(features, labels, train)
        features.loc[test, "crossfit_utility"] = model.predict_proba(features.loc[test, FEATURE_COLUMNS])[:, 1]
        fold_rows.append({
            "held_out_component": area,
            "n_train": int(train.sum()),
            "n_test": int(test.sum()),
            "oracle_positive_train": int(labels[train].sum()),
            "oracle_positive_test": int(labels[test].sum()),
        })

    full_model = fit_inverse(features, labels, np.ones(len(features), dtype=bool))
    features["full_fit_utility"] = full_model.predict_proba(features[FEATURE_COLUMNS])[:, 1]

    cross_ranked = ranked_zones(zones, features, "crossfit_utility")
    full_ranked = ranked_zones(zones, features, "full_fit_utility")
    cross_result = cached_prefix(universe, cross_ranked, detections, 1.0)
    full_result = cached_prefix(universe, full_ranked, detections, 1.0)

    classifier = full_model.named_steps["logisticregression"]
    scaler = full_model.named_steps["standardscaler"]
    coefficient_rows = []
    for name, coefficient, mean, scale in zip(
        FEATURE_COLUMNS,
        classifier.coef_[0],
        scaler.mean_,
        scaler.scale_,
    ):
        coefficient_rows.append({
            "feature": name,
            "standardized_coefficient": float(coefficient),
            "training_mean": float(mean),
            "training_scale": float(scale),
        })

    report = {
        "status": "development_only_inverse_patch_learning",
        "species": "Campanula microdonta",
        "support_fraction": SUPPORT_FRACTION,
        "field_coordinates_used_to_construct_features": False,
        "field_outcomes_used_to_define_oracle_labels": True,
        "oracle": oracle,
        "patch_count": int(len(zones)),
        "oracle_patch_count": int(oracle["n_patches"]),
        "crossfit_result": cross_result,
        "full_fit_result": full_result,
        "leave_one_component_out_folds": fold_rows,
        "features": FEATURE_COLUMNS,
        "full_fit_coefficients": coefficient_rows,
        "kernel_scale": float(kernel_scale),
        "claim_boundary": (
            "This is Campanula-guided inverse development. Cross-fitted compression is an internal "
            "development diagnostic, not evidence of cross-taxon generalization."
        ),
    }

    args.out.mkdir(parents=True, exist_ok=True)
    features.to_csv(args.out / "inverse_patch_feature_table.csv", index=False)
    pd.DataFrame(coefficient_rows).to_csv(args.out / "inverse_patch_coefficients.csv", index=False)
    cross_ranked.to_csv(args.out / "crossfit_inverse_patch_order.csv", index=False)
    full_ranked.to_csv(args.out / "full_fit_inverse_patch_order.csv", index=False)
    (args.out / "inverse_patch_learning_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
