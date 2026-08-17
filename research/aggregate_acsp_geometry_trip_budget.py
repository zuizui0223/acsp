#!/usr/bin/env python3
"""Aggregate outcome-free ACSP geometry-to-field-day operational validation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

EXPECTED_PROTOCOL = "6bd7c35e2e3de369088691ebe8861d0578f5933374895fe06cb390bfe9a4383f"
PRIMARY_HUB = "cell_centroid_snapped_to_nearest_land_grid_point"


def canonical(path: Path) -> tuple[dict, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    if expected != calculated or calculated != EXPECTED_PROTOCOL:
        raise ValueError("geometry trip-budget protocol fingerprint mismatch")
    payload["protocol_fingerprint"] = expected
    return payload, calculated


def describe(values) -> dict:
    arr = np.asarray(list(values), dtype=float)
    return {
        "n": int(len(arr)),
        "min": float(np.min(arr)),
        "median": float(np.median(arr)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    protocol, fingerprint = canonical(args.protocol)
    expected_islands = {str(row["island_id"]) for row in protocol["island_cells"]}
    summaries = []
    day_frames = []
    fixed_frames = []
    for path in sorted(args.input.glob("**/island_summary.json")):
        summary = json.loads(path.read_text(encoding="utf-8"))
        if summary.get("protocol_fingerprint") != fingerprint:
            raise ValueError(f"protocol mismatch in {path}")
        summaries.append(summary)
    for path in sorted(args.input.glob("**/day_budget_results.csv")):
        frame = pd.read_csv(path)
        if len(frame):
            day_frames.append(frame)
    for path in sorted(args.input.glob("**/fixed_k5_trip_results.csv")):
        frame = pd.read_csv(path)
        if len(frame):
            fixed_frames.append(frame)

    found = [str(row["island_id"]) for row in summaries]
    duplicates = sorted({name for name in found if found.count(name) > 1})
    found_set = set(found)
    missing = sorted(expected_islands - found_set)
    unexpected = sorted(found_set - expected_islands)
    day = pd.concat(day_frames, ignore_index=True) if day_frames else pd.DataFrame()
    fixed = pd.concat(fixed_frames, ignore_index=True) if fixed_frames else pd.DataFrame()

    primary = day[day["hub_proxy"].eq(PRIMARY_HUB)].copy() if len(day) else pd.DataFrame()
    day_summary = {}
    for target in map(int, protocol["budget_translation"]["target_days"]):
        sub = primary[primary["target_days"].eq(target)]
        day_summary[str(target)] = {
            "selected_k": describe(sub["k"]) if len(sub) else {},
            "coverage_fraction": describe(sub["coverage_fraction"]) if len(sub) else {},
            "estimated_road_km": describe(sub["estimated_road_km"].dropna()) if len(sub) and sub["estimated_road_km"].notna().any() else {},
            "total_hours": describe(sub["total_hours"].dropna()) if len(sub) and sub["total_hours"].notna().any() else {},
            "all_fit": bool(sub["fits_target_days"].fillna(False).all()) if len(sub) else False,
        }

    hub_sensitivity = {}
    for target in map(int, protocol["budget_translation"]["target_days"]):
        sub = day[day["target_days"].eq(target)] if len(day) else pd.DataFrame()
        if sub.empty:
            hub_sensitivity[str(target)] = {}
            continue
        grouped = sub.groupby("island_id").agg(
            min_k=("k", "min"), max_k=("k", "max"),
            min_coverage=("coverage_fraction", "min"), max_coverage=("coverage_fraction", "max"),
        )
        k_width = grouped["max_k"] - grouped["min_k"]
        coverage_width = grouped["max_coverage"] - grouped["min_coverage"]
        hub_sensitivity[str(target)] = {
            "k_range_across_hubs": describe(k_width),
            "coverage_range_across_hubs": describe(coverage_width),
            "islands_with_k_change": int((k_width > 0).sum()),
        }

    fixed_primary = fixed[fixed["hub_proxy"].eq(PRIMARY_HUB)].copy() if len(fixed) else pd.DataFrame()
    fixed_k5 = {
        "estimated_days": describe(fixed_primary["estimated_days"]) if len(fixed_primary) else {},
        "total_hours": describe(fixed_primary["total_hours"].dropna()) if len(fixed_primary) and fixed_primary["total_hours"].notna().any() else {},
        "estimated_road_km": describe(fixed_primary["estimated_road_km"].dropna()) if len(fixed_primary) and fixed_primary["estimated_road_km"].notna().any() else {},
        "islands_fitting_one_day": int((fixed_primary["estimated_days"] <= 1).sum()) if len(fixed_primary) else 0,
        "islands_requiring_more_than_one_day": int((fixed_primary["estimated_days"] > 1).sum()) if len(fixed_primary) else 0,
    }

    per_island_contract = {str(row["island_id"]): bool(row.get("island_operational_contract_pass", False)) for row in summaries}
    taxon_free = all(
        row.get("taxon_occurrences_used") is False
        and row.get("taxon_outcomes_used") is False
        and row.get("environmental_support_modifier_used") is False
        for row in summaries
    )
    all_primary_fit = bool(len(primary) == len(expected_islands) * len(protocol["budget_translation"]["target_days"]) and primary["fits_target_days"].fillna(False).all())
    all_contract = bool(
        not missing and not unexpected and not duplicates
        and len(summaries) == int(protocol["operational_contract"]["all_islands_required"])
        and all(per_island_contract.values())
        and all_primary_fit
        and taxon_free
    )

    summary = {
        "status": "operational_geometry_trip_budget_complete",
        "protocol_fingerprint": fingerprint,
        "islands_expected": int(len(expected_islands)),
        "islands_completed": int(len(found_set)),
        "missing_islands": missing,
        "unexpected_islands": unexpected,
        "duplicate_islands": duplicates,
        "day_budget_primary_hub": day_summary,
        "hub_proxy_sensitivity": hub_sensitivity,
        "fixed_k5_across_islands": fixed_k5,
        "per_island_contract": per_island_contract,
        "all_primary_day_prefixes_fit": all_primary_fit,
        "taxon_and_environment_modifier_free": taxon_free,
        "operational_contract_pass": all_contract,
        "interpretation": (
            "Geometry-only fine-scale coverage can be translated to field-day budgets with the production trip estimator. "
            "This is an operational proxy benchmark; it is not a road-network, access, detection, or biological-superiority validation."
            if all_contract else
            "The geometry-to-day operational translation did not satisfy its predeclared feasibility/monotonicity contract on every island."
        ),
        "frozen_192_consumed": False,
    }

    args.out.mkdir(parents=True, exist_ok=True)
    primary.to_csv(args.out / "primary_hub_day_budget_results.csv", index=False)
    day.to_csv(args.out / "all_hub_day_budget_results.csv", index=False)
    fixed.to_csv(args.out / "all_hub_fixed_k5_results.csv", index=False)
    pd.DataFrame(summaries).to_json(args.out / "island_summaries.jsonl", orient="records", lines=True)
    (args.out / "geometry_trip_budget_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
