#!/usr/bin/env python3
"""Evaluate geometry-only ACSP survey coverage under 1-5 day field budgets.

No taxon occurrence or outcome is read. The geometry-only max-coverage order is
fixed first; the production trip estimator is then used only as a downstream
budget translator. Route estimates never reorder the coverage sequence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np
import pandas as pd

from acsp_discover import infer_survey_protocol
from develop_izu_strong_coverage_comparator import build_geometry
from fast_max_coverage import SparseCoverageIndex
from gbif_fieldmap_builder_app import estimate_default_short_trip
from run_acsp_cross_island_confirmation_island import build_grid

EXPECTED_PROTOCOL = "6bd7c35e2e3de369088691ebe8861d0578f5933374895fe06cb390bfe9a4383f"
PRIMARY_HUB = "cell_centroid_snapped_to_nearest_land_grid_point"


def canonical(path: Path) -> tuple[dict, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    if expected != calculated or calculated != EXPECTED_PROTOCOL:
        raise ValueError(
            f"protocol fingerprint mismatch: file={expected} calculated={calculated} expected={EXPECTED_PROTOCOL}"
        )
    payload["protocol_fingerprint"] = expected
    return payload, calculated


def coverage_curve(index: SparseCoverageIndex, selected: pd.DataFrame, n_grid: int) -> np.ndarray:
    covered = np.zeros(int(n_grid), dtype=bool)
    curve: list[float] = []
    for raw_idx in selected["_global_idx"].to_numpy(int):
        start = index.adjacency.indptr[raw_idx]
        stop = index.adjacency.indptr[raw_idx + 1]
        covered[index.adjacency.indices[start:stop]] = True
        curve.append(float(covered.mean()))
    return np.asarray(curve, dtype=float)


def proxy_targets(bounds: tuple[float, float, float, float]) -> dict[str, tuple[float, float]]:
    west, south, east, north = bounds
    mid_lon = (west + east) / 2.0
    mid_lat = (south + north) / 2.0
    return {
        PRIMARY_HUB: (mid_lat, mid_lon),
        "west_quarter_midlat_snapped_to_nearest_land_grid_point": (mid_lat, west + 0.25 * (east - west)),
        "east_quarter_midlat_snapped_to_nearest_land_grid_point": (mid_lat, west + 0.75 * (east - west)),
        "midlon_south_quarter_snapped_to_nearest_land_grid_point": (south + 0.25 * (north - south), mid_lon),
        "midlon_north_quarter_snapped_to_nearest_land_grid_point": (south + 0.75 * (north - south), mid_lon),
    }


def snap_to_grid(grid: pd.DataFrame, target_lat: float, target_lon: float) -> tuple[float, float, int]:
    lat = grid["lat"].to_numpy(float)
    lon = grid["lon"].to_numpy(float)
    cos_lat = math.cos(math.radians(float(target_lat)))
    distance2 = np.square(lat - float(target_lat)) + np.square((lon - float(target_lon)) * cos_lat)
    idx = int(np.argmin(distance2))
    return float(lat[idx]), float(lon[idx]), idx


def make_plan(selected: pd.DataFrame, k: int) -> pd.DataFrame:
    prefix = selected.iloc[: int(k)].copy().reset_index(drop=True)
    return pd.DataFrame(
        {
            "site_id": np.arange(1, len(prefix) + 1, dtype=int),
            "survey_area_id": np.ones(len(prefix), dtype=int),
            "latitude": prefix["lat"].to_numpy(float),
            "longitude": prefix["lon"].to_numpy(float),
        }
    )


def trip_row(
    selected: pd.DataFrame,
    coverage: np.ndarray,
    *,
    k: int,
    hub_name: str,
    hub_lat: float,
    hub_lon: float,
    target_days: int,
    survey_protocol: dict,
) -> dict:
    plan = make_plan(selected, int(k))
    trip = estimate_default_short_trip(
        plan,
        float(hub_lat),
        float(hub_lon),
        survey_protocol=survey_protocol,
        target_days=int(target_days),
    )
    return {
        "hub_proxy": hub_name,
        "target_days": int(target_days),
        "k": int(k),
        "coverage_fraction": float(coverage[int(k) - 1]),
        "fits_target_days": bool(trip.get("fits_target_days", False)),
        "estimated_days": int(trip.get("estimated_days", 0)),
        "overtime_days": int(trip.get("overtime_days", 0)),
        "estimated_road_km": float(trip.get("estimated_road_km", np.nan)),
        "estimated_transit_km": float(trip.get("estimated_transit_km", np.nan)),
        "travel_hours": float(trip.get("travel_hours", np.nan)),
        "site_hours": float(trip.get("site_hours", np.nan)),
        "total_hours": float(trip.get("total_hours", np.nan)),
        "inter_area_transfers": int(trip.get("inter_area_transfers", 0)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--island", required=True)
    parser.add_argument("--dem", type=Path, required=True)
    parser.add_argument("--layer-manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    protocol, fingerprint = canonical(args.protocol)
    cells = {str(row["island_id"]): row for row in protocol["island_cells"]}
    if args.island not in cells:
        raise KeyError(args.island)
    cell = cells[args.island]
    bounds = tuple(float(cell[key]) for key in ("west", "south", "east", "north"))

    layer = json.loads(args.layer_manifest.read_text(encoding="utf-8"))
    if layer["protocol_fingerprint"] != fingerprint or layer["island_id"] != args.island:
        raise ValueError("public-layer manifest does not match protocol/island")
    if layer["taxon_occurrences_read"] is not False or layer["taxon_outcomes_read"] is not False:
        raise ValueError("outcome-free operational boundary violated")

    grid, _surface = build_grid(
        args.dem,
        args.island,
        bounds,
        float(protocol["candidate_surface"]["candidate_grid_m"]),
    )
    if grid.empty:
        raise RuntimeError("empty land grid")
    grid = grid.copy()
    grid["_global_idx"] = np.arange(len(grid), dtype=int)
    geometry = build_geometry(grid)
    radius = float(protocol["fine_scale_selector"]["design_radius_km"])
    max_sites = min(int(protocol["fine_scale_selector"]["max_sites"]), len(grid))

    select_start = time.perf_counter()
    sparse = SparseCoverageIndex.from_geometry(grid, geometry, radius)
    selected = sparse.select(grid, np.ones(len(grid), dtype=bool), max_budget=max_sites)
    selection_seconds = float(time.perf_counter() - select_start)
    if len(selected) != max_sites:
        raise RuntimeError(f"geometry selector returned {len(selected)} sites, expected {max_sites}")
    coverage = coverage_curve(sparse, selected, len(grid))

    survey = infer_survey_protocol({"kingdom": "Plantae"}).as_dict()
    expected_field = protocol["field_protocol"]
    assertions = {
        "protocol_id": survey["protocol_id"] == expected_field["required_protocol_id"],
        "daily_field_hours": float(survey["daily_field_hours"]) == float(expected_field["required_daily_field_hours"]),
        "search_minutes_per_cell": int(survey["search_minutes_per_cell"]) == int(expected_field["required_search_minutes_per_cell"]),
        "access_buffer_minutes_per_cell": int(survey["access_buffer_minutes_per_cell"]) == int(expected_field["required_access_buffer_minutes_per_cell"]),
        "minimum_repeat_visits": int(survey["minimum_repeat_visits"]) == int(expected_field["required_minimum_repeat_visits"]),
    }
    if not all(assertions.values()):
        raise RuntimeError(f"production plant survey protocol drifted: {assertions}")

    targets = proxy_targets(bounds)
    declared_hubs = list(protocol["hub_proxy"]["sensitivity"])
    if set(targets) != set(declared_hubs):
        raise RuntimeError("hub proxy implementation does not match protocol")
    hubs = {}
    for name in declared_hubs:
        target_lat, target_lon = targets[name]
        hub_lat, hub_lon, grid_index = snap_to_grid(grid, target_lat, target_lon)
        hubs[name] = {"latitude": hub_lat, "longitude": hub_lon, "grid_index": grid_index}

    prefix_rows: list[dict] = []
    chosen_rows: list[dict] = []
    trip_start = time.perf_counter()
    for hub_name in declared_hubs:
        hub = hubs[hub_name]
        for day in map(int, protocol["budget_translation"]["target_days"]):
            candidates = []
            for k in range(1, max_sites + 1):
                row = trip_row(
                    selected,
                    coverage,
                    k=k,
                    hub_name=hub_name,
                    hub_lat=hub["latitude"],
                    hub_lon=hub["longitude"],
                    target_days=day,
                    survey_protocol=survey,
                )
                row.update({"island_id": args.island, "hub_latitude": hub["latitude"], "hub_longitude": hub["longitude"]})
                prefix_rows.append(row)
                if row["fits_target_days"]:
                    candidates.append(row)
            if candidates:
                chosen = dict(max(candidates, key=lambda item: item["k"]))
                chosen["status"] = "ok"
            else:
                chosen = {
                    "island_id": args.island,
                    "hub_proxy": hub_name,
                    "target_days": day,
                    "k": 0,
                    "coverage_fraction": 0.0,
                    "fits_target_days": False,
                    "status": "no_prefix_fits",
                }
            chosen_rows.append(chosen)
    trip_seconds = float(time.perf_counter() - trip_start)

    chosen = pd.DataFrame(chosen_rows)
    primary = chosen[chosen["hub_proxy"].eq(PRIMARY_HUB)].sort_values("target_days").copy()
    k_values = primary["k"].to_numpy(int)
    coverage_values = primary["coverage_fraction"].to_numpy(float)
    k_monotone = bool(np.all(np.diff(k_values) >= 0))
    coverage_monotone = bool(np.all(np.diff(coverage_values) >= -1e-12))
    all_primary_fit = bool(primary["fits_target_days"].fillna(False).all())

    # K=5 is retained only as a diagnostic illustrating why fixed site count is
    # not an equal operational budget across islands.
    fixed_k = min(5, max_sites)
    fixed_k_rows = []
    for hub_name in declared_hubs:
        hub = hubs[hub_name]
        row = trip_row(
            selected,
            coverage,
            k=fixed_k,
            hub_name=hub_name,
            hub_lat=hub["latitude"],
            hub_lon=hub["longitude"],
            target_days=max(map(int, protocol["budget_translation"]["target_days"])),
            survey_protocol=survey,
        )
        row.update({"island_id": args.island})
        fixed_k_rows.append(row)

    hub_sensitivity = {}
    for day in map(int, protocol["budget_translation"]["target_days"]):
        sub = chosen[chosen["target_days"].eq(day)]
        hub_sensitivity[str(day)] = {
            "min_k": int(sub["k"].min()),
            "max_k": int(sub["k"].max()),
            "k_range": int(sub["k"].max() - sub["k"].min()),
            "min_coverage_fraction": float(sub["coverage_fraction"].min()),
            "max_coverage_fraction": float(sub["coverage_fraction"].max()),
            "coverage_range": float(sub["coverage_fraction"].max() - sub["coverage_fraction"].min()),
        }

    summary = {
        "status": "operational_trip_budget_complete",
        "protocol_fingerprint": fingerprint,
        "island_id": args.island,
        "candidate_grid_cells": int(len(grid)),
        "geometry_sites_generated": int(len(selected)),
        "final_geometry_coverage_fraction": float(coverage[-1]),
        "geometry_selection_runtime_seconds": selection_seconds,
        "trip_evaluation_runtime_seconds": trip_seconds,
        "field_protocol": survey,
        "field_protocol_assertions": assertions,
        "hub_proxies": hubs,
        "primary_day_results": primary.to_dict("records"),
        "hub_sensitivity": hub_sensitivity,
        "fixed_k5_primary_hub": next(row for row in fixed_k_rows if row["hub_proxy"] == PRIMARY_HUB),
        "primary_k_monotone": k_monotone,
        "primary_coverage_monotone": coverage_monotone,
        "all_primary_day_prefixes_fit": all_primary_fit,
        "island_operational_contract_pass": bool(k_monotone and coverage_monotone and all_primary_fit),
        "taxon_occurrences_used": False,
        "taxon_outcomes_used": False,
        "environmental_support_modifier_used": False,
    }

    args.out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(prefix_rows).to_csv(args.out / "trip_prefix_audit.csv", index=False)
    chosen.to_csv(args.out / "day_budget_results.csv", index=False)
    pd.DataFrame(fixed_k_rows).to_csv(args.out / "fixed_k5_trip_results.csv", index=False)
    selected.to_csv(args.out / "geometry_coverage_order.csv", index=False)
    (args.out / "island_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
