#!/usr/bin/env python3
"""Publication-oriented random-taxon validation of occupancy geometry.

This second-stage benchmark excludes taxon-region pairs whose occurrence records
collapse onto too few distinct proxy environments. It reports robust, pair-level
medians rather than allowing one extreme taxon to dominate the evidence.
Campanula is not used.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter
import tracemalloc

import numpy as np
import pandas as pd

import benchmark_random_taxa_occupancy_geometry as legacy
from benchmark_general_random_taxa_regions import fetch_occurrences, predeclare_pairs


def parser() -> argparse.ArgumentParser:
    command = legacy.parser()
    command.description = __doc__
    command.add_argument("--minimum-unique-states", type=int, default=4)
    command.add_argument("--minimum-unique-fraction", type=float, default=0.10)
    return command


def _coordinates(frame: pd.DataFrame) -> np.ndarray:
    for latitude, longitude in (
        ("decimalLatitude", "decimalLongitude"),
        ("latitude", "longitude"),
        ("_latitude", "_longitude"),
        ("lat", "lon"),
    ):
        if latitude in frame.columns and longitude in frame.columns:
            values = frame[[latitude, longitude]].apply(
                pd.to_numeric, errors="coerce"
            ).to_numpy(float)
            if np.isfinite(values).any():
                return values
    raise ValueError(
        "occurrence table lacks usable coordinate columns; available columns: "
        + ", ".join(map(str, frame.columns))
    )


def _state_diagnostics(values: np.ndarray) -> dict[str, float | int]:
    matrix = np.asarray(values, dtype=float)
    if matrix.ndim != 2 or len(matrix) == 0:
        return {"unique_environment_states": 0, "unique_state_fraction": 0.0, "duplicate_state_fraction": 1.0}
    # Scale before rounding so the diagnostic is independent of units.
    median = np.median(matrix, axis=0)
    mad = np.median(np.abs(matrix - median), axis=0) * 1.4826
    scale = np.where(mad > 0, mad, 1.0)
    scaled = (matrix - median) / scale
    scaled[:, mad == 0] = 0.0
    unique = int(len(np.unique(np.round(scaled, 6), axis=0)))
    fraction = float(unique / len(matrix))
    return {
        "unique_environment_states": unique,
        "unique_state_fraction": fraction,
        "duplicate_state_fraction": float(1.0 - fraction),
    }


def run(args: argparse.Namespace) -> dict[str, object]:
    legacy._coordinates = _coordinates
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    sample_path = output / "predeclared_taxon_region_pairs.csv"
    if sample_path.exists():
        sample = pd.read_csv(sample_path).head(int(args.pairs))
    else:
        sample = predeclare_pairs(
            int(args.pairs), int(args.seed), int(args.facet_limit), int(args.minimum_records)
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
            candidates, features = legacy._candidate_environment(row, occurrences)
            values, proxy_km = legacy._occurrence_environment(occurrences, candidates, features)
            diagnostics = _state_diagnostics(values)
            status.update(
                records=len(values),
                candidate_environments=len(candidates),
                features=";".join(features),
                median_occurrence_proxy_km=float(np.median(proxy_km)),
                **diagnostics,
            )
            informative = (
                diagnostics["unique_environment_states"] >= int(args.minimum_unique_states)
                and diagnostics["unique_state_fraction"] >= float(args.minimum_unique_fraction)
            )
            if not informative:
                status.update(
                    status="uninformative",
                    reason="occurrences collapse onto too few distinct proxy environments",
                )
            else:
                repeats = legacy._pair_benchmark(
                    values,
                    candidates[features].to_numpy(float),
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
                repeats.to_csv(output / f"pair_{pair_id:03d}_geometry_repeats.csv", index=False)
                all_repeats.append(repeats)
                status["status"] = "ok"
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
    repeats.to_csv(output / "geometry_repeat_results.csv", index=False)
    pair_summary = pd.DataFrame()
    if not repeats.empty:
        pair_summary = repeats.groupby(
            ["pair_id", "benchmark_taxon", "benchmark_region", "taxon_group", "geographic_stratum"],
            as_index=False,
        ).agg(
            repeats=("repeat", "size"),
            median_span_relative_error=("span_relative_error", "median"),
            median_continuity_absolute_error=("continuity_absolute_error", "median"),
            median_gap_strength_relative_error=("gap_strength_relative_error", "median"),
            component_count_match_rate=("component_count_match", "mean"),
            median_projection_lift_over_random=("projection_lift_over_random", "median"),
            mean_projection_lift_over_random=("projection_lift_over_random", "mean"),
            positive_projection_lift_fraction=(
                "projection_lift_over_random",
                lambda value: float(np.mean(np.asarray(value) > 0)),
            ),
        )
    pair_summary.to_csv(output / "geometry_pair_summary.csv", index=False)

    status_frame = pd.DataFrame(statuses)
    declared = int(sample["status"].eq("predeclared").sum())
    informative = int(status_frame["status"].eq("ok").sum()) if not status_frame.empty else 0
    informative_fraction = informative / max(1, declared)
    median_lift = None if pair_summary.empty else float(pair_summary["median_projection_lift_over_random"].median())
    positive_fraction = None if pair_summary.empty else float(np.mean(pair_summary["median_projection_lift_over_random"] > 0))
    result = {
        "design": "random taxon-region pairs; informative-state filter; repeated thinning; same-pool environmental null",
        "campanula_used": False,
        "predeclared_pairs": declared,
        "informative_pairs": informative,
        "uninformative_pairs": int(status_frame["status"].eq("uninformative").sum()) if not status_frame.empty else 0,
        "failed_pairs": int(status_frame["status"].eq("failed").sum()) if not status_frame.empty else 0,
        "informative_pair_fraction": informative_fraction,
        "median_pair_span_relative_error": None if pair_summary.empty else float(pair_summary["median_span_relative_error"].median()),
        "median_pair_continuity_absolute_error": None if pair_summary.empty else float(pair_summary["median_continuity_absolute_error"].median()),
        "median_pair_gap_strength_relative_error": None if pair_summary.empty else float(pair_summary["median_gap_strength_relative_error"].median()),
        "median_pair_projection_lift_over_random": median_lift,
        "positive_pair_fraction_projection_lift": positive_fraction,
        "diagnostic_mean_component_count_match_rate": None if pair_summary.empty else float(pair_summary["component_count_match_rate"].mean()),
        "publication_gate": {
            "minimum_informative_pair_fraction": 0.75,
            "maximum_median_span_relative_error": 0.25,
            "maximum_median_continuity_absolute_error": 0.15,
            "maximum_median_gap_strength_relative_error": 0.35,
            "median_projection_lift_must_be_positive": True,
            "minimum_positive_pair_fraction_projection_lift": 0.60,
        },
        "passes_publication_development_gate": bool(
            informative_fraction >= 0.75
            and not pair_summary.empty
            and pair_summary["median_span_relative_error"].median() <= 0.25
            and pair_summary["median_continuity_absolute_error"].median() <= 0.15
            and pair_summary["median_gap_strength_relative_error"].median() <= 0.35
            and float(pair_summary["median_projection_lift_over_random"].median()) > 0
            and float(np.mean(pair_summary["median_projection_lift_over_random"] > 0)) >= 0.60
        ),
        "protocol": vars(args),
        "caution": (
            "Occurrence environments are still nearest-candidate proxies. The next confirmation cohort "
            "must use direct environmental extraction at occurrence coordinates and frozen thresholds."
        ),
    }
    (output / "occupancy_geometry_benchmark_summary.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    print(json.dumps(run(parser().parse_args()), indent=2, ensure_ascii=False))
