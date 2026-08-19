#!/usr/bin/env python3
"""Development-only support-envelope set policy for Campanula.

This experiment replaces pointwise oracle classification and occurrence-prototype
count stopping with a genuinely set-level target.  Before field outcomes are
opened, the pre-2026 occurrence-conditioned support envelope is frozen.  Every
survey patch covers same-component support-envelope cells within the declared
1-km operational recovery radius.  Envelope mass is normalized within each
island so a large island cannot dominate a disconnected small island.

Selection is state dependent: after one patch is chosen, another patch receives
value only for support mass not already represented by the selected set.  One
best patch per disconnected component is seeded first, then patches are added by
maximum marginal uncovered envelope mass.  Survey size is chosen by the
coverage-versus-patch-count knee, with no field coordinate or field outcome read
until the complete order and stopping point are frozen.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

import campanula_patch_policy as base
from campanula_patch_policy_fast import cached_prefix
from campanula_worldcover_discovery import evaluate, haversine_km

SUPPORT_FRACTION = 0.05
COVERAGE_RADIUS_KM = 1.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--microterrain-universe", type=Path, required=True)
    parser.add_argument("--gbif-prototypes", type=Path, required=True)
    parser.add_argument("--ndvi", type=Path, required=True)
    parser.add_argument("--detections", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def _envelope_weights(universe: pd.DataFrame, support_rank: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    envelope_idx = np.flatnonzero(np.asarray(support_rank, dtype=float) <= SUPPORT_FRACTION)
    if not len(envelope_idx):
        raise RuntimeError("support envelope is empty")
    islands = universe.iloc[envelope_idx]["island"].astype(str).to_numpy()
    raw = np.maximum(1.0 - np.asarray(support_rank, dtype=float)[envelope_idx], 1e-12)
    weights = np.zeros(len(envelope_idx), dtype=float)
    components = sorted(set(islands))
    for component in components:
        local = islands == component
        total = float(raw[local].sum())
        if total <= 0:
            weights[local] = 1.0 / float(local.sum())
        else:
            weights[local] = raw[local] / total
        weights[local] /= float(len(components))
    weights /= float(weights.sum())
    return envelope_idx, weights


def _zone_envelope_matrix(
    universe: pd.DataFrame,
    zones: pd.DataFrame,
    envelope_idx: np.ndarray,
) -> np.ndarray:
    envelope = universe.iloc[envelope_idx]
    env_island = envelope["island"].astype(str).to_numpy()
    env_lat = envelope["lat"].to_numpy(float)
    env_lon = envelope["lon"].to_numpy(float)
    coverage = np.zeros((len(zones), len(envelope_idx)), dtype=bool)

    for zone_pos, (_, zone) in enumerate(zones.iterrows()):
        component = str(zone["survey_area_id"])
        local_env = np.flatnonzero(env_island == component)
        if not len(local_env):
            continue
        members = base.patch.member_indices(zone)
        if not members:
            continue
        member_rows = universe.iloc[members]
        member_lat = member_rows["lat"].to_numpy(float)
        member_lon = member_rows["lon"].to_numpy(float)
        minimum = np.full(len(local_env), np.inf, dtype=float)
        # Vectorize over envelope cells and loop only over member points.  The
        # 5% envelope and bounded complete-link patches keep this small.
        for lat, lon in zip(member_lat, member_lon):
            distance = haversine_km(
                np.full(len(local_env), float(lat)),
                np.full(len(local_env), float(lon)),
                env_lat[local_env],
                env_lon[local_env],
            )
            minimum = np.minimum(minimum, np.asarray(distance, dtype=float))
        coverage[zone_pos, local_env] = minimum <= COVERAGE_RADIUS_KM
    return coverage


def _marginal_order(
    zones: pd.DataFrame,
    coverage: np.ndarray,
    weights: np.ndarray,
) -> tuple[list[int], pd.DataFrame]:
    n = len(zones)
    selected = np.zeros(n, dtype=bool)
    covered = np.zeros(coverage.shape[1], dtype=bool)
    order: list[int] = []
    rows: list[dict[str, object]] = []

    def choose(candidates: np.ndarray, phase: str) -> int:
        best_key = None
        best = -1
        for pos in candidates:
            gain = float(weights[np.logical_and(coverage[pos], ~covered)].sum())
            member_count = float(zones.iloc[int(pos)].get("zone_member_count", 1.0))
            key = (gain, -member_count, -int(pos))
            if best_key is None or key > best_key:
                best_key = key
                best = int(pos)
        if best < 0:
            raise RuntimeError(f"no candidate available during {phase}")
        return best

    # Disconnected-component safety: every declared island contributes one
    # support-envelope representative before global competition begins.
    components = zones["survey_area_id"].astype(str).to_numpy()
    for component in sorted(set(components)):
        candidates = np.flatnonzero(np.logical_and(~selected, components == component))
        pos = choose(candidates, "component_seed")
        selected[pos] = True
        previous = float(weights[covered].sum())
        covered |= coverage[pos]
        cumulative = float(weights[covered].sum())
        order.append(pos)
        rows.append({
            "rank": len(order),
            "zone_id": str(zones.iloc[pos]["zone_id"]),
            "survey_area_id": component,
            "selection_phase": "component_seed",
            "marginal_envelope_mass": cumulative - previous,
            "cumulative_envelope_mass": cumulative,
        })

    while (~selected).any():
        candidates = np.flatnonzero(~selected)
        pos = choose(candidates, "global_marginal")
        selected[pos] = True
        previous = float(weights[covered].sum())
        covered |= coverage[pos]
        cumulative = float(weights[covered].sum())
        order.append(pos)
        rows.append({
            "rank": len(order),
            "zone_id": str(zones.iloc[pos]["zone_id"]),
            "survey_area_id": str(zones.iloc[pos]["survey_area_id"]),
            "selection_phase": "global_marginal",
            "marginal_envelope_mass": cumulative - previous,
            "cumulative_envelope_mass": cumulative,
        })

    curve = pd.DataFrame(rows)
    curve["selected_patch_fraction"] = curve["rank"] / float(n)
    curve["knee_score"] = curve["cumulative_envelope_mass"] - curve["selected_patch_fraction"]
    minimum_rank = len(set(components))
    eligible = curve["rank"] >= minimum_rank
    best_score = float(curve.loc[eligible, "knee_score"].max())
    chosen_rank = int(
        curve.loc[eligible & np.isclose(curve["knee_score"], best_score), "rank"].min()
    )
    curve["recommended"] = curve["rank"].eq(chosen_rank)
    return order, curve


def _ranked_zones(zones: pd.DataFrame, order: list[int]) -> pd.DataFrame:
    ranked = zones.iloc[order].copy().reset_index(drop=True)
    ranked["zone_score"] = np.arange(len(ranked), 0, -1, dtype=float)
    ranked["policy_rank"] = np.arange(1, len(ranked) + 1)
    return ranked


def _selected_cells(universe: pd.DataFrame, selected_zones: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    indices: set[int] = set()
    for _, zone in selected_zones.iterrows():
        indices.update(base.patch.member_indices(zone))
    return universe.loc[sorted(indices)].copy(), len(indices)


def main() -> None:
    args = parse_args()
    universe = pd.read_csv(args.microterrain_universe)
    prototypes = pd.read_csv(args.gbif_prototypes)
    universe, prototypes = base.attach_ndvi(universe, prototypes, args.ndvi)
    _, support_rank, _, kernel_scale = base.environmental_geometry(universe, prototypes)
    _, zones = base.make_zones(universe, support_rank, SUPPORT_FRACTION)

    envelope_idx, envelope_weights = _envelope_weights(universe, support_rank)
    coverage = _zone_envelope_matrix(universe, zones, envelope_idx)
    order, curve = _marginal_order(zones, coverage, envelope_weights)
    ranked = _ranked_zones(zones, order)
    recommended_rank = int(curve.loc[curve["recommended"], "rank"].iloc[0])
    selected_zones = ranked.iloc[:recommended_rank].copy()
    selected_cells, selected_cell_count = _selected_cells(universe, selected_zones)

    # Outcome-blind generator and stopping rule end here.  Field outcomes are
    # first opened below, solely for development scoring.
    detections = pd.read_csv(args.detections)
    recommended_field = evaluate(selected_cells, detections, COVERAGE_RADIUS_KM)
    complete_prefix = cached_prefix(universe, ranked, detections, COVERAGE_RADIUS_KM)

    envelope = universe.iloc[envelope_idx]
    report = {
        "status": "development_only_support_envelope_set_policy",
        "species": "Campanula microdonta",
        "field_coordinates_used_to_build_envelope": False,
        "field_coordinates_used_to_order_patches": False,
        "field_coordinates_used_to_choose_stopping_point": False,
        "support_fraction": SUPPORT_FRACTION,
        "coverage_radius_km": COVERAGE_RADIUS_KM,
        "patch_universe": int(len(zones)),
        "support_envelope_cells": int(len(envelope_idx)),
        "support_envelope_components": int(envelope["island"].astype(str).nunique()),
        "component_mass_normalization": "equal total support mass per disconnected island",
        "ordering": "one best patch per component, then maximum marginal uncovered support-envelope mass",
        "stopping_rule": "maximize cumulative envelope mass minus selected patch fraction",
        "selected_patches": recommended_rank,
        "selected_cells": int(selected_cell_count),
        "selected_envelope_mass": float(curve.loc[curve["recommended"], "cumulative_envelope_mass"].iloc[0]),
        "field_development_result": recommended_field,
        "first_complete_recovery_prefix": complete_prefix,
        "historical_complete_recovery_reference_patches": 32,
        "historical_minimum_set_cover_reference_patches": 11,
        "kernel_scale": float(kernel_scale),
        "interpretation": (
            "Patch value is state-dependent support-envelope complementarity, not pointwise suitability or "
            "oracle membership. Campanula field outcomes are opened only after the full order and knee are frozen."
        ),
    }

    args.out.mkdir(parents=True, exist_ok=True)
    selected_zones.to_csv(args.out / "support_envelope_selected_patches.csv", index=False)
    ranked.to_csv(args.out / "support_envelope_patch_order.csv", index=False)
    curve.to_csv(args.out / "support_envelope_frontier.csv", index=False)
    (args.out / "support_envelope_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
