#!/usr/bin/env python3
"""Exploratory Campanula benchmark for occurrence-relation selection.

Selection is frozen from historical occurrences and the candidate pool before
independent 2026 detections are read. This first benchmark uses nearest-candidate
terrain as an occurrence-feature proxy because the historical workflow did not
export terrain values at occurrence coordinates. Results are therefore
hypothesis-generating, not confirmatory.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
import tracemalloc

import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import RobustScaler

from acsp.field_validation import detection_recovery_table, recovery_summary
from acsp.relation_witness import relation_witness_membership
from acsp.relations import infer_occurrence_relation_graph, select_relation_cover

FEATURES = ("elevation", "slope", "aspect_sin", "aspect_cos", "roughness", "tpi", "distance_to_coast_m")
TOP_K = 5
N_NEIGHBORS = 3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        default="field_validation/campanula_microdonta/temporal_external_results",
    )
    return parser.parse_args()


def feature_matrix(candidates: pd.DataFrame) -> np.ndarray:
    frame = candidates.copy()
    aspect = np.deg2rad(pd.to_numeric(frame["aspect"], errors="coerce"))
    frame["aspect_sin"] = np.sin(aspect)
    frame["aspect_cos"] = np.cos(aspect)
    matrix = frame.loc[:, FEATURES].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    medians = np.nanmedian(matrix, axis=0)
    medians = np.where(np.isfinite(medians), medians, 0.0)
    return np.where(np.isfinite(matrix), matrix, medians[None, :])


def occurrence_feature_proxy(
    occurrences: pd.DataFrame,
    candidates: pd.DataFrame,
    candidate_features: np.ndarray,
) -> np.ndarray:
    occurrence_lat = occurrences["_latitude"].to_numpy(float)
    occurrence_lon = occurrences["_longitude"].to_numpy(float)
    candidate_lat = candidates["latitude"].to_numpy(float)
    candidate_lon = candidates["longitude"].to_numpy(float)
    latitude_scale = np.cos(np.deg2rad(occurrence_lat[:, None]))
    squared_km = ((occurrence_lat[:, None] - candidate_lat[None, :]) * 111.0) ** 2
    squared_km += (
        (occurrence_lon[:, None] - candidate_lon[None, :]) * 111.0 * latitude_scale
    ) ** 2
    nearest = np.argmin(squared_km, axis=1)
    proxy = candidate_features[nearest]
    return np.unique(np.round(proxy, decimals=8), axis=0)


def point_prototype_membership(
    occurrence_features: np.ndarray,
    candidate_features: np.ndarray,
) -> np.ndarray:
    scaler = RobustScaler(quantile_range=(25.0, 75.0)).fit(occurrence_features)
    occurrences = scaler.transform(occurrence_features)
    candidates = scaler.transform(candidate_features)
    neighbours = min(N_NEIGHBORS + 1, len(occurrences))
    distances, _ = NearestNeighbors(n_neighbors=neighbours).fit(occurrences).kneighbors(occurrences)
    local_scale = np.median(distances[:, 1:], axis=1)
    positive = local_scale[local_scale > 0]
    replacement = float(np.median(positive)) if positive.size else 1.0
    local_scale = np.where(local_scale > 0, local_scale, replacement)
    distance = np.linalg.norm(candidates[:, None, :] - occurrences[None, :, :], axis=2)
    return np.exp(-0.5 * (distance / local_scale[None, :]) ** 2)


def selected_frame(pool: pd.DataFrame, indices: np.ndarray, method: str) -> pd.DataFrame:
    selected = pool.iloc[indices].copy().reset_index(drop=True)
    selected["selection_method"] = method
    selected["selection_rank"] = np.arange(1, len(selected) + 1)
    return selected


def main() -> None:
    args = parse_args()
    output = Path(args.results)
    occurrences = pd.read_csv(output / "gbif_training_occurrences_through_2025.csv")
    pool = pd.read_csv(output / "distance_excluded_candidate_pool.csv")
    baseline = pd.read_csv(output / "frozen_acsp_top5.csv")

    candidate_features = feature_matrix(pool)
    occurrence_features = occurrence_feature_proxy(occurrences, pool, candidate_features)
    if len(occurrence_features) <= N_NEIGHBORS:
        raise RuntimeError("Too few distinct occurrence feature proxies for relation inference.")

    tracemalloc.start()
    started = time.perf_counter()
    graph = infer_occurrence_relation_graph(occurrence_features, n_neighbors=N_NEIGHBORS)
    relation_matrix = relation_witness_membership(graph, candidate_features)
    relation_indices = select_relation_cover(relation_matrix, n_select=min(TOP_K, len(pool)))
    relation_seconds = time.perf_counter() - started
    _, relation_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    tracemalloc.start()
    started = time.perf_counter()
    prototype_matrix = point_prototype_membership(occurrence_features, candidate_features)
    prototype_indices = select_relation_cover(prototype_matrix, n_select=min(TOP_K, len(pool)))
    prototype_seconds = time.perf_counter() - started
    _, prototype_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    relation = selected_frame(pool, relation_indices, "occurrence_relation_witness")
    prototype = selected_frame(pool, prototype_indices, "point_prototype_cover")
    relation.to_csv(output / "relation_witness_top5.csv", index=False)
    prototype.to_csv(output / "point_prototype_top5.csv", index=False)

    # Independent detections are deliberately read only after both new selections are frozen.
    detections = pd.read_csv(output / "independent_detection_clusters.csv")
    methods = {
        "current_acsp": baseline,
        "point_prototype_cover": prototype,
        "occurrence_relation_witness": relation,
    }
    summaries = []
    for method, selected in methods.items():
        recovered = detection_recovery_table(
            selected,
            detections,
            candidate_id_col="site_id",
            area_col="survey_area_id",
        )
        summary = recovery_summary(recovered)
        summary.insert(0, "method", method)
        summaries.append(summary)
    comparison = pd.concat(summaries, ignore_index=True)
    comparison.to_csv(output / "occurrence_relation_comparison.csv", index=False)

    primary = comparison[np.isclose(comparison["radius_km"], 10.0)].copy()
    result = {
        "status": "exploratory_feature_proxy_benchmark",
        "field_data_used_for_selection": False,
        "n_neighbors_predeclared": N_NEIGHBORS,
        "top_k": TOP_K,
        "occurrence_rows": int(len(occurrences)),
        "distinct_occurrence_feature_proxies": int(len(occurrence_features)),
        "candidate_rows": int(len(pool)),
        "relation_edges": int(len(graph.edges)),
        "feature_columns": list(FEATURES),
        "occurrence_feature_limitation": (
            "Terrain at historical occurrences was approximated by the geographically nearest candidate. "
            "A confirmatory benchmark must extract features directly at occurrence coordinates."
        ),
        "primary_10km": primary.to_dict(orient="records"),
        "runtime_seconds": {
            "occurrence_relation_witness": relation_seconds,
            "point_prototype_cover": prototype_seconds,
        },
        "peak_memory_bytes": {
            "occurrence_relation_witness": int(relation_peak),
            "point_prototype_cover": int(prototype_peak),
        },
    }
    (output / "occurrence_relation_benchmark_summary.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
