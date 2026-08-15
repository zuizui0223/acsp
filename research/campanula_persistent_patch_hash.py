#!/usr/bin/env python3
"""Run persistent-patch development with exact spatial-hash acceleration.

The original ACSP zone aggregator tests every existing zone for every new cell.
Complete-link compatibility implies that a compatible zone's first member must
itself lie within the merge threshold. We spatial-hash those zone anchors, then
retain the original exact haversine maximum-distance test and same `(maximum
distance, zone index)` tie-break. Patch-prefix recovery and matched-random
recovery are accelerated by precomputing each patch's field-cluster coverage.
These changes alter search cost only, not the patch or recovery definitions.
"""
from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd

import campanula_persistent_patch as patch
from campanula_worldcover_discovery import evaluate, haversine_km


def fast_complete_link_zones(
    candidates: pd.DataFrame,
    merge_distance_m: float | None = None,
    area_col: str = "survey_area_id",
    latitude_col: str = "latitude",
    longitude_col: str = "longitude",
    id_col: str = "site_id",
    score_col: str = "priority_score",
):
    if candidates is None or candidates.empty:
        return pd.DataFrame()
    threshold = float(merge_distance_m or 1000.0)
    work = candidates.copy().reset_index(drop=True)
    work[latitude_col] = pd.to_numeric(work[latitude_col], errors="coerce")
    work[longitude_col] = pd.to_numeric(work[longitude_col], errors="coerce")
    work[score_col] = pd.to_numeric(work[score_col], errors="coerce").fillna(0.0)
    work = work.dropna(subset=[latitude_col, longitude_col]).reset_index(drop=True)
    if area_col not in work.columns:
        work[area_col] = "1"

    rows = []
    mean_lat = float(work[latitude_col].mean())
    meters_per_lon = 111_320.0 * math.cos(math.radians(mean_lat))
    meters_per_lat = 111_320.0
    cell = max(threshold, 1.0)

    for area, group in work.groupby(area_col, sort=True, dropna=False):
        ordered = group.assign(
            _stable_numeric=pd.to_numeric(group[id_col], errors="coerce"),
            _stable_id=group[id_col].astype(str),
        ).sort_values(
            ["_stable_numeric", "_stable_id", latitude_col, longitude_col],
            kind="mergesort",
            na_position="last",
        )
        zones: list[list[int]] = []
        anchor_bins: dict[tuple[int, int], list[int]] = {}

        def xy(index):
            return (
                float(work.at[index, longitude_col]) * meters_per_lon,
                float(work.at[index, latitude_col]) * meters_per_lat,
            )

        for index in ordered.index:
            x, y = xy(index)
            bx, by = int(math.floor(x / cell)), int(math.floor(y / cell))
            candidate_zone_indices = set()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    candidate_zone_indices.update(
                        anchor_bins.get((bx + dx, by + dy), ())
                    )

            compatible = []
            for zone_index in sorted(candidate_zone_indices):
                members = work.loc[zones[zone_index]]
                distances_m = 1000.0 * haversine_km(
                    float(work.at[index, latitude_col]),
                    float(work.at[index, longitude_col]),
                    members[latitude_col].to_numpy(float),
                    members[longitude_col].to_numpy(float),
                )
                maximum = float(distances_m.max()) if len(distances_m) else 0.0
                if maximum <= threshold:
                    compatible.append((maximum, zone_index))
            if compatible:
                zone_index = min(compatible)[1]
                zones[zone_index].append(index)
            else:
                zone_index = len(zones)
                zones.append([index])
                anchor_bins.setdefault((bx, by), []).append(zone_index)

        safe_area = re.sub(r"[^A-Za-z0-9_-]+", "-", str(area)).strip("-") or "1"
        for zone_number, indices in enumerate(zones, start=1):
            members = work.loc[indices]
            priority = float(members[score_col].max())
            representative = members.sort_values(
                [score_col, id_col], ascending=[False, True], kind="mergesort"
            ).iloc[0]
            distances_m = 1000.0 * haversine_km(
                float(representative[latitude_col]),
                float(representative[longitude_col]),
                members[latitude_col].to_numpy(float),
                members[longitude_col].to_numpy(float),
            )
            rows.append(
                {
                    "zone_id": f"{safe_area}-Z{zone_number:03d}",
                    area_col: area,
                    "zone_score": round(0.90 * priority, 6),
                    "zone_member_count": int(len(members)),
                    "zone_radius_m": round(
                        float(distances_m.max()) if len(distances_m) else 0.0, 1
                    ),
                    "zone_merge_threshold_m": threshold,
                    "representative_site_id": representative[id_col],
                    "latitude": float(representative[latitude_col]),
                    "longitude": float(representative[longitude_col]),
                    "zone_member_site_ids": ";".join(
                        members[id_col].astype(str).tolist()
                    ),
                }
            )
    zones = pd.DataFrame(rows)
    if zones.empty:
        return zones
    zones = zones.sort_values(
        ["zone_score", "zone_id"],
        ascending=[False, True],
        kind="mergesort",
    ).reset_index(drop=True)
    zones["zone_rank"] = np.arange(1, len(zones) + 1)
    return zones


def _zone_coverage_masks(universe, zones, detections, radius_km):
    detection_rows = detections.reset_index(drop=True)
    masks = []
    sizes = []
    for _, zone in zones.iterrows():
        member_ids = patch.member_indices(zone)
        members = universe.loc[member_ids]
        island = str(zone["survey_area_id"])
        mask = 0
        for detection_index, point in detection_rows.iterrows():
            if str(point["island"]) != island or members.empty:
                continue
            distances = haversine_km(
                float(point["latitude"]),
                float(point["longitude"]),
                members["lat"].to_numpy(float),
                members["lon"].to_numpy(float),
            )
            if bool(np.any(distances <= float(radius_km))):
                mask |= 1 << int(detection_index)
        masks.append(mask)
        sizes.append(int(len(member_ids)))
    return detection_rows, np.asarray(masks, dtype=object), np.asarray(sizes, dtype=int)


def fast_prefix_patch_frontier(universe, zones, detections, radius_km):
    if zones is None or zones.empty:
        return None
    ordered = zones.sort_values(
        ["zone_score", "zone_id"], ascending=[False, True], kind="mergesort"
    ).reset_index(drop=True)
    detection_rows, masks, _ = _zone_coverage_masks(
        universe, ordered, detections, radius_km
    )
    earliest = np.full(len(detection_rows), np.inf)
    for zone_position, mask in enumerate(masks, start=1):
        mask_int = int(mask)
        for detection_index in range(len(detection_rows)):
            if np.isfinite(earliest[detection_index]):
                continue
            if mask_int & (1 << detection_index):
                earliest[detection_index] = zone_position
    if not np.isfinite(earliest).all():
        return None
    n_patches = int(np.max(earliest))
    selected_zones = ordered.iloc[:n_patches].copy()
    selected_indices = set()
    for _, zone in selected_zones.iterrows():
        selected_indices.update(patch.member_indices(zone))
    chosen = universe.loc[sorted(selected_indices)]
    result = evaluate(chosen, detections, radius_km)
    if result["recovered"] != len(detections):
        raise RuntimeError("fast patch-prefix calculation failed its exact recovery audit")
    island_patch_counts = (
        selected_zones["survey_area_id"].astype(str).value_counts().to_dict()
    )
    return {
        "n_patches": n_patches,
        "n_cells": int(len(selected_indices)),
        "grid_fraction": float(len(selected_indices) / len(universe)),
        "estimated_cell_area_km2": float(len(selected_indices) * 0.01),
        "island_patch_counts": {str(k): int(v) for k, v in island_patch_counts.items()},
        "selected_zone_ids": selected_zones["zone_id"].astype(str).tolist(),
        **result,
    }


def fast_random_patch_audit(
    universe,
    zones,
    detections,
    observed,
    radius_km,
    iterations,
    seed,
):
    """Exact random-patch estimand using precomputed patch coverage bitmasks."""
    rng = np.random.default_rng(seed)
    detection_rows, masks, sizes = _zone_coverage_masks(
        universe, zones.reset_index(drop=True), detections, radius_km
    )
    groups = {}
    for zone_index, zone in zones.reset_index(drop=True).iterrows():
        groups.setdefault(str(zone["survey_area_id"]), []).append(int(zone_index))

    recoveries = np.zeros(int(iterations), dtype=int)
    cell_counts = np.zeros(int(iterations), dtype=int)
    evaluated = 0
    for _ in range(int(iterations)):
        coverage_mask = 0
        cells = 0
        feasible = True
        for island, count in observed["island_patch_counts"].items():
            pool = np.asarray(groups.get(str(island), []), dtype=int)
            if len(pool) < int(count):
                feasible = False
                break
            chosen = rng.choice(pool, size=int(count), replace=False)
            for zone_index in chosen:
                coverage_mask |= int(masks[int(zone_index)])
                cells += int(sizes[int(zone_index)])
        if not feasible:
            continue
        recoveries[evaluated] = int(coverage_mask.bit_count())
        cell_counts[evaluated] = int(cells)
        evaluated += 1

    recoveries = recoveries[:evaluated]
    cell_counts = cell_counts[:evaluated]
    if not evaluated:
        return {
            "iterations_requested": int(iterations),
            "iterations_evaluated": 0,
            "complete_recovery_probability": None,
            "mean_recovered": None,
            "mean_cells": None,
            "q05_cells": None,
            "q95_cells": None,
        }
    return {
        "iterations_requested": int(iterations),
        "iterations_evaluated": int(evaluated),
        "complete_recovery_probability": float(
            np.mean(recoveries == len(detection_rows))
        ),
        "mean_recovered": float(np.mean(recoveries)),
        "mean_cells": float(np.mean(cell_counts)),
        "q05_cells": float(np.quantile(cell_counts, 0.05)),
        "q95_cells": float(np.quantile(cell_counts, 0.95)),
    }


if __name__ == "__main__":
    patch.aggregate_candidates_to_zones = fast_complete_link_zones
    patch.prefix_patch_frontier = fast_prefix_patch_frontier
    patch.random_patch_audit = fast_random_patch_audit
    patch.SUPPORT_FRACTIONS = (0.0381, 0.05, 0.075, 0.10)
    patch.MERGE_DISTANCES_M = (500.0, 1000.0)
    patch.main()
