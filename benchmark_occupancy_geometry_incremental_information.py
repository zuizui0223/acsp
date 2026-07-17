#!/usr/bin/env python3
"""Assess incremental information in occupancy geometry on the frozen real-taxon cohort.

This is an exploratory, non-winner-gated benchmark.  For each technically informative
random taxon-region pair, it computes full-data conventional summaries and occupancy
geometry from direct CHELSA values.  It then asks whether continuity and gap strength
are redundant with PCA breadth, Gaussian covariance volume, and two-cluster silhouette.

Because the frozen cohort is small, the script reports effect sizes, nearest matched
pairs, and leave-one-pair-out prediction errors rather than declaring significance.
Campanula is intentionally excluded.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge
from sklearn.model_selection import LeaveOneOut
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import benchmark_occupancy_geometry_comparators as comparator
import benchmark_random_taxa_occupancy_geometry_direct as direct
import benchmark_random_taxa_occupancy_geometry_v2 as publication
from acsp.occupancy_geometry import infer_occupancy_geometry
from benchmark_general_random_taxa_regions import fetch_occurrences, predeclare_pairs


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", default="benchmark_results/occupancy_geometry_incremental_information")
    p.add_argument("--pairs", type=int, default=12)
    p.add_argument("--records-per-pair", type=int, default=120)
    p.add_argument("--minimum-records", type=int, default=20)
    p.add_argument("--facet-limit", type=int, default=180)
    p.add_argument("--minimum-unique-states", type=int, default=4)
    p.add_argument("--seed", type=int, default=20260731)
    return p


def _safe_spearman(x: pd.Series, y: pd.Series) -> tuple[float, float]:
    result = spearmanr(x.to_numpy(float), y.to_numpy(float))
    return float(result.statistic), float(result.pvalue)


def _loo_predictions(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    predictions = np.full(len(y), np.nan, dtype=float)
    for train, test in LeaveOneOut().split(x):
        model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
        model.fit(x[train], y[train])
        predictions[test] = model.predict(x[test])
    return predictions


def _prediction_summary(frame: pd.DataFrame, target: str, predictors: list[str]) -> dict[str, float]:
    x = frame[predictors].to_numpy(float)
    y = frame[target].to_numpy(float)
    prediction = _loo_predictions(x, y)
    baseline = np.full(len(y), np.mean(y), dtype=float)
    mae = float(np.mean(np.abs(y - prediction)))
    baseline_mae = float(np.mean(np.abs(y - baseline)))
    ss_res = float(np.sum((y - prediction) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    return {
        "loo_mae": mae,
        "mean_baseline_mae": baseline_mae,
        "mae_ratio_to_mean_baseline": mae / max(baseline_mae, 1e-12),
        "loo_q2": 1.0 - ss_res / max(ss_tot, 1e-12),
    }


def _matched_pairs(frame: pd.DataFrame) -> pd.DataFrame:
    conventional = frame[["pca_breadth", "gaussian_log_volume", "kmeans_silhouette"]].to_numpy(float)
    conventional = StandardScaler().fit_transform(conventional)
    rows: list[dict[str, object]] = []
    for i in range(len(frame)):
        distances = np.linalg.norm(conventional - conventional[i], axis=1)
        distances[i] = np.inf
        j = int(np.argmin(distances))
        rows.append({
            "pair_id": int(frame.iloc[i].pair_id),
            "benchmark_taxon": str(frame.iloc[i].benchmark_taxon),
            "matched_pair_id": int(frame.iloc[j].pair_id),
            "matched_taxon": str(frame.iloc[j].benchmark_taxon),
            "conventional_distance": float(distances[j]),
            "continuity_absolute_difference": float(abs(frame.iloc[i].continuity - frame.iloc[j].continuity)),
            "gap_strength_absolute_difference": float(abs(frame.iloc[i].gap_strength - frame.iloc[j].gap_strength)),
            "span_absolute_difference": float(abs(frame.iloc[i].span - frame.iloc[j].span)),
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
    rows: list[dict[str, object]] = []
    for _, row in sample[sample["status"].eq("predeclared")].iterrows():
        pair_id = int(row.pair_id)
        status: dict[str, object] = {
            "pair_id": pair_id,
            "scientific_name": str(row.scientific_name),
            "region_name": str(row.region_name),
        }
        try:
            occurrences = fetch_occurrences(row, int(args.records_per_pair))
            occurrence_points = direct._occurrence_points(occurrences)
            values, _ = direct._sample_complete(occurrence_points)
            diagnostics = publication._state_diagnostics(values)
            if len(values) < 6:
                raise ValueError("insufficient complete direct-CHELSA occurrence environments")
            if diagnostics["unique_environment_states"] < int(args.minimum_unique_states):
                status.update(status="uninformative", reason="too few distinct CHELSA states", **diagnostics)
            else:
                geometry = infer_occupancy_geometry(values)
                rows.append({
                    "pair_id": pair_id,
                    "benchmark_taxon": str(row.scientific_name),
                    "benchmark_region": str(row.region_name),
                    "taxon_group": str(row.taxon_group),
                    "geographic_stratum": str(row.geographic_stratum),
                    "records": int(len(values)),
                    "unique_environment_states": int(diagnostics["unique_environment_states"]),
                    "pca_breadth": comparator._pca_breadth(values),
                    "gaussian_log_volume": comparator._gaussian_log_volume(values),
                    "kmeans_silhouette": comparator._two_cluster_silhouette(values, int(args.seed) + pair_id),
                    "span": float(geometry.span),
                    "continuity": float(geometry.continuity),
                    "gap_strength": float(geometry.gap_strength),
                })
                status.update(status="ok", records=len(values), **diagnostics)
        except Exception as exc:
            status.update(status="failed", reason=str(exc))
        statuses.append(status)
        pd.DataFrame(statuses).to_csv(output / "pair_status.csv", index=False)

    frame = pd.DataFrame(rows)
    frame.to_csv(output / "incremental_pair_metrics.csv", index=False)
    if len(frame) < 6:
        result = {
            "validation_stage": "real_taxon_incremental_information",
            "campanula_used": False,
            "evaluable_pairs": int(len(frame)),
            "exploratory_not_winner_gated": True,
            "error": "fewer than six evaluable pairs",
        }
        (output / "incremental_information_summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result

    conventional = ["pca_breadth", "gaussian_log_volume", "kmeans_silhouette"]
    targets = ["continuity", "gap_strength"]
    correlations: list[dict[str, object]] = []
    for target in targets:
        for predictor in conventional + ["span"]:
            rho, pvalue = _safe_spearman(frame[target], frame[predictor])
            correlations.append({"target": target, "predictor": predictor, "spearman_rho": rho, "p_value_descriptive": pvalue})
    correlation_frame = pd.DataFrame(correlations)
    correlation_frame.to_csv(output / "topology_conventional_correlations.csv", index=False)

    matched = _matched_pairs(frame)
    matched.to_csv(output / "conventional_nearest_matches.csv", index=False)

    prediction = {target: _prediction_summary(frame, target, conventional) for target in targets}
    result = {
        "validation_stage": "real_taxon_incremental_information",
        "campanula_used": False,
        "environment_source": "CHELSA v2.1 30 arc-second COG: bio1, bio4, bio12, bio15",
        "predeclared_pairs": int(sample["status"].eq("predeclared").sum()),
        "evaluable_pairs": int(len(frame)),
        "exploratory_not_winner_gated": True,
        "small_sample_guardrail": "Effect sizes and leave-one-pair-out prediction are reported descriptively; no significance or superiority gate is used.",
        "conventional_predictors": conventional,
        "leave_one_pair_out_prediction": prediction,
        "median_nearest_match_conventional_distance": float(matched.conventional_distance.median()),
        "median_topology_difference_among_nearest_matches": {
            "continuity": float(matched.continuity_absolute_difference.median()),
            "gap_strength": float(matched.gap_strength_absolute_difference.median()),
            "span": float(matched.span_absolute_difference.median()),
        },
        "maximum_absolute_spearman_with_conventional": {
            target: float(correlation_frame[correlation_frame.target.eq(target)].spearman_rho.abs().max())
            for target in targets
        },
        "interpretation": "Topology is incremental when conventional summaries poorly predict it and conventionally matched taxon pairs retain appreciable continuity or gap differences. This benchmark quantifies that evidence without treating the small cohort as definitive.",
        "protocol": vars(args),
    }
    (output / "incremental_information_summary.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    result = run(parser().parse_args())
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if int(result.get("evaluable_pairs", 0)) < 6:
        raise SystemExit("Fewer than six taxon-region pairs were evaluable")
