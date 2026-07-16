#!/usr/bin/env python3
"""Compare environmental occupancy geometry with conventional niche summaries.

The benchmark reuses the frozen direct-CHELSA taxon-region cohort.  It does not
require occupancy geometry to outperform every comparator.  It reports which
quantities are reproducible under occurrence thinning and which distances
separate held-out occurrences from available environments.

Campanula is intentionally excluded.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter
import tracemalloc

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

import benchmark_random_taxa_occupancy_geometry as geometry_benchmark
import benchmark_random_taxa_occupancy_geometry_direct as direct
import benchmark_random_taxa_occupancy_geometry_v2 as publication
from acsp.occupancy_geometry import infer_occupancy_geometry, robust_scale
from benchmark_general_random_taxa_regions import fetch_occurrences, predeclare_pairs


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--output", default="benchmark_results/occupancy_geometry_comparators")
    command.add_argument("--pairs", type=int, default=12)
    command.add_argument("--records-per-pair", type=int, default=120)
    command.add_argument("--minimum-records", type=int, default=20)
    command.add_argument("--facet-limit", type=int, default=180)
    command.add_argument("--repeats", type=int, default=30)
    command.add_argument("--training-fraction", type=float, default=0.70)
    command.add_argument("--random-draws", type=int, default=200)
    command.add_argument("--minimum-unique-states", type=int, default=4)
    command.add_argument("--seed", type=int, default=20260730)
    return command


def _relative_error(value: float, reference: float) -> float:
    return abs(float(value) - float(reference)) / max(abs(float(reference)), 1e-12)


def _scaled_from_reference(reference: np.ndarray, values: np.ndarray) -> np.ndarray:
    median = np.median(reference, axis=0)
    mad = np.median(np.abs(reference - median), axis=0) * 1.4826
    scale = np.where(mad > 0.0, mad, 1.0)
    scaled = (values - median) / scale
    scaled[:, mad == 0.0] = 0.0
    return scaled


def _pca_breadth(values: np.ndarray) -> float:
    scaled = robust_scale(values)
    if len(scaled) < 2:
        return 0.0
    covariance = np.cov(scaled, rowvar=False)
    covariance = np.atleast_2d(covariance)
    return float(np.trace(covariance))


def _gaussian_log_volume(values: np.ndarray) -> float:
    """Regularised covariance log-volume, a stable hypervolume proxy."""
    scaled = robust_scale(values)
    covariance = np.atleast_2d(np.cov(scaled, rowvar=False))
    regularised = covariance + np.eye(covariance.shape[0]) * 1e-6
    sign, logdet = np.linalg.slogdet(regularised)
    return float(logdet) if sign > 0 else float("nan")


def _two_cluster_silhouette(values: np.ndarray, seed: int) -> float:
    scaled = robust_scale(values)
    unique = np.unique(np.round(scaled, 8), axis=0)
    if len(unique) < 3 or len(scaled) < 4:
        return 0.0
    labels = KMeans(n_clusters=2, n_init=10, random_state=seed).fit_predict(scaled)
    if len(np.unique(labels)) < 2:
        return 0.0
    return float(silhouette_score(scaled, labels))


def _distance_lifts(
    training: np.ndarray,
    held: np.ndarray,
    available: np.ndarray,
    *,
    random_draws: int,
    rng: np.random.Generator,
) -> tuple[float, float]:
    train_scaled = _scaled_from_reference(training, training)
    held_scaled = _scaled_from_reference(training, held)
    available_scaled = _scaled_from_reference(training, available)

    centroid = np.mean(train_scaled, axis=0)
    held_centroid = float(np.median(np.linalg.norm(held_scaled - centroid, axis=1)))
    held_nn = float(np.median(np.min(
        np.linalg.norm(held_scaled[:, None, :] - train_scaled[None, :, :], axis=2), axis=1
    )))

    centroid_null: list[float] = []
    nn_null: list[float] = []
    for _ in range(random_draws):
        index = rng.choice(len(available_scaled), size=len(held_scaled), replace=len(available_scaled) < len(held_scaled))
        sample = available_scaled[index]
        centroid_null.append(float(np.median(np.linalg.norm(sample - centroid, axis=1))))
        nn_null.append(float(np.median(np.min(
            np.linalg.norm(sample[:, None, :] - train_scaled[None, :, :], axis=2), axis=1
        ))))
    return float(np.mean(centroid_null) - held_centroid), float(np.mean(nn_null) - held_nn)


def _repeat_comparison(
    values: np.ndarray,
    available: np.ndarray,
    *,
    repeats: int,
    training_fraction: float,
    random_draws: int,
    seed: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    full_geometry = infer_occupancy_geometry(values)
    full_pca = _pca_breadth(values)
    full_volume = _gaussian_log_volume(values)
    full_silhouette = _two_cluster_silhouette(values, seed)
    training_n = min(len(values) - 2, max(4, int(round(len(values) * training_fraction))))
    rows: list[dict[str, float | int]] = []

    for repeat in range(1, repeats + 1):
        training_index = np.sort(rng.choice(len(values), size=training_n, replace=False))
        held_index = np.setdiff1d(np.arange(len(values)), training_index)
        training = values[training_index]
        held = values[held_index]
        inferred = infer_occupancy_geometry(training)
        pca = _pca_breadth(training)
        volume = _gaussian_log_volume(training)
        silhouette = _two_cluster_silhouette(training, seed + repeat)
        centroid_lift, nearest_occurrence_lift = _distance_lifts(
            training, held, available, random_draws=random_draws, rng=rng
        )
        rows.append({
            "repeat": repeat,
            "training_records": len(training),
            "heldout_records": len(held),
            "geometry_span_relative_error": _relative_error(inferred.span, full_geometry.span),
            "geometry_continuity_absolute_error": abs(inferred.continuity - full_geometry.continuity),
            "geometry_gap_relative_error": _relative_error(inferred.gap_strength, full_geometry.gap_strength),
            "pca_breadth_relative_error": _relative_error(pca, full_pca),
            "gaussian_log_volume_absolute_error": abs(volume - full_volume),
            "kmeans_silhouette_absolute_error": abs(silhouette - full_silhouette),
            "centroid_projection_lift": centroid_lift,
            "nearest_occurrence_projection_lift": nearest_occurrence_lift,
        })
    return pd.DataFrame(rows)


def run(args: argparse.Namespace) -> dict[str, object]:
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    sample_path = output / "predeclared_taxon_region_pairs.csv"
    sample = (
        pd.read_csv(sample_path).head(int(args.pairs))
        if sample_path.exists()
        else predeclare_pairs(int(args.pairs), int(args.seed), int(args.facet_limit), int(args.minimum_records))
    )
    sample.to_csv(sample_path, index=False)

    statuses: list[dict[str, object]] = []
    all_repeats: list[pd.DataFrame] = []
    for _, row in sample[sample["status"].eq("predeclared")].iterrows():
        pair_id = int(row.pair_id)
        started = perf_counter()
        tracemalloc.start()
        status: dict[str, object] = {
            "pair_id": pair_id,
            "scientific_name": str(row.scientific_name),
            "region_name": str(row.region_name),
        }
        try:
            occurrences = fetch_occurrences(row, int(args.records_per_pair))
            occurrence_points = direct._occurrence_points(occurrences)
            null_points = direct._null_points(row, occurrences)
            values, _ = direct._sample_complete(occurrence_points)
            available, _ = direct._sample_complete(null_points)
            if len(values) < 6 or len(available) < 10:
                raise ValueError("insufficient complete direct-CHELSA environments")
            diagnostics = publication._state_diagnostics(values)
            if diagnostics["unique_environment_states"] < int(args.minimum_unique_states):
                status.update(status="uninformative", reason="too few distinct CHELSA states", **diagnostics)
            else:
                repeats = _repeat_comparison(
                    values,
                    available,
                    repeats=int(args.repeats),
                    training_fraction=float(args.training_fraction),
                    random_draws=int(args.random_draws),
                    seed=int(args.seed) + pair_id,
                )
                repeats["pair_id"] = pair_id
                repeats["benchmark_taxon"] = str(row.scientific_name)
                repeats["benchmark_region"] = str(row.region_name)
                repeats["taxon_group"] = str(row.taxon_group)
                repeats["geographic_stratum"] = str(row.geographic_stratum)
                all_repeats.append(repeats)
                status.update(status="ok", records=len(values), null_environments=len(available), **diagnostics)
        except Exception as exc:
            status.update(status="failed", reason=str(exc))
        finally:
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            status["runtime_seconds"] = float(perf_counter() - started)
            status["peak_memory_bytes"] = int(peak)
            statuses.append(status)
            pd.DataFrame(statuses).to_csv(output / "pair_status.csv", index=False)

    repeats = pd.concat(all_repeats, ignore_index=True) if all_repeats else pd.DataFrame()
    repeats.to_csv(output / "comparator_repeat_results.csv", index=False)
    summary = pd.DataFrame()
    if not repeats.empty:
        summary = repeats.groupby(
            ["pair_id", "benchmark_taxon", "benchmark_region", "taxon_group", "geographic_stratum"],
            as_index=False,
        ).agg(
            geometry_span_error=("geometry_span_relative_error", "median"),
            geometry_continuity_error=("geometry_continuity_absolute_error", "median"),
            geometry_gap_error=("geometry_gap_relative_error", "median"),
            pca_breadth_error=("pca_breadth_relative_error", "median"),
            gaussian_log_volume_error=("gaussian_log_volume_absolute_error", "median"),
            kmeans_silhouette_error=("kmeans_silhouette_absolute_error", "median"),
            centroid_projection_lift=("centroid_projection_lift", "median"),
            nearest_occurrence_projection_lift=("nearest_occurrence_projection_lift", "median"),
        )
    summary.to_csv(output / "comparator_pair_summary.csv", index=False)

    declared = int(sample["status"].eq("predeclared").sum())
    evaluable = int(len(summary))
    result = {
        "validation_stage": "frozen_direct_chelsa_method_comparison",
        "campanula_used": False,
        "predeclared_pairs": declared,
        "evaluable_pairs": evaluable,
        "completion_fraction": evaluable / max(1, declared),
        "environment_source": "CHELSA v2.1 30 arc-second COG: bio1, bio4, bio12, bio15",
        "comparison_is_descriptive_not_winner_gated": True,
        "median_metrics": {} if summary.empty else {
            column: float(summary[column].median())
            for column in summary.columns
            if column.endswith("_error") or column.endswith("_lift")
        },
        "interpretation_guardrail": (
            "Nearest-occurrence projection is a conventional baseline shared with the current "
            "diagnostic projection. Novelty must rest on reproducible continuity and gap quantities, "
            "not on nearest-neighbour lift alone."
        ),
        "protocol": vars(args),
    }
    (output / "comparator_summary.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    result = run(parser().parse_args())
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if int(result.get("evaluable_pairs", 0)) < 6:
        raise SystemExit("Fewer than six taxon-region pairs were evaluable")
