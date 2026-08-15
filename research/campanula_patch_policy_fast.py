#!/usr/bin/env python3
"""Run Campanula patch-policy evaluation with cached exact patch coverage."""
from __future__ import annotations

import numpy as np

import campanula_patch_policy as policy
from campanula_persistent_patch_hash import _zone_coverage_masks
from campanula_worldcover_discovery import evaluate


_original_oracle = policy.exact_oracle_set_cover
_coverage_cache = {}


def json_safe_oracle(*args, **kwargs):
    result = _original_oracle(*args, **kwargs)
    if result is not None and "island_patch_counts" in result:
        result["island_patch_counts"] = {
            str(key): int(value)
            for key, value in result["island_patch_counts"].items()
        }
    return result


def cached_prefix(universe, ranked_zones, detections, radius_km):
    if ranked_zones is None or ranked_zones.empty:
        return None
    zone_ids = tuple(sorted(ranked_zones["zone_id"].astype(str).tolist()))
    cache_key = (zone_ids, float(radius_km))
    if cache_key not in _coverage_cache:
        canonical = ranked_zones.sort_values("zone_id", kind="mergesort").reset_index(drop=True)
        detection_rows, masks, _ = _zone_coverage_masks(
            universe, canonical, detections, radius_km
        )
        mask_by_id = {
            str(zone_id): int(mask)
            for zone_id, mask in zip(canonical["zone_id"].astype(str), masks)
        }
        _coverage_cache[cache_key] = (detection_rows, mask_by_id)
    detection_rows, mask_by_id = _coverage_cache[cache_key]

    ordered = ranked_zones.sort_values(
        ["zone_score", "zone_id"], ascending=[False, True], kind="mergesort"
    ).reset_index(drop=True)
    earliest = np.full(len(detection_rows), np.inf)
    for position, zone in ordered.iterrows():
        mask = mask_by_id[str(zone["zone_id"])]
        for detection_index in range(len(detection_rows)):
            if np.isfinite(earliest[detection_index]):
                continue
            if mask & (1 << detection_index):
                earliest[detection_index] = position + 1
    if not np.isfinite(earliest).all():
        return None
    n_patches = int(np.max(earliest))
    selected_zones = ordered.iloc[:n_patches].copy()
    selected_indices = set()
    for _, zone in selected_zones.iterrows():
        selected_indices.update(policy.patch.member_indices(zone))
    chosen = universe.loc[sorted(selected_indices)]
    result = evaluate(chosen, detections, radius_km)
    if result["recovered"] != len(detections):
        raise RuntimeError("cached patch-prefix evaluation failed exact audit")
    island_counts = selected_zones["survey_area_id"].astype(str).value_counts().to_dict()
    return {
        "n_patches": n_patches,
        "n_cells": int(len(selected_indices)),
        "grid_fraction": float(len(selected_indices) / len(universe)),
        "estimated_cell_area_km2": float(len(selected_indices) * 0.01),
        "island_patch_counts": {str(k): int(v) for k, v in island_counts.items()},
        "selected_zone_ids": selected_zones["zone_id"].astype(str).tolist(),
        **result,
    }


if __name__ == "__main__":
    policy.fast_prefix_patch_frontier = cached_prefix
    policy.exact_oracle_set_cover = json_safe_oracle
    policy.main()
