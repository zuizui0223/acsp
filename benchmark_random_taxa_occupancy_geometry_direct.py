#!/usr/bin/env python3
"""Frozen confirmation using direct CHELSA extraction at occurrence and null coordinates."""
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
from acsp.chelsa_sampling import DEFAULT_VARIABLES, sample_chelsa_at_coordinates
from benchmark_general_random_taxa_regions import (
    _species_metadata,
    fetch_occurrences,
    predeclare_pairs,
    rectangle_feature,
)
from gbif_fieldmap_builder_app import build_automatic_discover_bundle

FEATURES = tuple(DEFAULT_VARIABLES)


def parser() -> argparse.ArgumentParser:
    command = publication.parser()
    command.description = __doc__
    command.set_defaults(
        output="benchmark_results/random_taxa_occupancy_geometry_direct",
        pairs=12,
        seed=20260730,
        minimum_unique_fraction=0.0,
    )
    # Retained only so old workflow invocations remain compatible.
    command.add_argument("--maximum-direct-match-km", type=float, default=1.0)
    return command


def _occurrence_points(occurrences: pd.DataFrame) -> pd.DataFrame:
    coordinates = publication._coordinates(occurrences)
    return pd.DataFrame({"latitude": coordinates[:, 0], "longitude": coordinates[:, 1]})


def _null_points(row: pd.Series, occurrences: pd.DataFrame) -> pd.DataFrame:
    bounds = (float(row.west), float(row.south), float(row.east), float(row.north))
    metadata = _species_metadata(int(row.speciesKey)) or {}
    metadata.setdefault("kingdom", "Plantae" if row.taxon_group == "plant" else "Animalia")
    bundle = build_automatic_discover_bundle(
        str(row.scientific_name),
        occurrences.reset_index(drop=True),
        "random taxa direct CHELSA benchmark",
        str(row.region_name),
        taxon_metadata=metadata,
        survey_bounds=bounds,
        survey_features=[rectangle_feature(bounds, str(row.region_name))],
        candidate_generation_only=True,
    )
    candidates = bundle.get("potential_candidates", pd.DataFrame()).copy()
    if not {"latitude", "longitude"}.issubset(candidates.columns):
        raise ValueError("candidate generator did not return null coordinates")
    candidates["latitude"] = pd.to_numeric(candidates["latitude"], errors="coerce")
    candidates["longitude"] = pd.to_numeric(candidates["longitude"], errors="coerce")
    candidates = candidates.dropna(subset=["latitude", "longitude"]).drop_duplicates(
        ["latitude", "longitude"]
    )
    if len(candidates) < 10:
        raise ValueError("fewer than ten candidate null coordinates remain")
    return candidates[["latitude", "longitude"]].reset_index(drop=True)


def _sample_complete(points: pd.DataFrame) -> tuple[np.ndarray, pd.DataFrame]:
    sampled = sample_chelsa_at_coordinates(points, variables=FEATURES)
    complete = sampled.frame.iloc[sampled.complete_indices].reset_index(drop=True)
    return complete[list(FEATURES)].to_numpy(float), complete


def run(args: argparse.Namespace) -> dict[str, object]:
    legacy._coordinates = publication._coordinates
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
            occurrence_points = _occurrence_points(occurrences)
            null_points = _null_points(row, occurrences)
            values, occurrence_sample = _sample_complete(occurrence_points)
            null_environment, null_sample = _sample_complete(null_points)
            if len(values) < 6:
                raise ValueError(f"only {len(values)} occurrence coordinates had complete CHELSA values")
            if len(null_environment) < 10:
                raise ValueError(f"only {len(null_environment)} null coordinates had complete CHELSA values")

            diagnostics = publication._state_diagnostics(values)
            status.update(
                records=len(values),
                occurrence_input_coordinates=len(occurrence_points),
                occurrence_complete_fraction=float(len(values) / max(1, len(occurrence_points))),
                null_input_coordinates=len(null_points),
                null_complete_environments=len(null_environment),
                features=";".join(FEATURES),
                environment_source="CHELSA v2.1 30 arc-second COG",
                **diagnostics,
            )
            if diagnostics["unique_environment_states"] < int(args.minimum_unique_states):
                status.update(status="uninformative", reason="too few distinct direct CHELSA states")
            else:
                repeats = legacy._pair_benchmark(
                    values,
                    null_environment,
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
        "validation_stage": "direct_chelsa_coordinate_confirmation",
        "design": "independent random taxon-region pairs; direct CHELSA sampling for occurrences and null coordinates",
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
        "environment_source": "CHELSA v2.1 30 arc-second COG: bio1, bio4, bio12, bio15",
    }
    (output / "occupancy_geometry_benchmark_summary.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    result = run(parser().parse_args())
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not result.get("passes_direct_confirmation_gate", False):
        raise SystemExit("Direct CHELSA confirmation gate failed")
