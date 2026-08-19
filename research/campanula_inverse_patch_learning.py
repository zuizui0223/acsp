#!/usr/bin/env python3
"""Development-only inverse learning from the Campanula patch-cover family.

All inference-time patch features are frozen before the 2026 field outcomes are
opened. Field outcomes are then used only to characterize the *family* of
minimum set covers, not one arbitrary MILP solution. A patch is:

- ``oracle_compatible`` when it can occur in at least one minimum-size cover;
- ``oracle_necessary`` when excluding it forces a larger minimum cover.

The learned utility targets oracle compatibility using only outcome-blind,
region-agnostic patch attributes. Campanula remains development data; any
resulting rule must be frozen before untouched-taxon evaluation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from scipy.optimize import Bounds, LinearConstraint, milp
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import campanula_patch_policy as base
import campanula_patch_policy_spatial as spatial
from campanula_patch_policy_fast import cached_prefix
from campanula_persistent_patch_hash import _zone_coverage_masks
from campanula_worldcover_discovery import haversine_km

SUPPORT_FRACTION = 0.05
ORACLE_RADIUS_KM = 1.0
MILP_TIME_LIMIT_SECONDS = 5.0
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
        entropy = -np.sum(
            np.where(probabilities > 0, probabilities * np.log(probabilities), 0.0),
            axis=1,
        )
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
            raw[local] = float(
                np.min(haversine_km(lat[pos], lon[pos], lat[others], lon[others]))
            )
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
    rarity = (
        (matrix / prevalence[None, :]).max(axis=1)
        if matrix.shape[1]
        else np.zeros(len(zones))
    )
    if len(rarity) and np.max(rarity) > 0:
        rarity = rarity / np.max(rarity)
    component_counts = zones["survey_area_id"].astype(str).value_counts().to_dict()
    features = zones[
        ["zone_id", "survey_area_id", "latitude", "longitude"]
    ].copy().reset_index(drop=True)
    features["support"] = support
    features["area_cost"] = area_cost
    features["survey_gap"] = gap
    features["prototype_mean"] = matrix.mean(axis=1) if matrix.shape[1] else 0.0
    features["prototype_max"] = matrix.max(axis=1) if matrix.shape[1] else 0.0
    features["prototype_effective_n"] = _effective_n(matrix)
    features["prototype_rarity"] = rarity
    features["nearest_patch_distance_norm"] = _nearest_patch_distance_norm(zones)
    features["component_patch_count_inv"] = [
        1.0 / component_counts[str(x)] for x in features["survey_area_id"]
    ]
    return features


def coverage_matrix_for_oracle(
    universe: pd.DataFrame,
    zones: pd.DataFrame,
    detections: pd.DataFrame,
    radius_km: float,
) -> np.ndarray:
    detection_rows, masks, _ = _zone_coverage_masks(
        universe, zones.reset_index(drop=True), detections, radius_km
    )
    coverage = np.zeros((len(detection_rows), len(zones)), dtype=float)
    for zone_index, raw_mask in enumerate(masks):
        mask = int(raw_mask)
        for detection_index in range(len(detection_rows)):
            coverage[detection_index, zone_index] = float(
                bool(mask & (1 << detection_index))
            )
    if np.any(coverage.sum(axis=1) == 0):
        raise RuntimeError("patch universe leaves at least one development cluster uncovered")
    return coverage


def solve_minimum_cover(
    coverage: np.ndarray,
    *,
    forced_in: int | None = None,
    forced_out: int | None = None,
    time_limit: float = MILP_TIME_LIMIT_SECONDS,
) -> tuple[int, np.ndarray] | None:
    """Solve binary minimum set cover with optional one-patch forcing."""
    n_patches = int(coverage.shape[1])
    lower = np.zeros(n_patches, dtype=float)
    upper = np.ones(n_patches, dtype=float)
    if forced_in is not None:
        lower[int(forced_in)] = 1.0
    if forced_out is not None:
        upper[int(forced_out)] = 0.0
    result = milp(
        c=np.ones(n_patches, dtype=float),
        integrality=np.ones(n_patches, dtype=int),
        bounds=Bounds(lower, upper),
        constraints=LinearConstraint(
            coverage,
            lb=np.ones(coverage.shape[0]),
            ub=np.full(coverage.shape[0], np.inf),
        ),
        options={"time_limit": float(time_limit)},
    )
    if not result.success or result.x is None:
        return None
    selected = np.flatnonzero(result.x > 0.5)
    return int(len(selected)), selected


def characterize_minimum_cover_family(
    coverage: np.ndarray,
    *,
    time_limit: float = MILP_TIME_LIMIT_SECONDS,
) -> dict[str, object]:
    """Classify patches against all minimum-size covers without solution-pool bias."""
    baseline = solve_minimum_cover(coverage, time_limit=time_limit)
    if baseline is None:
        raise RuntimeError("minimum patch cover could not be solved")
    minimum_size, baseline_indices = baseline
    compatible = np.zeros(coverage.shape[1], dtype=bool)
    necessary = np.zeros(coverage.shape[1], dtype=bool)
    unresolved_in: list[int] = []
    unresolved_out: list[int] = []

    for patch_index in range(coverage.shape[1]):
        forced = solve_minimum_cover(
            coverage, forced_in=patch_index, time_limit=time_limit
        )
        if forced is None:
            unresolved_in.append(int(patch_index))
        else:
            compatible[patch_index] = int(forced[0]) == minimum_size

        excluded = solve_minimum_cover(
            coverage, forced_out=patch_index, time_limit=time_limit
        )
        if excluded is None:
            # If the solver proves no feasible cover under exclusion, the patch
            # is certainly necessary; a timeout is kept unresolved below.
            unresolved_out.append(int(patch_index))
        else:
            necessary[patch_index] = int(excluded[0]) > minimum_size

    # Every patch in the baseline minimum solution is compatible even if a
    # forced-in re-solve timed out. Do not infer necessity from timeouts.
    compatible[baseline_indices] = True
    return {
        "minimum_size": int(minimum_size),
        "baseline_indices": baseline_indices,
        "compatible": compatible,
        "necessary": necessary,
        "unresolved_forced_in": unresolved_in,
        "unresolved_forced_out": unresolved_out,
    }


def component_first_order(features: pd.DataFrame, score_col: str) -> list[int]:
    """Guarantee one patch per disconnected component, then rank globally."""
    chosen: list[int] = []
    for _, group in features.groupby("survey_area_id", sort=True):
        best = group.sort_values(
            [score_col, "zone_id"],
            ascending=[False, True],
            kind="mergesort",
        ).index[0]
        chosen.append(int(best))
    remaining = [
        i
        for i in features.sort_values(
            [score_col, "zone_id"],
            ascending=[False, True],
            kind="mergesort",
        ).index
        if int(i) not in chosen
    ]
    return [*chosen, *map(int, remaining)]


def ranked_zones(
    zones: pd.DataFrame, features: pd.DataFrame, score_col: str
) -> pd.DataFrame:
    order = component_first_order(features, score_col)
    ranked = zones.iloc[order].copy().reset_index(drop=True)
    values = features.loc[order, score_col].to_numpy(float)
    ranked["learned_patch_utility"] = values
    ranked["zone_score"] = np.arange(len(ranked), 0, -1, dtype=float)
    ranked["policy_rank"] = np.arange(1, len(ranked) + 1)
    return ranked


def fit_inverse(
    features: pd.DataFrame, labels: np.ndarray, train_mask: np.ndarray
) -> object:
    y = labels[train_mask]
    if len(np.unique(y)) < 2:
        raise ValueError("inverse training fold needs both compatible and incompatible patches")
    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(
            C=1.0,
            class_weight="balanced",
            max_iter=5000,
            random_state=20260819,
        ),
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
    responsibility, support_rank, proto_rows, kernel_scale = base.environmental_geometry(
        universe, prototypes
    )
    _, zones = base.make_zones(universe, support_rank, SUPPORT_FRACTION)
    matrix, support, area_cost, _ = base.patch_responsibilities(
        zones, responsibility, support_rank
    )
    gap, _, _, _, _ = spatial.patch_spatial_features(zones, proto_rows)

    # Everything above is outcome-blind. Field outcomes become visible only here.
    detections = pd.read_csv(args.detections)
    coverage = coverage_matrix_for_oracle(
        universe, zones, detections, ORACLE_RADIUS_KM
    )
    family = characterize_minimum_cover_family(coverage)

    features = build_feature_table(zones, matrix, support, area_cost, gap)
    features["oracle_compatible"] = np.asarray(family["compatible"], dtype=int)
    features["oracle_necessary"] = np.asarray(family["necessary"], dtype=int)
    baseline_indices = np.asarray(family["baseline_indices"], dtype=int)
    features["baseline_oracle_selected"] = 0
    features.loc[baseline_indices, "baseline_oracle_selected"] = 1
    labels = features["oracle_compatible"].to_numpy(int)

    # Leave one island/component out: no oracle labels from the held-out island
    # are used to predict that island's patch utility.
    features["crossfit_utility"] = np.nan
    fold_rows = []
    areas = features["survey_area_id"].astype(str).to_numpy()
    for area in sorted(set(areas)):
        test = areas == area
        train = ~test
        model = fit_inverse(features, labels, train)
        features.loc[test, "crossfit_utility"] = model.predict_proba(
            features.loc[test, FEATURE_COLUMNS]
        )[:, 1]
        fold_rows.append(
            {
                "held_out_component": area,
                "n_train": int(train.sum()),
                "n_test": int(test.sum()),
                "compatible_train": int(labels[train].sum()),
                "compatible_test": int(labels[test].sum()),
                "necessary_test": int(features.loc[test, "oracle_necessary"].sum()),
            }
        )

    full_model = fit_inverse(features, labels, np.ones(len(features), dtype=bool))
    features["full_fit_utility"] = full_model.predict_proba(
        features[FEATURE_COLUMNS]
    )[:, 1]

    cross_ranked = ranked_zones(zones, features, "crossfit_utility")
    full_ranked = ranked_zones(zones, features, "full_fit_utility")
    cross_result = cached_prefix(universe, cross_ranked, detections, ORACLE_RADIUS_KM)
    full_result = cached_prefix(universe, full_ranked, detections, ORACLE_RADIUS_KM)

    classifier = full_model.named_steps["logisticregression"]
    scaler = full_model.named_steps["standardscaler"]
    coefficient_rows = []
    for name, coefficient, mean, scale in zip(
        FEATURE_COLUMNS,
        classifier.coef_[0],
        scaler.mean_,
        scaler.scale_,
    ):
        coefficient_rows.append(
            {
                "feature": name,
                "standardized_coefficient": float(coefficient),
                "training_mean": float(mean),
                "training_scale": float(scale),
            }
        )

    baseline_zone_ids = zones.iloc[baseline_indices]["zone_id"].astype(str).tolist()
    report = {
        "status": "development_only_inverse_patch_learning",
        "species": "Campanula microdonta",
        "support_fraction": SUPPORT_FRACTION,
        "field_coordinates_used_to_construct_features": False,
        "field_outcomes_used_to_define_oracle_labels": True,
        "oracle_label_definition": "membership in any minimum-size patch cover",
        "oracle_minimum_patch_count": int(family["minimum_size"]),
        "baseline_minimum_solution_zone_ids": baseline_zone_ids,
        "oracle_compatible_patch_count": int(features["oracle_compatible"].sum()),
        "oracle_necessary_patch_count": int(features["oracle_necessary"].sum()),
        "oracle_unresolved_forced_in": list(family["unresolved_forced_in"]),
        "oracle_unresolved_forced_out": list(family["unresolved_forced_out"]),
        "patch_count": int(len(zones)),
        "crossfit_result": cross_result,
        "full_fit_result": full_result,
        "leave_one_component_out_folds": fold_rows,
        "features": FEATURE_COLUMNS,
        "full_fit_coefficients": coefficient_rows,
        "kernel_scale": float(kernel_scale),
        "claim_boundary": (
            "Campanula-guided inverse development only. Compatibility labels summarize the family "
            "of minimum field-outcome covers; cross-fit is an internal anti-memorization diagnostic, "
            "not cross-taxon validation."
        ),
    }

    args.out.mkdir(parents=True, exist_ok=True)
    features.to_csv(args.out / "inverse_patch_feature_table.csv", index=False)
    pd.DataFrame(coefficient_rows).to_csv(
        args.out / "inverse_patch_coefficients.csv", index=False
    )
    cross_ranked.to_csv(args.out / "crossfit_inverse_patch_order.csv", index=False)
    full_ranked.to_csv(args.out / "full_fit_inverse_patch_order.csv", index=False)
    (args.out / "inverse_patch_learning_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
