#!/usr/bin/env python3
"""Benchmark local ecological contrast on the frozen Campanula candidate pool.

Historical occurrence coordinates are mapped to the nearest candidate environment
within the same island because the archived GBIF table does not yet contain
terrain values sampled directly at occurrence coordinates. This approximation is
reported explicitly and never uses 2026 field detections in fitting or selection.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter
import tracemalloc

import numpy as np
import pandas as pd
from sklearn.preprocessing import RobustScaler

from acsp.contrast import (
    candidate_contrasts,
    contrast_membership,
    fit_ecological_contrast,
)
from acsp.field_validation import haversine_distance_m, recovery_summary
from field_validation.campanula_microdonta.run_temporal_external_validation import (
    DEFAULT_RECOVERY_RADII_KM,
    assign_island,
    island_constrained_recovery,
)

FEATURE_COLUMNS = ["elevation", "slope", "roughness", "tpi", "distance_to_coast_m"]
TOP_K = 5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        default="field_validation/campanula_microdonta/temporal_external_results",
    )
    return parser.parse_args()


def finite_feature_frame(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    columns = [column for column in FEATURE_COLUMNS if column in frame.columns]
    if not columns:
        raise RuntimeError("No ecological feature columns were available.")
    result = frame.copy()
    for column in columns:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result = result.dropna(subset=columns).reset_index(drop=True)
    if result.empty:
        raise RuntimeError("No candidate had a complete ecological feature vector.")
    return result, columns


def occurrence_environment_proxies(
    occurrences: pd.DataFrame,
    pool: pd.DataFrame,
    columns: list[str],
) -> pd.DataFrame:
    rows = []
    for occurrence in occurrences.itertuples(index=False):
        latitude = float(getattr(occurrence, "_latitude"))
        longitude = float(getattr(occurrence, "_longitude"))
        area = assign_island(latitude, longitude)
        available = pool[pool["survey_area_id"].astype(str).eq(area)]
        if available.empty:
            continue
        distances = haversine_distance_m(
            latitude,
            longitude,
            available["latitude"].to_numpy(float),
            available["longitude"].to_numpy(float),
        )
        nearest = available.iloc[int(np.argmin(distances))]
        row = {
            "survey_area_id": area,
            "proxy_site_id": str(nearest["site_id"]),
            "occurrence_distance_to_proxy_km": float(np.min(distances) / 1000.0),
        }
        row.update({column: float(nearest[column]) for column in columns})
        rows.append(row)
    proxies = pd.DataFrame(rows)
    if proxies.empty:
        raise RuntimeError("No historical occurrence could be mapped to an island candidate environment.")
    return proxies.drop_duplicates(["survey_area_id", "proxy_site_id"]).reset_index(drop=True)


def area_balanced_best(pool: pd.DataFrame, score: np.ndarray) -> pd.DataFrame:
    ranked = pool.copy()
    ranked["method_score"] = np.asarray(score, dtype=float)
    selected = []
    for area, group in ranked.groupby("survey_area_id", sort=True):
        chosen = group.sort_values(
            ["method_score", "site_id"], ascending=[False, True], kind="mergesort"
        ).iloc[0]
        selected.append(chosen)
    result = pd.DataFrame(selected)
    if len(result) > TOP_K:
        result = result.sort_values(
            ["method_score", "site_id"], ascending=[False, True], kind="mergesort"
        ).head(TOP_K)
    return result.reset_index(drop=True)


def absolute_prototype_score(occupied: np.ndarray, candidates: np.ndarray) -> np.ndarray:
    scaler = RobustScaler(quantile_range=(25.0, 75.0)).fit(occupied)
    occupied_scaled = scaler.transform(occupied)
    candidate_scaled = scaler.transform(candidates)
    delta = candidate_scaled[:, None, :] - occupied_scaled[None, :, :]
    distance2 = np.mean(delta * delta, axis=2)
    membership = np.exp(-0.5 * distance2)
    return membership.mean(axis=1)


def method_summary(name: str, selected: pd.DataFrame, clusters: pd.DataFrame) -> pd.DataFrame:
    recovery = island_constrained_recovery(selected, clusters, DEFAULT_RECOVERY_RADII_KM)
    summary = recovery_summary(recovery, radii_km=DEFAULT_RECOVERY_RADII_KM)
    summary.insert(0, "method", name)
    return summary


def main() -> None:
    args = parse_args()
    root = Path(args.results)
    pool, columns = finite_feature_frame(pd.read_csv(root / "distance_excluded_candidate_pool.csv"))
    occurrences = pd.read_csv(root / "gbif_training_occurrences_through_2025.csv")
    clusters = pd.read_csv(root / "independent_detection_clusters.csv")
    current = pd.read_csv(root / "frozen_acsp_top5.csv")
    proxies = occurrence_environment_proxies(occurrences, pool, columns)

    candidate_matrix = pool[columns].to_numpy(float)
    candidate_groups = pool["survey_area_id"].astype(str).to_numpy()
    occupied_matrix = proxies[columns].to_numpy(float)
    occupied_groups = proxies["survey_area_id"].astype(str).to_numpy()

    tracemalloc.start()
    started = perf_counter()
    operator = fit_ecological_contrast(
        occupied_matrix,
        occupied_groups,
        candidate_matrix,
        candidate_groups,
    )
    contrasts = candidate_contrasts(
        candidate_matrix,
        candidate_groups,
        candidate_matrix,
        candidate_groups,
    )
    memberships = contrast_membership(operator, contrasts)
    contrast_selected = area_balanced_best(pool, memberships.mean(axis=1))
    contrast_seconds = perf_counter() - started
    _, contrast_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    tracemalloc.start()
    started = perf_counter()
    absolute_scores = absolute_prototype_score(occupied_matrix, candidate_matrix)
    absolute_selected = area_balanced_best(pool, absolute_scores)
    absolute_seconds = perf_counter() - started
    _, absolute_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    contrast_selected.to_csv(root / "ecological_contrast_top5.csv", index=False)
    absolute_selected.to_csv(root / "absolute_prototype_area_balanced_top5.csv", index=False)
    proxies.to_csv(root / "historical_occurrence_environment_proxies.csv", index=False)

    comparison = pd.concat(
        [
            method_summary("current_acsp", current, clusters),
            method_summary("absolute_prototype_area_balanced", absolute_selected, clusters),
            method_summary("ecological_contrast", contrast_selected, clusters),
        ],
        ignore_index=True,
    )
    comparison.to_csv(root / "ecological_contrast_comparison.csv", index=False)

    primary = comparison[np.isclose(comparison["radius_km"], 10.0)].copy()
    result = {
        "hypothesis": "occupied states transfer as local empirical contrasts rather than absolute environmental values",
        "field_data_used_in_fit_or_selection": False,
        "feature_columns": columns,
        "candidate_count": int(len(pool)),
        "historical_occurrence_environment_proxies": int(len(proxies)),
        "proxy_environment_caution": (
            "Historical occurrence environments were approximated by the nearest frozen candidate "
            "within the same island because archived occurrence rows lacked sampled terrain values."
        ),
        "operator_group_count": int(len(operator.group_labels)),
        "operator_groups": [str(value) for value in operator.group_labels],
        "median_contrast": operator.median_contrast.tolist(),
        "feature_reliability": operator.feature_reliability.tolist(),
        "primary_10km": primary.to_dict(orient="records"),
        "runtime_seconds": {
            "ecological_contrast": float(contrast_seconds),
            "absolute_prototype": float(absolute_seconds),
        },
        "peak_memory_bytes": {
            "ecological_contrast": int(contrast_peak),
            "absolute_prototype": int(absolute_peak),
        },
        "acceptance_rule": (
            "Do not adopt unless ecological contrast exceeds the area-balanced absolute prototype "
            "and same-quota random selection in cross-taxon leave-one-region-out validation."
        ),
    }
    (root / "ecological_contrast_benchmark_summary.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
