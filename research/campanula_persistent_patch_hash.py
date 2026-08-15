#!/usr/bin/env python3
"""Run persistent-patch development with an exact complete-link spatial hash.

The original ACSP zone aggregator tests every existing zone for every new cell.
Complete-link compatibility implies that a compatible zone's first member must
itself lie within the merge threshold. We therefore spatial-hash only those
zone anchors, then retain the original exact haversine maximum-distance test and
same `(maximum distance, zone index)` tie-break. This changes search cost, not
the patch definition.
"""
from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd

import campanula_persistent_patch as patch
from campanula_worldcover_discovery import haversine_km


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
                    candidate_zone_indices.update(anchor_bins.get((bx + dx, by + dy), ()))

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
                    "zone_radius_m": round(float(distances_m.max()) if len(distances_m) else 0.0, 1),
                    "zone_merge_threshold_m": threshold,
                    "representative_site_id": representative[id_col],
                    "latitude": float(representative[latitude_col]),
                    "longitude": float(representative[longitude_col]),
                    "zone_member_site_ids": ";".join(members[id_col].astype(str).tolist()),
                }
            )
    zones = pd.DataFrame(rows)
    if zones.empty:
        return zones
    zones = zones.sort_values(["zone_score", "zone_id"], ascending=[False, True], kind="mergesort").reset_index(drop=True)
    zones["zone_rank"] = np.arange(1, len(zones) + 1)
    return zones


if __name__ == "__main__":
    patch.aggregate_candidates_to_zones = fast_complete_link_zones
    patch.SUPPORT_FRACTIONS = (0.0381, 0.05, 0.075, 0.10)
    patch.MERGE_DISTANCES_M = (500.0, 1000.0)
    patch.main()
