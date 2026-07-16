#!/usr/bin/env python3
"""Confirmation benchmark using occurrence-supported environmental rows.

The candidate-generation bundle already computes environmental features for known
occurrence-supported rows. This benchmark uses those rows to describe occurrence
environments and reserves occurrence-excluded candidates only for the available-
environment null. Campanula is not used.
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
import benchmark_random_taxa_occupancy_geometry_v2 as publication
from benchmark_general_random_taxa_regions import (
    _species_metadata,
    fetch_occurrences,
    predeclare_pairs,
    rectangle_feature,
)
from gbif_fieldmap_builder_app import build_automatic_discover_bundle

FEATURES = legacy.FEATURES


def parser() -> argparse.ArgumentParser:
    command = publication.parser()
    command.description = __doc__
    command.set_defaults(
        output="benchmark_results/random_taxa_occupancy_geometry_direct",
        pairs=12,
        seed=20260730,
        minimum_unique_fraction=0.0,
    )
    command.add_argument("--maximum-direct-match-km", type=float, default=1.0)
    return command


def _environment_tables(row: pd.Series, occurrences: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    bounds = (float(row.west), float(row.south), float(row.east), float(row.north))
    metadata = _species_metadata(int(row.speciesKey)) or {}
    metadata.setdefault("kingdom", "Plantae" if row.taxon_group == "plant" else "Animalia")
    bundle = build_automatic_discover_bundle(
        str(row.scientific_name),
        occurrences.reset_index(drop=True),
        "random taxa direct occupancy-geometry benchmark",
        str(row.region_name),
        taxon_metadata=metadata,
        survey_bounds=bounds,
        survey_features=[rectangle_feature(bounds, str(row.region_name))],
        candidate_generation_only=True,
    )
    candidates = bundle["potential_candidates"].copy()
    features = [column for column in FEATURES if column in candidates.columns]
    if len(features) < 2:
        raise ValueError("fewer than two environmental features are available")
    required = features + ["latitude", "longitude"]
    for column in required:
        candidates[column] = pd.to_numeric(candidates[column], errors="coerce")
    candidates = candidates.dropna(subset=required).reset_index(drop=True)
    candidate_type = candidates.get("candidate_type", pd.Series("", index=candidates.index)).astype(str)
    known_mask = candidate_type.str.contains(
        "occurrence-supported|known-location|known anchor", case=False, na=False
    )
    known = candidates.loc[known_mask].copy().reset_index(drop=True)
    available = candidates.loc[~known_mask].copy().reset_index(drop=True)
    if len(known) < 4:
        raise ValueError("fewer than four occurrence-supported environmental rows remain")
    if len(available) < 10:
        raise ValueError("fewer than ten occurrence-excluded available environments remain")
    return known, available, features


def _direct_occurrence_environment(
    occurrences: pd.DataFrame,
    known: pd.DataFrame,
    features: list[str],
    maximum_direct_match_km: float,
) -> tuple[np.ndarray, np.ndarray]:
    coordinates = publication._coordinates(occurrences)
    finite = np.isfinite(coordinates).all(axis=1)
    coordinates = coordinates[finite]
    known_coordinates = known[["latitude", "longitude"]].to_numpy(float)
    distances = legacy._distance_matrix_km(coordinates, known_coordinates)
    nearest = np.argmin(distances, axis=1)
    nearest_km = distances[np.arange(len(nearest)), nearest]
    matched = nearest_km <= float(maximum_direct_match_km)
    if int(matched.sum()) < 6:
        raise ValueError(
            f"only {int(matched.sum())} occurrences have occurrence-supported environments "
            f"within {float(maximum_direct_match_km):.3f} km"
        )
    return known.iloc[nearest[matched]][features].to_numpy(float), nearest_km[matched]


def run(args: argparse.Namespace) -> dict[str, object]:
    legacy._coordinates = publication._coordinates
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
            known, available, features = _environment_tables(row, occurrences)
            values, direct_km = _direct_occurrence_environment(
                occurrences, known, features, float(args.maximum_direct_match_km)
            )
            diagnostics = publication._state_diagnostics(values)
            status.update(
                records=len(values),
                occurrence_supported_environments=len(known),
                available_environments=len(available),
                features=";".join(features),
                median_direct_match_km=float(np.median(direct_km)),
                maximum_direct_match_km=float(np.max(direct_km)),
                **diagnostics,
            )
            informative = diagnostics["unique_environment_states"] >= int(args.minimum_unique_states)
            if not informative:
                status.update(status="uninformative", reason="too few distinct direct environmental states")
            else:
                repeats = legacy._pair_benchmark(
                    values,
                    available[features].to_numpy(float),
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
            median_projection_lift_over_random=("projection_lift_over_random", "median"),
            positive_projection_lift_fraction=(
                "projection_lift_over_random", lambda value: float(np.mean(np.asarray(value) > 0))
            ),
        )
        pair_summary["complete_success"] = (
            (pair_summary["median_span_relative_error"] <= 0.25)
            & (pair_summary["median_continuity_absolute_error"] <= 0.15)
            & (pair_summary["median_gap_strength_relative_error"] <= 0.35)
            & (pair_summary["median_projection_lift_over_random"] > 0.0)
        )
    pair_summary.to_csv(output / "geometry_pair_summary.csv", index=False)

    status_frame = pd.DataFrame(statuses)
    declared = int(sample["status"].eq("predeclared").sum())
    informative = int(status_frame["status"].eq("ok").sum()) if not status_frame.empty else 0
    technical = informative + int(status_frame["status"].eq("uninformative").sum()) if not status_frame.empty else 0
    complete_success = None if pair_summary.empty else float(pair_summary["complete_success"].mean())
    result = {
        "validation_stage": "direct_occurrence_environment_confirmation",
        "design": "independent random taxon-region pairs; occurrence-supported environments; occurrence-excluded null",
        "campanula_used": False,
        "predeclared_pairs": declared,
        "technically_eligible_pairs": technical,
        "informative_pairs": informative,
        "technical_eligibility_fraction": technical / max(1, declared),
        "informative_among_eligible": informative / max(1, technical),
        "median_pair_span_relative_error": None if pair_summary.empty else float(pair_summary["median_span_relative_error"].median()),
        "median_pair_continuity_absolute_error": None if pair_summary.empty else float(pair_summary["median_continuity_absolute_error"].median()),
        "median_pair_gap_strength_relative_error": None if pair_summary.empty else float(pair_summary["median_gap_strength_relative_error"].median()),
        "median_pair_projection_lift_over_random": None if pair_summary.empty else float(pair_summary["median_projection_lift_over_random"].median()),
        "positive_pair_fraction_projection_lift": None if pair_summary.empty else float(np.mean(pair_summary["median_projection_lift_over_random"] > 0)),
        "complete_success_fraction": complete_success,
        "passes_direct_confirmation_gate": bool(
            technical / max(1, declared) >= 0.60
            and informative / max(1, technical) >= 0.75
            and not pair_summary.empty
            and pair_summary["median_span_relative_error"].median() <= 0.25
            and pair_summary["median_continuity_absolute_error"].median() <= 0.15
            and pair_summary["median_gap_strength_relative_error"].median() <= 0.35
            and pair_summary["median_projection_lift_over_random"].median() > 0
            and np.mean(pair_summary["median_projection_lift_over_random"] > 0) >= 0.60
            and pair_summary["complete_success"].mean() >= 0.50
        ),
        "protocol": vars(args),
        "caution": "Occurrence-supported rows are generated by the existing ACSP environmental pipeline; exact source rasters remain feature-dependent.",
    }
    (output / "occupancy_geometry_benchmark_summary.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    result = run(parser().parse_args())
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not result.get("passes_direct_confirmation_gate", False):
        raise SystemExit("Direct occurrence-environment confirmation gate failed")
