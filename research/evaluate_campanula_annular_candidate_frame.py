"""Evaluate occurrence-anchored annuli on the frozen full-island land-cell frame.

Scientific role: Campanula development diagnosis only. Historical occurrence
clusters are held out whole. The selected frame uses only retained same-island
cluster coordinates and the outcome-blind 100-m land-cell universe. Inspected
2026 field detections are never read.

Cell count is a matched spatial-allocation proxy, not field effort. Roads,
trails, barriers, route length, search time, and detection probability remain
outside this baseline.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from evaluate_campanula_occurrence_anchor_loco import (
    PRIMARY_CLUSTER_POLICY,
    SENSITIVITY_CLUSTER_POLICY,
    SUPPORTED_CLUSTER_POLICIES,
    cluster_occurrence_points,
    prepare_island_occurrences,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OCCURRENCES = (
    REPO_ROOT
    / "field_validation"
    / "campanula_microdonta"
    / "development_data"
    / "gbif_training_occurrences_through_2025.csv"
)
DEFAULT_MANIFEST = (
    REPO_ROOT
    / "field_validation"
    / "campanula_microdonta"
    / "development_data"
    / "manifest.json"
)
DEFAULT_OUT_DIR = REPO_ROOT / "validation" / "campanula_annular_candidate_frame_v1"
EARTH_RADIUS_KM = 6371.0088


def _vector_haversine_km(
    latitude: float,
    longitude: float,
    latitudes: np.ndarray,
    longitudes: np.ndarray,
) -> np.ndarray:
    """Return vectorised great-circle distances in kilometres."""
    lat1 = math.radians(float(latitude))
    lon1 = math.radians(float(longitude))
    lat2 = np.radians(np.asarray(latitudes, dtype=float))
    lon2 = np.radians(np.asarray(longitudes, dtype=float))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    value = (
        np.sin(dlat / 2.0) ** 2
        + math.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(
        np.sqrt(np.clip(value, 0.0, 1.0))
    )


def prepare_candidate_universe(universe: pd.DataFrame) -> pd.DataFrame:
    """Normalize the outcome-blind full-island land-cell universe."""
    aliases = {
        "island": ("island", "survey_area_id"),
        "latitude": ("latitude", "lat"),
        "longitude": ("longitude", "lon"),
    }
    selected: dict[str, str] = {}
    for target, options in aliases.items():
        for option in options:
            if option in universe.columns:
                selected[target] = option
                break
        if target not in selected:
            raise ValueError(
                f"candidate universe requires one of {options} for {target!r}"
            )

    work = pd.DataFrame(
        {
            "island": universe[selected["island"]].astype(str).str.strip().str.lower(),
            "latitude": pd.to_numeric(
                universe[selected["latitude"]], errors="coerce"
            ),
            "longitude": pd.to_numeric(
                universe[selected["longitude"]], errors="coerce"
            ),
        }
    )
    work = work.dropna(subset=["latitude", "longitude"]).copy()
    valid = work["latitude"].between(-90, 90) & work["longitude"].between(-180, 180)
    work = work.loc[valid].copy()
    work["candidate_cell_id"] = np.arange(len(work), dtype=int)
    if work.empty:
        raise ValueError("candidate universe contains no valid land cells")
    return work.reset_index(drop=True)


def _minimum_distance_to_anchors_km(
    cells: pd.DataFrame,
    anchors: pd.DataFrame,
) -> np.ndarray:
    """Return each cell's nearest retained-anchor distance."""
    if cells.empty:
        return np.asarray([], dtype=float)
    if anchors.empty:
        return np.full(len(cells), np.inf, dtype=float)
    minima = np.full(len(cells), np.inf, dtype=float)
    cell_lat = cells["latitude"].to_numpy(float)
    cell_lon = cells["longitude"].to_numpy(float)
    for anchor in anchors.to_dict(orient="records"):
        minima = np.minimum(
            minima,
            _vector_haversine_km(
                float(anchor["latitude"]),
                float(anchor["longitude"]),
                cell_lat,
                cell_lon,
            ),
        )
    return minima


def _matched_random_recovery_probability(
    population_size: int,
    hit_cells: int,
    draw_size: int,
) -> float:
    """Exact probability that a same-size random draw contains at least one hit cell."""
    population = int(population_size)
    hits = int(hit_cells)
    draws = int(draw_size)
    if population < 0 or hits < 0 or draws < 0:
        raise ValueError("population_size, hit_cells, and draw_size must be non-negative")
    if hits > population or draws > population:
        raise ValueError("hit_cells and draw_size cannot exceed population_size")
    if hits == 0 or draws == 0:
        return 0.0
    if draws > population - hits:
        return 1.0
    log_no_hit = (
        math.lgamma(population - hits + 1)
        - math.lgamma(draws + 1)
        - math.lgamma(population - hits - draws + 1)
        - math.lgamma(population + 1)
        + math.lgamma(draws + 1)
        + math.lgamma(population - draws + 1)
    )
    no_hit = math.exp(min(0.0, log_no_hit))
    return float(max(0.0, min(1.0, 1.0 - no_hit)))


def evaluate_annular_candidate_frame(
    universe: pd.DataFrame,
    historical_clusters: pd.DataFrame,
    *,
    exclusion_radius_km: float = 0.5,
    outer_radii_km: Sequence[float] = (1.0, 2.0, 2.5, 5.0),
    recovery_radii_km: Sequence[float] = (0.1, 0.25, 0.5, 1.0),
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Evaluate annular land-cell frames under whole-cluster holdout."""
    cells = prepare_candidate_universe(universe)
    if float(exclusion_radius_km) < 0:
        raise ValueError("exclusion_radius_km must be non-negative")
    outer_radii = tuple(sorted({float(value) for value in outer_radii_km}))
    recovery_radii = tuple(sorted({float(value) for value in recovery_radii_km}))
    if not outer_radii or any(value <= exclusion_radius_km for value in outer_radii):
        raise ValueError("every outer radius must exceed exclusion_radius_km")
    if not recovery_radii or any(value <= 0 for value in recovery_radii):
        raise ValueError("recovery radii must be positive")

    required = {
        "historical_cluster_id",
        "cluster_policy",
        "island",
        "latitude",
        "longitude",
    }
    missing = sorted(required.difference(historical_clusters.columns))
    if missing:
        raise ValueError(f"historical clusters are missing columns: {missing}")

    rows: list[dict[str, object]] = []
    for policy in SUPPORTED_CLUSTER_POLICIES:
        policy_clusters = historical_clusters.loc[
            historical_clusters["cluster_policy"].astype(str).eq(policy)
        ].copy()
        for hidden in policy_clusters.to_dict(orient="records"):
            island = str(hidden["island"]).strip().lower()
            island_cells = cells.loc[cells["island"].eq(island)].copy()
            retained = policy_clusters.loc[
                policy_clusters["island"].astype(str).str.lower().eq(island)
                & ~policy_clusters["historical_cluster_id"].eq(
                    hidden["historical_cluster_id"]
                )
            ].copy()
            anchor_absent = retained.empty
            nearest_anchor_distance = None
            if not anchor_absent:
                anchor_distances = _vector_haversine_km(
                    float(hidden["latitude"]),
                    float(hidden["longitude"]),
                    retained["latitude"].to_numpy(float),
                    retained["longitude"].to_numpy(float),
                )
                nearest_anchor_distance = float(anchor_distances.min())
            inside_exclusion = bool(
                nearest_anchor_distance is not None
                and nearest_anchor_distance <= float(exclusion_radius_km) + 1e-12
            )
            anchor_conditioned_evaluable = bool(
                not anchor_absent and not inside_exclusion
            )

            cell_anchor_distance = _minimum_distance_to_anchors_km(
                island_cells, retained
            )
            eligible_mask = (
                np.isfinite(cell_anchor_distance)
                & (cell_anchor_distance > float(exclusion_radius_km) + 1e-12)
            )
            eligible = island_cells.loc[eligible_mask].copy()
            eligible_hidden_distance = (
                _vector_haversine_km(
                    float(hidden["latitude"]),
                    float(hidden["longitude"]),
                    eligible["latitude"].to_numpy(float),
                    eligible["longitude"].to_numpy(float),
                )
                if not eligible.empty
                else np.asarray([], dtype=float)
            )

            for outer_radius in outer_radii:
                selected_mask = eligible_mask & (
                    cell_anchor_distance <= outer_radius + 1e-12
                )
                selected = island_cells.loc[selected_mask].copy()
                selected_hidden_distance = (
                    _vector_haversine_km(
                        float(hidden["latitude"]),
                        float(hidden["longitude"]),
                        selected["latitude"].to_numpy(float),
                        selected["longitude"].to_numpy(float),
                    )
                    if not selected.empty
                    else np.asarray([], dtype=float)
                )
                nearest_selected = (
                    None
                    if selected_hidden_distance.size == 0
                    else float(selected_hidden_distance.min())
                )
                base: dict[str, object] = {
                    "cluster_policy": policy,
                    "hidden_cluster_id": int(hidden["historical_cluster_id"]),
                    "island": island,
                    "hidden_latitude": float(hidden["latitude"]),
                    "hidden_longitude": float(hidden["longitude"]),
                    "retained_same_island_anchor_count": int(len(retained)),
                    "nearest_retained_anchor_km": nearest_anchor_distance,
                    "anchor_absent": bool(anchor_absent),
                    "inside_known_point_exclusion": bool(inside_exclusion),
                    "anchor_conditioned_evaluable": bool(anchor_conditioned_evaluable),
                    "known_point_exclusion_km": float(exclusion_radius_km),
                    "outer_radius_km": float(outer_radius),
                    "same_island_land_cells": int(len(island_cells)),
                    "eligible_cells_outside_exclusion": int(len(eligible)),
                    "selected_annular_cells": int(len(selected)),
                    "selected_fraction_of_island_land_cells": (
                        float(len(selected) / len(island_cells))
                        if len(island_cells)
                        else 0.0
                    ),
                    "selected_fraction_of_eligible_cells": (
                        float(len(selected) / len(eligible)) if len(eligible) else 0.0
                    ),
                    "nearest_selected_cell_km": nearest_selected,
                    "hidden_medoid_inside_coordinate_annulus": bool(
                        nearest_anchor_distance is not None
                        and nearest_anchor_distance > float(exclusion_radius_km)
                        and nearest_anchor_distance <= outer_radius
                    ),
                }
                for recovery_radius in recovery_radii:
                    suffix = f"{recovery_radius:g}km"
                    recovered = bool(
                        nearest_selected is not None
                        and nearest_selected <= recovery_radius + 1e-12
                    )
                    hit_cells = int(
                        (eligible_hidden_distance <= recovery_radius + 1e-12).sum()
                    )
                    random_probability = (
                        _matched_random_recovery_probability(
                            len(eligible), hit_cells, len(selected)
                        )
                        if len(eligible)
                        else 0.0
                    )
                    base[f"recovered_{suffix}"] = recovered
                    base[f"eligible_hit_cells_{suffix}"] = hit_cells
                    base[f"matched_cell_random_probability_{suffix}"] = random_probability
                    base[f"lift_over_matched_cell_random_{suffix}"] = (
                        float(recovered) - random_probability
                    )
                rows.append(base)

    folds = pd.DataFrame(rows).sort_values(
        ["cluster_policy", "outer_radius_km", "island", "hidden_cluster_id"],
        kind="mergesort",
    ).reset_index(drop=True)

    aggregate_rows: list[dict[str, object]] = []
    for (policy, outer_radius), group in folds.groupby(
        ["cluster_policy", "outer_radius_km"], sort=True
    ):
        evaluable = group["anchor_conditioned_evaluable"].astype(bool)
        for recovery_radius in recovery_radii:
            suffix = f"{recovery_radius:g}km"
            recovered = group[f"recovered_{suffix}"].astype(bool)
            random_probability = pd.to_numeric(
                group[f"matched_cell_random_probability_{suffix}"], errors="coerce"
            ).fillna(0.0)
            aggregate_rows.append(
                {
                    "cluster_policy": str(policy),
                    "outer_radius_km": float(outer_radius),
                    "recovery_radius_km": float(recovery_radius),
                    "known_point_exclusion_km": float(exclusion_radius_km),
                    "declared_folds": int(len(group)),
                    "anchor_conditioned_evaluable_folds": int(evaluable.sum()),
                    "anchor_absent_folds": int(
                        group["anchor_absent"].astype(bool).sum()
                    ),
                    "inside_exclusion_folds": int(
                        group["inside_known_point_exclusion"].astype(bool).sum()
                    ),
                    "recovered_folds": int(recovered.sum()),
                    "anchor_conditioned_recall": (
                        float(recovered.loc[evaluable].mean())
                        if evaluable.any()
                        else None
                    ),
                    "intention_to_evaluate_recall": float(recovered.mean()),
                    "mean_matched_cell_random_probability": float(
                        random_probability.mean()
                    ),
                    "mean_lift_over_matched_cell_random": float(
                        recovered.astype(float).mean() - random_probability.mean()
                    ),
                    "median_selected_annular_cells": float(
                        pd.to_numeric(group["selected_annular_cells"]).median()
                    ),
                    "median_selected_fraction_of_island_land_cells": float(
                        pd.to_numeric(
                            group["selected_fraction_of_island_land_cells"]
                        ).median()
                    ),
                    "maximum_selected_fraction_of_island_land_cells": float(
                        pd.to_numeric(
                            group["selected_fraction_of_island_land_cells"]
                        ).max()
                    ),
                    "effort_boundary": (
                        "Matched land-cell count only; not matched route length, "
                        "search time, accessible area, or monetary cost."
                    ),
                }
            )
    aggregate = pd.DataFrame(aggregate_rows)

    summary: dict[str, object] = {
        "schema_version": "campanula-annular-candidate-frame-v1",
        "scientific_role": "development_internal_candidate_frame_baseline_only",
        "independent_validation": False,
        "reads_2026_field_outcomes": False,
        "candidate_universe_rows": int(len(cells)),
        "candidate_universe_islands": sorted(cells["island"].unique().tolist()),
        "cluster_policies": list(SUPPORTED_CLUSTER_POLICIES),
        "known_point_exclusion_km": float(exclusion_radius_km),
        "outer_radii_km": [float(value) for value in outer_radii],
        "recovery_radii_km": [float(value) for value in recovery_radii],
        "post_loco_frontier_radius_km": 2.5,
        "post_loco_frontier_radius_reason": (
            "Development-only radius added after the historical LOCO maximum "
            "nearest retained-anchor distance was 2.298833515 km; it is not a "
            "universal or confirmatory parameter."
        ),
        "primary_cluster_policy": PRIMARY_CLUSTER_POLICY,
        "sensitivity_cluster_policy": SENSITIVITY_CLUSTER_POLICY,
        "fold_rows": int(len(folds)),
        "aggregate_rows": int(len(aggregate)),
        "decision_rule": (
            "The next habitat or continuity filter must be evaluated on the same "
            "whole-cluster folds and retain recovery while reducing selected land "
            "cells relative to this annular frame."
        ),
        "interpretation_boundary": (
            "Candidate-cell count is not field effort. This baseline does not "
            "represent access, graph continuity, route length, search duration, "
            "non-detection, or external generalization."
        ),
    }
    return folds, aggregate, summary


def build_historical_clusters(
    occurrences: pd.DataFrame,
    island_bounds: Mapping[str, Sequence[float]],
    *,
    cluster_radius_m: float = 500.0,
) -> pd.DataFrame:
    """Build primary and sensitivity historical cluster representations."""
    points = prepare_island_occurrences(occurrences, island_bounds)
    return pd.concat(
        [
            cluster_occurrence_points(
                points, cluster_radius_m=cluster_radius_m, policy=policy
            )
            for policy in SUPPORTED_CLUSTER_POLICIES
        ],
        ignore_index=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--occurrences", type=Path, default=DEFAULT_OCCURRENCES)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--cluster-radius-m", type=float, default=500.0)
    parser.add_argument("--known-point-exclusion-km", type=float, default=0.5)
    parser.add_argument(
        "--outer-radii-km", type=float, nargs="+", default=[1.0, 2.0, 2.5, 5.0]
    )
    parser.add_argument(
        "--recovery-radii-km", type=float, nargs="+", default=[0.1, 0.25, 0.5, 1.0]
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    island_bounds = manifest.get("island_bounds")
    if not isinstance(island_bounds, dict):
        raise ValueError("manifest must contain an island_bounds object")
    occurrences = pd.read_csv(args.occurrences)
    clusters = build_historical_clusters(
        occurrences, island_bounds, cluster_radius_m=args.cluster_radius_m
    )
    folds, aggregate, summary = evaluate_annular_candidate_frame(
        pd.read_csv(args.universe),
        clusters,
        exclusion_radius_km=args.known_point_exclusion_km,
        outer_radii_km=args.outer_radii_km,
        recovery_radii_km=args.recovery_radii_km,
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "annular_candidate_frame_folds.csv": folds,
        "annular_candidate_frame_aggregate.csv": aggregate,
    }
    for filename, frame in outputs.items():
        path = args.out_dir / filename
        frame.to_csv(path, index=False)
        print(f"wrote {path}")
    summary_path = args.out_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"wrote {summary_path}")


if __name__ == "__main__":
    main()
