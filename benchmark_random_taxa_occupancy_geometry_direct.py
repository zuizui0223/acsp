#!/usr/bin/env python3
"""Confirmation benchmark with coordinate-to-environment-cell extraction.

Occurrence coordinates and null environments are evaluated against the same ACSP-generated
environmental reference grid. Each occurrence is retained only when a complete reference cell
lies within the declared maximum distance. Cells used by occurrences are removed from the null.
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
import benchmark_random_taxa_occupancy_geometry_v2 as publication
from acsp.environment_sampling import sample_environment_at_points
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


def _reference_environment(row: pd.Series, occurrences: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    bounds = (float(row.west), float(row.south), float(row.east), float(row.north))
    metadata = _species_metadata(int(row.speciesKey)) or {}
    metadata.setdefault("kingdom", "Plantae" if row.taxon_group == "plant" else "Animalia")
    bundle = build_automatic_discover_bundle(
        str(row.scientific_name),
        occurrences.reset_index(drop=True),
        "random taxa coordinate environment benchmark",
        str(row.region_name),
        taxon_metadata=metadata,
        survey_bounds=bounds,
        survey_features=[rectangle_feature(bounds, str(row.region_name))],
        candidate_generation_only=True,
    )
    reference = bundle["potential_candidates"].copy()
    features = [column for column in FEATURES if column in reference.columns]
    if len(features) < 2:
        raise ValueError("fewer than two environmental features are available")
    required = ["latitude", "longitude", *features]
    for column in required:
        reference[column] = pd.to_numeric(reference[column], errors="coerce")
    reference = reference.dropna(subset=required).drop_duplicates(
        subset=["latitude", "longitude"], keep="first"
    ).reset_index(drop=True)
    if len(reference) < 10:
        raise ValueError("fewer than ten complete environmental reference cells remain")
    return reference, features


def _occurrence_points(occurrences: pd.DataFrame) -> pd.DataFrame:
    coordinates = publication._coordinates(occurrences)
    return pd.DataFrame({"latitude": coordinates[:, 0], "longitude": coordinates[:, 1]})


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
            reference, features = _reference_environment(row, occurrences)
            sample_result = sample_environment_at_points(
                _occurrence_points(occurrences),
                reference,
                features,
                maximum_distance_km=float(args.maximum_direct_match_km),
            )
            if len(sample_result.values) < 6:
                raise ValueError(
                    f"only {len(sample_result.values)} occurrences matched complete environmental "
                    f"cells within {float(args.maximum_direct_match_km):.3f} km"
                )
            null_mask = np.ones(len(reference), dtype=bool)
            null_mask[np.unique(sample_result.matched_reference_indices)] = False
            null_environment = reference.loc[null_mask, features].to_numpy(float)
            if len(null_environment) < 10:
                raise ValueError("fewer than ten occurrence-excluded null environments remain")

            values = sample_result.values
            diagnostics = publication._state_diagnostics(values)
            status.update(
                records=len(values),
                environmental_reference_cells=len(reference),
                occurrence_excluded_null_environments=len(null_environment),
                features=";".join(features),
                median_direct_match_km=float(np.median(sample_result.distances_km)),
                maximum_direct_match_km=float(np.max(sample_result.distances_km)),
                matched_occurrence_fraction=float(len(values) / max(1, len(occurrences))),
                **diagnostics,
            )
            informative = diagnostics["unique_environment_states"] >= int(args.minimum_unique_states)
            if not informative:
                status.update(status="uninformative", reason="too few distinct sampled environmental states")
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
        "validation_stage": "coordinate_environment_cell_confirmation",
        "design": "independent random taxon-region pairs; bounded coordinate-to-cell extraction; occurrence-excluded null",
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
        "caution": "Environmental values are nearest complete ACSP reference cells within a frozen distance bound; extraction distance is reported for every pair.",
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
