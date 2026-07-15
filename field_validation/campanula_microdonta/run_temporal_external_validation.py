#!/usr/bin/env python3
"""Run a temporally independent ACSP field validation for Campanula microdonta.

The execution order is deliberately fixed:

1. Fetch Japanese GBIF occurrences dated no later than 2025.
2. Build ACSP candidates without reading the 2026 field detections.
3. Select the prespecified plant Top-5 using local-habitat evidence only.
4. Read and cluster the independent 2026 field GPS records.
5. Compare the frozen Top-5 with same-pool random Top-5 sets.

The field detections are never used for candidate generation, scoring, parameter
selection, or Top-k selection. This is a temporal external validation rather than
a claim that predictions were physically exported before the field campaign.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

from acsp.field_validation import (
    DEFAULT_RECOVERY_RADII_KM,
    cluster_field_detections,
    detection_recovery_table,
    haversine_distance_m,
    recovery_summary,
    stratified_random_recovery_benchmark,
)
from acsp.planning import integrated_candidate_scores, select_complementary_candidates
from gbif_fieldmap_builder_app import (
    build_automatic_discover_bundle,
    clean_occurrences,
    detect_occurrence_columns,
    gbif_record_to_species_row,
)


SCIENTIFIC_NAME = "Campanula microdonta"
COUNTRY_CODE = "JP"
TRAINING_YEAR_MAX = 2025
PRIMARY_TOP_K = 5
PRIMARY_RADIUS_KM = 10.0
DEFAULT_SEED = 20260715
GBIF_MATCH_URL = "https://api.gbif.org/v1/species/match"
GBIF_SEARCH_URL = "https://api.gbif.org/v1/occurrence/search"

# Rectangles define the five surveyed islands. The terrestrial candidate surface
# inside them is still resolved by the existing ACSP land mask.
ISLAND_BOUNDS: dict[str, tuple[float, float, float, float]] = {
    "oshima": (139.30, 34.64, 139.47, 34.82),
    "toshima": (139.24, 34.49, 139.31, 34.55),
    "niijima": (139.20, 34.33, 139.31, 34.44),
    "shikinejima": (139.18, 34.30, 139.24, 34.35),
    "kozushima": (139.09, 34.17, 139.18, 34.26),
}
SURVEY_BOUNDS = (
    min(value[0] for value in ISLAND_BOUNDS.values()),
    min(value[1] for value in ISLAND_BOUNDS.values()),
    max(value[2] for value in ISLAND_BOUNDS.values()),
    max(value[3] for value in ISLAND_BOUNDS.values()),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--locations",
        default=str(Path(__file__).with_name("locations_2026.csv")),
        help="Independent 2026 positive field GPS CSV.",
    )
    parser.add_argument(
        "--output",
        default="field_validation/campanula_microdonta/temporal_external_results",
    )
    parser.add_argument("--gbif-cap", type=int, default=2000)
    parser.add_argument("--random-iterations", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--cluster-radius-m", type=float, default=500.0)
    return parser.parse_args()


def rectangle_feature(name: str, bounds: tuple[float, float, float, float]) -> dict[str, Any]:
    west, south, east, north = bounds
    return {
        "type": "Feature",
        "properties": {"name": name, "survey_area_id": name},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [west, south],
                [east, south],
                [east, north],
                [west, north],
                [west, south],
            ]],
        },
    }


def _request_json(url: str, params: dict[str, Any], *, timeout: int = 90) -> dict[str, Any]:
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def fetch_historical_gbif(cap: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    match = _request_json(GBIF_MATCH_URL, {"name": SCIENTIFIC_NAME}, timeout=30)
    usage_key = match.get("usageKey")
    if usage_key is None:
        raise RuntimeError(f"GBIF did not resolve {SCIENTIFIC_NAME!r}: {match}")

    base = {
        "taxonKey": int(usage_key),
        "country": COUNTRY_CODE,
        "hasCoordinate": "true",
        "hasGeospatialIssue": "false",
        "occurrenceStatus": "PRESENT",
        "year": f"1000,{TRAINING_YEAR_MAX}",
    }
    count_payload = _request_json(GBIF_SEARCH_URL, {**base, "limit": 0, "offset": 0})
    total = int(count_payload.get("count", 0))
    target = min(max(1, int(cap)), total)
    if total < 1:
        raise RuntimeError("GBIF returned no eligible historical coordinate records.")

    page_size = 300
    pages = max(1, int(math.ceil(target / page_size)))
    if total <= target:
        offsets = list(range(0, target, page_size))
        retrieval = "sequential"
    else:
        offsets = sorted(set(np.linspace(0, max(0, total - page_size), pages, dtype=int).tolist()))
        retrieval = "representative_offsets"

    records: list[dict[str, Any]] = []
    for offset in offsets:
        payload = _request_json(
            GBIF_SEARCH_URL,
            {**base, "limit": min(page_size, max(1, target - len(records))), "offset": int(offset)},
        )
        records.extend(payload.get("results", []))
        if len(records) >= target:
            break

    raw = pd.DataFrame([gbif_record_to_species_row(record) for record in records[:target]])
    if raw.empty:
        raise RuntimeError("GBIF retrieval returned no usable rows.")
    occurrences = clean_occurrences(raw, detect_occurrence_columns(raw)).reset_index(drop=True)
    if "year" in occurrences.columns:
        years = pd.to_numeric(occurrences["year"], errors="coerce")
        occurrences = occurrences[years.le(TRAINING_YEAR_MAX)].reset_index(drop=True)
    if len(occurrences) < 4:
        raise RuntimeError(f"Only {len(occurrences)} historical records remained after cleaning.")

    metadata = dict(match)
    metadata.setdefault("kingdom", "Plantae")
    provenance = {
        "query_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scientific_name_requested": SCIENTIFIC_NAME,
        "gbif_match_scientific_name": match.get("scientificName"),
        "gbif_usage_key": int(usage_key),
        "gbif_match_confidence": match.get("confidence"),
        "country": COUNTRY_CODE,
        "maximum_training_year": TRAINING_YEAR_MAX,
        "gbif_eligible_record_count": total,
        "gbif_fetch_cap": int(cap),
        "retrieval_strategy": retrieval,
        "raw_rows_received": int(len(raw)),
        "clean_training_rows": int(len(occurrences)),
        "taxon_metadata": metadata,
    }
    return occurrences, provenance


def assign_island(latitude: float, longitude: float) -> str:
    lat = float(latitude)
    lon = float(longitude)
    for island, (west, south, east, north) in ISLAND_BOUNDS.items():
        if west <= lon <= east and south <= lat <= north:
            return island
    centers = {
        island: ((south + north) / 2.0, (west + east) / 2.0)
        for island, (west, south, east, north) in ISLAND_BOUNDS.items()
    }
    return min(
        centers,
        key=lambda island: float(
            haversine_distance_m(lat, lon, np.array([centers[island][0]]), np.array([centers[island][1]]))[0]
        ),
    )


def build_frozen_candidates(occurrences: pd.DataFrame, metadata: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    training = occurrences.copy().reset_index(drop=True)
    training["_row_id"] = np.arange(len(training), dtype=int)
    features = [rectangle_feature(name, bounds) for name, bounds in ISLAND_BOUNDS.items()]
    bundle = build_automatic_discover_bundle(
        SCIENTIFIC_NAME,
        training,
        "GBIF records through 2025; temporal external validation",
        "Izu five-island field region",
        override_row_ids=training["_row_id"].tolist(),
        taxon_metadata=metadata,
        survey_bounds=SURVEY_BOUNDS,
        survey_features=features,
        candidate_generation_only=True,
    )
    potential = bundle["potential_candidates"].copy()
    if potential.empty:
        raise RuntimeError("ACSP produced no potential candidates.")
    potential = potential.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)
    candidate_type = potential.get("candidate_type", pd.Series("", index=potential.index)).astype(str)
    potential = potential[
        ~candidate_type.str.contains("occurrence-supported|known-location|known anchor", case=False, na=False)
    ].reset_index(drop=True)
    scored = integrated_candidate_scores(potential, exclude_occurrence_derived=True)
    if scored.empty:
        raise RuntimeError("No distance-excluded candidates remained.")
    if "component_local_habitat_score" not in scored.columns:
        raise RuntimeError("ACSP did not expose component_local_habitat_score.")
    local = pd.to_numeric(scored["component_local_habitat_score"], errors="coerce")
    if local.notna().sum() < 1:
        raise RuntimeError("No candidate had usable local-habitat evidence.")

    scored["survey_area_id"] = [
        assign_island(latitude, longitude)
        for latitude, longitude in zip(scored["latitude"], scored["longitude"])
    ]
    if "site_id" not in scored.columns:
        scored["site_id"] = np.arange(1, len(scored) + 1, dtype=int)
    scored["site_id"] = scored["site_id"].astype(str)
    scored = scored.sort_values(
        ["component_local_habitat_score", "site_id"],
        ascending=[False, True],
        kind="mergesort",
    ).reset_index(drop=True)

    # This is exactly the predeclared plant selection policy used in the
    # independent random-taxon benchmark: local-habitat ordering only.
    selected = select_complementary_candidates(
        scored,
        min(PRIMARY_TOP_K, len(scored)),
        score_col="component_local_habitat_score",
        evidence_weight=1.0,
    )
    selected["is_recommended"] = True
    selected["validation_role"] = "frozen_before_field_GPS_read"
    selected["training_year_max"] = TRAINING_YEAR_MAX
    return scored, selected


def island_constrained_recovery(
    selected: pd.DataFrame,
    clusters: pd.DataFrame,
    radii_km: tuple[float, ...] = DEFAULT_RECOVERY_RADII_KM,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, detection in clusters.iterrows():
        island = str(detection["island"]).lower()
        available = selected[selected["survey_area_id"].astype(str).str.lower().eq(island)]
        row = detection.to_dict()
        row["same_island_candidate_count"] = int(len(available))
        if available.empty:
            row["nearest_candidate_id"] = None
            row["nearest_candidate_distance_km"] = np.inf
            for radius in radii_km:
                row[f"recovered_{float(radius):g}km"] = False
        else:
            distances = haversine_distance_m(
                float(detection["latitude"]),
                float(detection["longitude"]),
                available["latitude"].to_numpy(float),
                available["longitude"].to_numpy(float),
            )
            nearest_position = int(np.argmin(distances))
            nearest = available.iloc[nearest_position]
            distance_km = float(distances[nearest_position] / 1000.0)
            row["nearest_candidate_id"] = nearest["site_id"]
            row["nearest_candidate_distance_km"] = distance_km
            for radius in radii_km:
                row[f"recovered_{float(radius):g}km"] = bool(distance_km <= float(radius))
        rows.append(row)
    return pd.DataFrame(rows)


def island_random_benchmark(
    pool: pd.DataFrame,
    selected: pd.DataFrame,
    clusters: pd.DataFrame,
    *,
    iterations: int,
    seed: int,
    radii_km: tuple[float, ...] = DEFAULT_RECOVERY_RADII_KM,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    quotas = selected.groupby("survey_area_id").size().astype(int).to_dict()
    observed = recovery_summary(island_constrained_recovery(selected, clusters, radii_km), radii_km=radii_km)
    observed = observed.set_index("radius_km")
    rng = np.random.default_rng(int(seed))
    random_rows: list[dict[str, Any]] = []
    for iteration in range(1, max(1, int(iterations)) + 1):
        parts = []
        for area, quota in quotas.items():
            area_pool = pool[pool["survey_area_id"].eq(area)]
            if len(area_pool) < quota:
                raise RuntimeError(f"Area {area!r} has {len(area_pool)} candidates for quota {quota}.")
            parts.append(area_pool.iloc[rng.choice(len(area_pool), size=quota, replace=False)])
        sampled = pd.concat(parts, ignore_index=True)
        summary = recovery_summary(island_constrained_recovery(sampled, clusters, radii_km), radii_km=radii_km)
        for row in summary.itertuples(index=False):
            random_rows.append({
                "iteration": iteration,
                "radius_km": float(row.radius_km),
                "random_detection_recall": float(row.detection_recall),
            })
    draws = pd.DataFrame(random_rows)
    results = []
    for radius, group in draws.groupby("radius_km", sort=True):
        observed_recall = float(observed.loc[radius, "detection_recall"])
        values = group["random_detection_recall"].to_numpy(float)
        results.append({
            "radius_km": float(radius),
            "acsp_detection_recall": observed_recall,
            "random_mean_recall": float(values.mean()),
            "random_q025": float(np.quantile(values, 0.025)),
            "random_q975": float(np.quantile(values, 0.975)),
            "lift_over_random": observed_recall - float(values.mean()),
            "randomization_p_one_sided": float((1 + np.sum(values >= observed_recall)) / (len(values) + 1)),
            "iterations": int(iterations),
            "seed": int(seed),
        })
    return pd.DataFrame(results), draws


def main() -> None:
    args = parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    # Stage 1: historical occurrence retrieval and candidate freezing.
    occurrences, provenance = fetch_historical_gbif(args.gbif_cap)
    pool, selected = build_frozen_candidates(occurrences, provenance["taxon_metadata"])
    occurrences.to_csv(output / "gbif_training_occurrences_through_2025.csv", index=False)
    pool.to_csv(output / "distance_excluded_candidate_pool.csv", index=False)
    selected.to_csv(output / "frozen_acsp_top5.csv", index=False)
    (output / "gbif_query_provenance.json").write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )

    # Stage 2: only after Top-5 is frozen do we read the independent field GPS.
    locations = pd.read_csv(args.locations)
    field_rows, clusters = cluster_field_detections(
        locations,
        cluster_radius_m=float(args.cluster_radius_m),
        area_col="island",
    )
    field_rows.to_csv(output / "field_rows_with_clusters.csv", index=False)
    clusters.to_csv(output / "independent_detection_clusters.csv", index=False)

    regional_recovery = detection_recovery_table(
        selected,
        clusters,
        candidate_id_col="site_id",
        area_col="survey_area_id",
    )
    regional_summary = recovery_summary(regional_recovery)
    regional_benchmark, regional_draws = stratified_random_recovery_benchmark(
        pool,
        selected["site_id"],
        clusters,
        iterations=int(args.random_iterations),
        seed=int(args.seed),
        candidate_id_col="site_id",
        area_col="survey_area_id",
    )
    regional_recovery.to_csv(output / "regional_detection_recovery.csv", index=False)
    regional_summary.to_csv(output / "regional_recovery_summary.csv", index=False)
    regional_benchmark.to_csv(output / "regional_same_pool_random_benchmark.csv", index=False)
    regional_draws.to_csv(output / "regional_same_pool_random_draws.csv", index=False)

    within_island_recovery = island_constrained_recovery(selected, clusters)
    within_island_summary = recovery_summary(within_island_recovery)
    within_island_benchmark, within_island_draws = island_random_benchmark(
        pool,
        selected,
        clusters,
        iterations=int(args.random_iterations),
        seed=int(args.seed),
    )
    within_island_recovery.to_csv(output / "within_island_detection_recovery.csv", index=False)
    within_island_summary.to_csv(output / "within_island_recovery_summary.csv", index=False)
    within_island_benchmark.to_csv(output / "within_island_same_pool_random_benchmark.csv", index=False)
    within_island_draws.to_csv(output / "within_island_same_pool_random_draws.csv", index=False)

    primary_regional = regional_benchmark[np.isclose(regional_benchmark["radius_km"], PRIMARY_RADIUS_KM)].iloc[0]
    primary_within = within_island_benchmark[
        np.isclose(within_island_benchmark["radius_km"], PRIMARY_RADIUS_KM)
    ].iloc[0]
    result = {
        "design": "temporal external validation; GBIF <=2025, independent field detections from 2026",
        "field_data_used_in_training": False,
        "field_data_read_after_top5_frozen": True,
        "selection_policy": "Top-5 by component_local_habitat_score; evidence_weight=1.0",
        "primary_endpoint": "independent field-cluster recall within 10 km",
        "training_occurrences": int(len(occurrences)),
        "candidate_pool": int(len(pool)),
        "selected_candidates": int(len(selected)),
        "independent_detection_clusters": int(len(clusters)),
        "selected_island_allocation": selected["survey_area_id"].value_counts().sort_index().to_dict(),
        "regional_primary": primary_regional.to_dict(),
        "within_island_primary": primary_within.to_dict(),
        "cluster_radius_m": float(args.cluster_radius_m),
        "random_iterations": int(args.random_iterations),
        "seed": int(args.seed),
        "scientific_guardrail": (
            "This tests transfer from historical GBIF occurrences to independent 2026 field detections. "
            "Positive-only detections do not estimate occupancy or detection probability."
        ),
    }
    (output / "validation_summary.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
