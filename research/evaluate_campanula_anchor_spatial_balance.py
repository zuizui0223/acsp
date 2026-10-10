"""Evaluate spatially balanced sampling inside occurrence-anchored annuli.

Scientific role: Campanula development only. Historical occurrence clusters are
held out whole. The retained same-island clusters define an annular local search
frame after a known-point exclusion. Candidate cells are then selected by a
deterministic Morton space-filling order, with systematic positions along that
order to distribute a fixed number of cells across the frame.

This is a strong coverage comparator, not a promoted ACSP policy. Cell count is
not route length, accessible area, search time, cost, or detection probability.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from evaluate_campanula_annular_candidate_frame import (
    _matched_random_recovery_probability,
    _minimum_distance_to_anchors_km,
    _vector_haversine_km,
    prepare_candidate_universe,
)
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
DEFAULT_OUT_DIR = REPO_ROOT / "validation" / "campanula_anchor_spatial_balance_v1"
MORTON_BITS = 16
MORTON_MAX = (1 << MORTON_BITS) - 1


def _part1by1(values: np.ndarray) -> np.ndarray:
    """Spread 16-bit integers so another coordinate can be interleaved."""
    out = np.asarray(values, dtype=np.uint64) & np.uint64(0x0000FFFF)
    out = (out | (out << np.uint64(8))) & np.uint64(0x00FF00FF)
    out = (out | (out << np.uint64(4))) & np.uint64(0x0F0F0F0F)
    out = (out | (out << np.uint64(2))) & np.uint64(0x33333333)
    out = (out | (out << np.uint64(1))) & np.uint64(0x55555555)
    return out


def morton_order(frame: pd.DataFrame) -> np.ndarray:
    """Return deterministic local Morton order for candidate coordinates."""
    if frame.empty:
        return np.asarray([], dtype=int)
    lat = pd.to_numeric(frame["latitude"], errors="coerce").to_numpy(float)
    lon = pd.to_numeric(frame["longitude"], errors="coerce").to_numpy(float)
    if not np.isfinite(lat).all() or not np.isfinite(lon).all():
        raise ValueError("Morton ordering requires complete finite coordinates")

    mean_lat = math.radians(float(np.mean(lat)))
    x = lon * math.cos(mean_lat)
    y = lat

    def quantize(values: np.ndarray) -> np.ndarray:
        low = float(values.min())
        high = float(values.max())
        if high <= low + 1e-15:
            return np.zeros(len(values), dtype=np.uint64)
        scaled = (values - low) / (high - low)
        return np.rint(np.clip(scaled, 0.0, 1.0) * MORTON_MAX).astype(np.uint64)

    qx = quantize(x)
    qy = quantize(y)
    code = _part1by1(qx) | (_part1by1(qy) << np.uint64(1))
    stable_ids = pd.to_numeric(frame["candidate_cell_id"], errors="coerce").to_numpy()
    return np.lexsort((stable_ids, code)).astype(int)


def systematic_morton_sample(frame: pd.DataFrame, count: int) -> pd.DataFrame:
    """Select exact count at evenly spaced positions along a Morton order."""
    target = int(count)
    if target < 0:
        raise ValueError("count must be non-negative")
    if target == 0 or frame.empty:
        return frame.iloc[0:0].copy()
    if target >= len(frame):
        return frame.copy().reset_index(drop=True)
    order = morton_order(frame)
    positions = np.floor((np.arange(target, dtype=float) + 0.5) * len(order) / target).astype(int)
    positions = np.clip(positions, 0, len(order) - 1)
    if len(np.unique(positions)) != target:
        raise RuntimeError("systematic Morton positions were not unique")
    return frame.iloc[order[positions]].copy().reset_index(drop=True)


def evaluate_anchor_spatial_balance(
    universe: pd.DataFrame,
    historical_clusters: pd.DataFrame,
    *,
    exclusion_radius_km: float = 0.5,
    outer_radii_km: Sequence[float] = (2.0, 2.5),
    selection_fractions: Sequence[float] = (0.025, 0.05, 0.10, 0.25, 0.50, 1.0),
    recovery_radii_km: Sequence[float] = (0.1, 0.25, 0.5, 1.0),
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Evaluate spatially balanced prefixes under whole-cluster holdout."""
    cells = prepare_candidate_universe(universe)
    clusters = historical_clusters.copy().reset_index(drop=True)
    required = {
        "historical_cluster_id",
        "cluster_policy",
        "island",
        "latitude",
        "longitude",
    }
    missing = sorted(required.difference(clusters.columns))
    if missing:
        raise ValueError(f"historical clusters are missing columns: {missing}")
    clusters["island"] = clusters["island"].astype(str).str.strip().str.lower()
    for column in ("latitude", "longitude"):
        clusters[column] = pd.to_numeric(clusters[column], errors="coerce")

    outer_radii = tuple(sorted({float(value) for value in outer_radii_km}))
    fractions = tuple(sorted({float(value) for value in selection_fractions}))
    recovery_radii = tuple(sorted({float(value) for value in recovery_radii_km}))
    if float(exclusion_radius_km) < 0:
        raise ValueError("exclusion_radius_km must be non-negative")
    if not outer_radii or any(value <= exclusion_radius_km for value in outer_radii):
        raise ValueError("every outer radius must exceed exclusion_radius_km")
    if not fractions or any(value <= 0 or value > 1 for value in fractions):
        raise ValueError("selection fractions must lie in (0, 1]")
    if not recovery_radii or any(value <= 0 for value in recovery_radii):
        raise ValueError("recovery radii must be positive")

    rows: list[dict[str, object]] = []
    for policy in SUPPORTED_CLUSTER_POLICIES:
        policy_clusters = clusters.loc[
            clusters["cluster_policy"].astype(str).eq(policy)
        ].copy()
        for hidden in policy_clusters.to_dict(orient="records"):
            island = str(hidden["island"])
            island_cells = cells.loc[cells["island"].eq(island)].copy()
            retained = policy_clusters.loc[
                policy_clusters["island"].astype(str).eq(island)
                & ~policy_clusters["historical_cluster_id"].eq(
                    hidden["historical_cluster_id"]
                )
            ].copy()
            anchor_absent = retained.empty
            nearest_anchor_distance: float | None = None
            if not anchor_absent:
                nearest_anchor_distance = float(
                    _vector_haversine_km(
                        float(hidden["latitude"]),
                        float(hidden["longitude"]),
                        retained["latitude"].to_numpy(float),
                        retained["longitude"].to_numpy(float),
                    ).min()
                )
            inside_exclusion = bool(
                nearest_anchor_distance is not None
                and nearest_anchor_distance <= float(exclusion_radius_km) + 1e-12
            )
            evaluable = bool(not anchor_absent and not inside_exclusion)

            cell_anchor_distance = _minimum_distance_to_anchors_km(
                island_cells, retained
            )
            outside_exclusion = (
                np.isfinite(cell_anchor_distance)
                & (cell_anchor_distance > float(exclusion_radius_km) + 1e-12)
            )

            for outer_radius in outer_radii:
                annulus_mask = outside_exclusion & (
                    cell_anchor_distance <= outer_radius + 1e-12
                )
                annulus = island_cells.loc[annulus_mask].copy().reset_index(drop=True)
                annulus_hidden_distance = (
                    _vector_haversine_km(
                        float(hidden["latitude"]),
                        float(hidden["longitude"]),
                        annulus["latitude"].to_numpy(float),
                        annulus["longitude"].to_numpy(float),
                    )
                    if not annulus.empty
                    else np.asarray([], dtype=float)
                )

                for fraction in fractions:
                    if annulus.empty or anchor_absent:
                        selected = annulus.iloc[0:0].copy()
                    else:
                        count = max(1, int(math.ceil(float(fraction) * len(annulus))))
                        selected = systematic_morton_sample(annulus, count)
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
                        "anchor_conditioned_evaluable": bool(evaluable),
                        "known_point_exclusion_km": float(exclusion_radius_km),
                        "outer_radius_km": float(outer_radius),
                        "selection_fraction_of_annulus": float(fraction),
                        "same_island_land_cells": int(len(island_cells)),
                        "annular_cells": int(len(annulus)),
                        "selected_spatially_balanced_cells": int(len(selected)),
                        "selected_fraction_of_island_land_cells": (
                            float(len(selected) / len(island_cells))
                            if len(island_cells)
                            else 0.0
                        ),
                        "nearest_selected_cell_km": nearest_selected,
                    }
                    for recovery_radius in recovery_radii:
                        suffix = f"{recovery_radius:g}km"
                        recovered = bool(
                            nearest_selected is not None
                            and nearest_selected <= recovery_radius + 1e-12
                        )
                        hit_cells = int(
                            (annulus_hidden_distance <= recovery_radius + 1e-12).sum()
                        )
                        random_probability = (
                            _matched_random_recovery_probability(
                                len(annulus), hit_cells, len(selected)
                            )
                            if len(annulus)
                            else 0.0
                        )
                        base[f"recovered_{suffix}"] = recovered
                        base[f"annular_hit_cells_{suffix}"] = hit_cells
                        base[f"matched_annulus_random_probability_{suffix}"] = random_probability
                        base[f"lift_over_matched_annulus_random_{suffix}"] = (
                            float(recovered) - random_probability
                        )
                    rows.append(base)

    folds = pd.DataFrame(rows).sort_values(
        [
            "cluster_policy",
            "outer_radius_km",
            "selection_fraction_of_annulus",
            "island",
            "hidden_cluster_id",
        ],
        kind="mergesort",
    ).reset_index(drop=True)

    aggregate_rows: list[dict[str, object]] = []
    for keys, group in folds.groupby(
        ["cluster_policy", "outer_radius_km", "selection_fraction_of_annulus"],
        sort=True,
    ):
        policy, outer_radius, fraction = keys
        evaluable_mask = group["anchor_conditioned_evaluable"].astype(bool)
        for recovery_radius in recovery_radii:
            suffix = f"{recovery_radius:g}km"
            recovered = group[f"recovered_{suffix}"].astype(bool)
            random_probability = pd.to_numeric(
                group[f"matched_annulus_random_probability_{suffix}"], errors="coerce"
            ).fillna(0.0)
            conditioned_random = random_probability.loc[evaluable_mask]
            conditioned_recovered = recovered.loc[evaluable_mask].astype(float)
            aggregate_rows.append(
                {
                    "cluster_policy": str(policy),
                    "outer_radius_km": float(outer_radius),
                    "selection_fraction_of_annulus": float(fraction),
                    "recovery_radius_km": float(recovery_radius),
                    "declared_folds": int(len(group)),
                    "anchor_conditioned_evaluable_folds": int(evaluable_mask.sum()),
                    "anchor_absent_folds": int(
                        group["anchor_absent"].astype(bool).sum()
                    ),
                    "inside_exclusion_folds": int(
                        group["inside_known_point_exclusion"].astype(bool).sum()
                    ),
                    "recovered_folds": int(recovered.sum()),
                    "anchor_conditioned_recall": (
                        float(conditioned_recovered.mean())
                        if evaluable_mask.any()
                        else None
                    ),
                    "anchor_conditioned_mean_random_probability": (
                        float(conditioned_random.mean())
                        if evaluable_mask.any()
                        else None
                    ),
                    "anchor_conditioned_mean_lift_over_random": (
                        float(conditioned_recovered.mean() - conditioned_random.mean())
                        if evaluable_mask.any()
                        else None
                    ),
                    "intention_to_evaluate_recall": float(recovered.mean()),
                    "mean_matched_annulus_random_probability": float(
                        random_probability.mean()
                    ),
                    "mean_lift_over_matched_annulus_random": float(
                        recovered.astype(float).mean() - random_probability.mean()
                    ),
                    "median_selected_spatially_balanced_cells": float(
                        pd.to_numeric(group["selected_spatially_balanced_cells"]).median()
                    ),
                    "median_selected_fraction_of_island_land_cells": float(
                        pd.to_numeric(
                            group["selected_fraction_of_island_land_cells"]
                        ).median()
                    ),
                    "effort_boundary": (
                        "Matched annulus land-cell count only; not route length, "
                        "accessible area, search time, or monetary cost."
                    ),
                }
            )
    aggregate = pd.DataFrame(aggregate_rows)

    summary: dict[str, object] = {
        "schema_version": "campanula-anchor-spatial-balance-v1",
        "scientific_role": "development_internal_spatial_coverage_baseline_only",
        "independent_validation": False,
        "reads_2026_field_outcomes": False,
        "hidden_cluster_coordinates_used_for_candidate_selection": False,
        "candidate_universe_rows": int(len(cells)),
        "selection_method": "systematic positions on deterministic 16-bit Morton order",
        "cluster_policies": list(SUPPORTED_CLUSTER_POLICIES),
        "known_point_exclusion_km": float(exclusion_radius_km),
        "outer_radii_km": [float(value) for value in outer_radii],
        "selection_fractions": [float(value) for value in fractions],
        "recovery_radii_km": [float(value) for value in recovery_radii],
        "primary_cluster_policy": PRIMARY_CLUSTER_POLICY,
        "sensitivity_cluster_policy": SENSITIVITY_CLUSTER_POLICY,
        "fold_rows": int(len(folds)),
        "aggregate_rows": int(len(aggregate)),
        "decision_rule": (
            "Any ecological or graph-continuity selector must beat this spatially "
            "balanced occurrence-frame comparator at the same candidate-cell count."
        ),
        "interpretation_boundary": (
            "Morton-systematic sampling is a deterministic coverage comparator, "
            "not official GRTS, a field route, or external validation."
        ),
    }
    return folds, aggregate, summary


def build_historical_clusters(
    occurrences: pd.DataFrame,
    island_bounds: Mapping[str, Sequence[float]],
    *,
    cluster_radius_m: float = 500.0,
) -> pd.DataFrame:
    """Build primary and sensitivity whole-occurrence cluster representations."""
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
    parser.add_argument("--outer-radii-km", type=float, nargs="+", default=[2.0, 2.5])
    parser.add_argument(
        "--selection-fractions",
        type=float,
        nargs="+",
        default=[0.025, 0.05, 0.10, 0.25, 0.50, 1.0],
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
    clusters = build_historical_clusters(
        pd.read_csv(args.occurrences),
        island_bounds,
        cluster_radius_m=args.cluster_radius_m,
    )
    folds, aggregate, summary = evaluate_anchor_spatial_balance(
        pd.read_csv(args.universe),
        clusters,
        exclusion_radius_km=args.known_point_exclusion_km,
        outer_radii_km=args.outer_radii_km,
        selection_fractions=args.selection_fractions,
        recovery_radii_km=args.recovery_radii_km,
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    folds.to_csv(args.out_dir / "anchor_spatial_balance_folds.csv", index=False)
    aggregate.to_csv(args.out_dir / "anchor_spatial_balance_aggregate.csv", index=False)
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(aggregate.to_csv(index=False))


if __name__ == "__main__":
    main()
