#!/usr/bin/env python3
"""Development-only component-wise stopping diagnostic for Campanula.

The patch order inside each disconnected island component is built entirely from
pre-2026 occurrence prototypes and public NDVI using the already frozen spatial
policy coefficients.  Before field outcomes are opened, each component is
truncated at a deterministic environmental-coverage versus patch-area knee.

This tests a simple hypothesis suggested by the 32-versus-11 compression gap:
poor compression may come from continuing to select redundant patches inside a
component after its occurrence-conditioned environmental support is already
well represented.  Field detections are used only after all component stopping
points and selected patch IDs are frozen.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

import campanula_patch_policy as base
import campanula_patch_policy_spatial as spatial
from campanula_worldcover_discovery import evaluate

SUPPORT_FRACTION = 0.05
SUPPORT_WEIGHT = 0.25
NEW_COMPONENT_WEIGHT = 0.10
AREA_COST_WEIGHT = 0.02
GEO_WEIGHT = 1.00
GAP_WEIGHT = 0.05


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--microterrain-universe", type=Path, required=True)
    parser.add_argument("--gbif-prototypes", type=Path, required=True)
    parser.add_argument("--ndvi", type=Path, required=True)
    parser.add_argument("--detections", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def _component_order_and_knee(
    zones: pd.DataFrame,
    matrix: np.ndarray,
    support: np.ndarray,
    area_cost: np.ndarray,
    proto_rows: pd.DataFrame,
    gap: np.ndarray,
    spatial_scale: dict[str, float],
    islands: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
    component: str,
) -> tuple[list[int], dict[str, object], pd.DataFrame]:
    global_idx = np.flatnonzero(islands.astype(str) == str(component))
    if not len(global_idx):
        raise ValueError(f"component {component!r} has no patches")

    proto_mask = proto_rows["island"].astype(str).eq(str(component)).to_numpy()
    if proto_mask.any():
        component_matrix = matrix[np.ix_(global_idx, np.flatnonzero(proto_mask))]
        prototype_scope = "same_component_occurrence_prototypes"
    else:
        component_matrix = matrix[global_idx]
        prototype_scope = "global_occurrence_prototypes_no_local_training_records"

    local_islands = islands[global_idx]
    local_lat = lat[global_idx]
    local_lon = lon[global_idx]
    local_gap = gap[global_idx]
    order_local = spatial.greedy_spatial_order(
        component_matrix,
        support[global_idx],
        area_cost[global_idx],
        local_islands,
        local_lat,
        local_lon,
        local_gap,
        spatial_scale,
        SUPPORT_WEIGHT,
        NEW_COMPONENT_WEIGHT,
        AREA_COST_WEIGHT,
        GEO_WEIGHT,
        GAP_WEIGHT,
    )
    order_global = [int(global_idx[pos]) for pos in order_local]

    max_coverage = float(np.mean(component_matrix.max(axis=0))) if component_matrix.shape[1] else 0.0
    member_counts = pd.to_numeric(
        zones.iloc[global_idx]["zone_member_count"], errors="coerce"
    ).fillna(1.0).to_numpy(float)
    total_cells = float(member_counts.sum())
    current = np.zeros(component_matrix.shape[1], dtype=float)
    cumulative_cells = 0.0
    rows: list[dict[str, object]] = []
    for rank, local_pos in enumerate(order_local, start=1):
        current = np.maximum(current, component_matrix[local_pos])
        raw_coverage = float(np.mean(current)) if len(current) else 0.0
        coverage_fraction = raw_coverage / max_coverage if max_coverage > 0 else 0.0
        cumulative_cells += float(member_counts[local_pos])
        area_fraction = cumulative_cells / total_cells if total_cells > 0 else 0.0
        knee_score = coverage_fraction - area_fraction
        global_pos = int(global_idx[local_pos])
        rows.append(
            {
                "component": str(component),
                "rank": int(rank),
                "zone_id": str(zones.iloc[global_pos]["zone_id"]),
                "environmental_coverage_fraction": float(coverage_fraction),
                "cumulative_patch_cells": int(cumulative_cells),
                "component_patch_cell_fraction": float(area_fraction),
                "knee_score": float(knee_score),
            }
        )

    curve = pd.DataFrame(rows)
    best_score = float(curve["knee_score"].max())
    chosen_rank = int(
        curve.loc[np.isclose(curve["knee_score"], best_score), "rank"].min()
    )
    chosen = order_global[:chosen_rank]
    curve["recommended"] = curve["rank"].eq(chosen_rank)
    audit = {
        "component": str(component),
        "patch_universe": int(len(global_idx)),
        "selected_patches": int(chosen_rank),
        "prototype_count": int(component_matrix.shape[1]),
        "prototype_scope": prototype_scope,
        "maximum_environmental_coverage": float(max_coverage),
        "knee_score": best_score,
        "selected_zone_ids": zones.iloc[chosen]["zone_id"].astype(str).tolist(),
    }
    return chosen, audit, curve


def main() -> None:
    args = parse_args()
    universe = pd.read_csv(args.microterrain_universe)
    prototypes = pd.read_csv(args.gbif_prototypes)
    universe, prototypes = base.attach_ndvi(universe, prototypes, args.ndvi)
    responsibility, support_rank, proto_rows, kernel_scale = base.environmental_geometry(
        universe, prototypes
    )
    _, zones = base.make_zones(universe, support_rank, SUPPORT_FRACTION)
    matrix, support, area_cost, _ = base.patch_responsibilities(
        zones, responsibility, support_rank
    )
    gap, spatial_scale, islands, lat, lon = spatial.patch_spatial_features(
        zones, proto_rows
    )

    # Outcome-blind selection ends here. The detection file has not been read.
    selected_positions: list[int] = []
    component_audits = []
    curves = []
    for component in sorted(set(islands.astype(str))):
        chosen, audit, curve = _component_order_and_knee(
            zones,
            matrix,
            support,
            area_cost,
            proto_rows,
            gap,
            spatial_scale,
            islands,
            lat,
            lon,
            component,
        )
        selected_positions.extend(chosen)
        component_audits.append(audit)
        curves.append(curve)

    selected_positions = list(dict.fromkeys(selected_positions))
    selected_zones = zones.iloc[selected_positions].copy().reset_index(drop=True)
    selected_member_indices: set[int] = set()
    for _, zone in selected_zones.iterrows():
        selected_member_indices.update(base.patch.member_indices(zone))
    selected_cells = universe.loc[sorted(selected_member_indices)].copy()

    # Development scoring only from this line onward.
    detections = pd.read_csv(args.detections)
    field_result = evaluate(selected_cells, detections, 1.0)

    report = {
        "status": "development_only_component_environmental_knee",
        "species": "Campanula microdonta",
        "field_coordinates_used_to_select_patches": False,
        "support_fraction": SUPPORT_FRACTION,
        "patch_universe": int(len(zones)),
        "selected_patches": int(len(selected_zones)),
        "selected_cells": int(len(selected_member_indices)),
        "component_audits": component_audits,
        "field_development_result": field_result,
        "historical_complete_recovery_reference_patches": 32,
        "historical_minimum_set_cover_reference_patches": 11,
        "interpretation": (
            "The component knees are frozen without field outcomes. Field recovery is read only as a "
            "development diagnostic; failure is retained and does not trigger hidden threshold tuning."
        ),
        "kernel_scale": float(kernel_scale),
    }

    args.out.mkdir(parents=True, exist_ok=True)
    selected_zones.to_csv(args.out / "component_knee_selected_patches.csv", index=False)
    pd.concat(curves, ignore_index=True).to_csv(
        args.out / "component_knee_curves.csv", index=False
    )
    (args.out / "component_knee_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
