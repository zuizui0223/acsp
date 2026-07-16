#!/usr/bin/env python3
"""Random-taxon validation of environmental occupancy geometry.

The benchmark asks whether geometry inferred from occurrence environments is
reproducible under random thinning and whether held-out occurrence states lie
closer to the retained occupied geometry than arbitrary available environments.
It does not fit an SDM or evaluate survey-site recovery.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter
import tracemalloc

import numpy as np
import pandas as pd

from acsp.occupancy_geometry import infer_occupancy_geometry, project_states
from benchmark_general_random_taxa_regions import (
    _species_metadata,
    fetch_occurrences,
    predeclare_pairs,
    rectangle_feature,
)
from gbif_fieldmap_builder_app import build_automatic_discover_bundle

FEATURES = ("elevation", "slope", "roughness", "tpi", "distance_to_coast_m")
EARTH_RADIUS_KM = 6371.0088


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--output", default="benchmark_results/random_taxa_occupancy_geometry")
    command.add_argument("--pairs", type=int, default=8)
    command.add_argument("--records-per-pair", type=int, default=120)
    command.add_argument("--minimum-records", type=int, default=20)
    command.add_argument("--facet-limit", type=int, default=120)
    command.add_argument("--repeats", type=int, default=30)
    command.add_argument("--training-fraction", type=float, default=0.70)
    command.add_argument("--random-draws", type=int, default=100)
    command.add_argument("--seed", type=int, default=20260716)
    return command


def _coordinates(frame: pd.DataFrame) -> np.ndarray:
    for latitude, longitude in (("decimalLatitude", "decimalLongitude"), ("latitude", "longitude")):
        if latitude in frame.columns and longitude in frame.columns:
            return frame[[latitude, longitude]].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    raise ValueError("occurrence table lacks coordinate columns")


def _distance_matrix_km(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    first_lat = np.radians(first[:, 0])[:, None]
    first_lon = np.radians(first[:, 1])[:, None]
    second_lat = np.radians(second[:, 0])[None, :]
    second_lon = np.radians(second[:, 1])[None, :]
    delta_lat = second_lat - first_lat
    delta_lon = second_lon - first_lon
    value = (
        np.sin(delta_lat / 2.0) ** 2
        + np.cos(first_lat) * np.cos(second_lat) * np.sin(delta_lon / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(value, 0.0, 1.0)))


def _candidate_environment(row: pd.Series, occurrences: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    bounds = (float(row.west), float(row.south), float(row.east), float(row.north))
    metadata = _species_metadata(int(row.speciesKey)) or {}
    metadata.setdefault("kingdom", "Plantae" if row.taxon_group == "plant" else "Animalia")
    bundle = build_automatic_discover_bundle(
        str(row.scientific_name),
        occurrences.reset_index(drop=True),
        "random taxa occupancy-geometry benchmark",
        str(row.region_name),
        taxon_metadata=metadata,
        survey_bounds=bounds,
        survey_features=[rectangle_feature(bounds, str(row.region_name))],
        candidate_generation_only=True,
    )
    candidates = bundle["potential_candidates"].copy()
    candidate_type = candidates.get("candidate_type", pd.Series("", index=candidates.index)).astype(str)
    candidates = candidates[
        ~candidate_type.str.contains("occurrence-supported|known-location|known anchor", case=False, na=False)
    ].copy()
    features = [column for column in FEATURES if column in candidates.columns]
    if len(features) < 2:
        raise ValueError("fewer than two environmental features are available")
    for column in features:
        candidates[column] = pd.to_numeric(candidates[column], errors="coerce")
    candidates["latitude"] = pd.to_numeric(candidates["latitude"], errors="coerce")
    candidates["longitude"] = pd.to_numeric(candidates["longitude"], errors="coerce")
    candidates = candidates.dropna(subset=features + ["latitude", "longitude"]).reset_index(drop=True)
    if len(candidates) < 10:
        raise ValueError("fewer than ten complete candidate environments remain")
    return candidates, features


def _occurrence_environment(occurrences: pd.DataFrame, candidates: pd.DataFrame, features: list[str]) -> tuple[np.ndarray, np.ndarray]:
    coordinates = _coordinates(occurrences)
    finite = np.isfinite(coordinates).all(axis=1)
    coordinates = coordinates[finite]
    if len(coordinates) < 6:
        raise ValueError("fewer than six finite occurrence coordinates remain")
    candidate_coordinates = candidates[["latitude", "longitude"]].to_numpy(float)
    distances = _distance_matrix_km(coordinates, candidate_coordinates)
    nearest = np.argmin(distances, axis=1)
    return candidates.iloc[nearest][features].to_numpy(float), distances[np.arange(len(nearest)), nearest]


def _relative_error(value: float, reference: float) -> float:
    return abs(float(value) - float(reference)) / max(abs(float(reference)), 1e-12)


def _pair_benchmark(
    values: np.ndarray,
    available: np.ndarray,
    *,
    repeats: int,
    training_fraction: float,
    random_draws: int,
    seed: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    full = infer_occupancy_geometry(values)
    rows: list[dict[str, object]] = []
    training_n = min(len(values) - 2, max(4, int(round(len(values) * training_fraction))))
    for repeat in range(1, repeats + 1):
        training_index = np.sort(rng.choice(len(values), size=training_n, replace=False))
        held_index = np.setdiff1d(np.arange(len(values)), training_index)
        training = values[training_index]
        held = values[held_index]
        geometry = infer_occupancy_geometry(training)
        held_distance, held_component = project_states(training, held, geometry)

        random_medians = []
        for _ in range(random_draws):
            random_index = rng.choice(len(available), size=len(held), replace=len(available) < len(held))
            random_distance, _ = project_states(training, available[random_index], geometry)
            random_medians.append(float(np.median(random_distance)))
        random_median = float(np.mean(random_medians))
        held_median = float(np.median(held_distance))
        rows.append(
            {
                "repeat": repeat,
                "training_records": len(training),
                "heldout_records": len(held),
                "span_relative_error": _relative_error(geometry.span, full.span),
                "continuity_absolute_error": abs(geometry.continuity - full.continuity),
                "gap_strength_relative_error": _relative_error(geometry.gap_strength, full.gap_strength),
                "component_count_match": int(geometry.component_count == full.component_count),
                "training_component_count": geometry.component_count,
                "full_component_count": full.component_count,
                "heldout_median_projection_distance": held_median,
                "random_available_median_projection_distance": random_median,
                "projection_lift_over_random": random_median - held_median,
                "heldout_components_represented": int(len(np.unique(held_component))),
            }
        )
    return pd.DataFrame(rows)


def run(args: argparse.Namespace) -> dict[str, object]:
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
            candidates, features = _candidate_environment(row, occurrences)
            values, proxy_km = _occurrence_environment(occurrences, candidates, features)
            repeats = _pair_benchmark(
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
            status.update(
                status="ok",
                records=len(values),
                candidate_environments=len(candidates),
                features=";".join(features),
                median_occurrence_proxy_km=float(np.median(proxy_km)),
            )
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
            mean_projection_lift_over_random=("projection_lift_over_random", "mean"),
            positive_projection_lift_fraction=("projection_lift_over_random", lambda value: float(np.mean(np.asarray(value) > 0))),
        )
    pair_summary.to_csv(output / "geometry_pair_summary.csv", index=False)

    declared = int(sample["status"].eq("predeclared").sum())
    evaluable = int(len(pair_summary))
    completion = evaluable / max(1, declared)
    result = {
        "design": "random taxon-region pairs; repeated random occurrence thinning; same-pool environmental null",
        "campanula_used": False,
        "predeclared_pairs": declared,
        "evaluable_pairs": evaluable,
        "completion_rate": completion,
        "median_pair_span_relative_error": None if pair_summary.empty else float(pair_summary["median_span_relative_error"].median()),
        "median_pair_continuity_absolute_error": None if pair_summary.empty else float(pair_summary["median_continuity_absolute_error"].median()),
        "median_pair_gap_strength_relative_error": None if pair_summary.empty else float(pair_summary["median_gap_strength_relative_error"].median()),
        "mean_component_count_match_rate": None if pair_summary.empty else float(pair_summary["component_count_match_rate"].mean()),
        "mean_projection_lift_over_random": None if pair_summary.empty else float(pair_summary["mean_projection_lift_over_random"].mean()),
        "positive_pair_fraction_projection_lift": None if pair_summary.empty else float(np.mean(pair_summary["mean_projection_lift_over_random"] > 0)),
        "initial_gate": {
            "minimum_completion_rate": 0.75,
            "maximum_median_span_relative_error": 0.25,
            "maximum_median_continuity_absolute_error": 0.15,
            "minimum_component_count_match_rate": 0.60,
            "projection_lift_over_random_must_be_positive": True,
        },
        "passes_initial_gate": bool(
            completion >= 0.75
            and not pair_summary.empty
            and pair_summary["median_span_relative_error"].median() <= 0.25
            and pair_summary["median_continuity_absolute_error"].median() <= 0.15
            and pair_summary["component_count_match_rate"].mean() >= 0.60
            and pair_summary["mean_projection_lift_over_random"].mean() > 0
        ),
        "protocol": vars(args),
        "caution": (
            "Occurrence environments are approximated by nearest complete candidate environments. "
            "This is a development stability test, not independent proof of ecological novelty."
        ),
    }
    (output / "occupancy_geometry_benchmark_summary.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    print(json.dumps(run(parser().parse_args()), indent=2, ensure_ascii=False))
