#!/usr/bin/env python3
"""Use Campanula field detections as development labels, not validation.

The candidate pool is ordered without reading 2026 field outcomes. Only after
that outcome-free order is fixed are the 19 detection clusters read. The field
labels then define a development-only set-cover oracle and prefix recovery
curve. The oracle is a diagnostic target, never an inference-time policy.

If a real travel matrix is supplied, ACSP also infers the recommended effort
from explicitly allowed human movement modes. No straight-line routing fallback
is used in that mode.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from acsp.auto_budget import infer_recommended_effort_from_matrix
from acsp.coverage import select_maximum_coverage_sites
from acsp.field_validation import detection_recovery_table, haversine_distance_m, recovery_summary
from acsp.travel_matrix import read_travel_time_matrix

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POOL = ROOT / "field_validation/campanula_microdonta/development_data/candidate_pool.csv"
DEFAULT_DETECTIONS = ROOT / "field_validation/campanula_microdonta/development_data/detection_clusters.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-pool", default=str(DEFAULT_POOL))
    parser.add_argument("--detections", default=str(DEFAULT_DETECTIONS))
    parser.add_argument("--output-dir", default="campanula_inverse_effort_development")
    parser.add_argument("--coverage-radius-km", type=float, default=1.0)
    parser.add_argument("--recovery-radius-km", type=float, default=1.0)
    parser.add_argument("--travel-matrix")
    parser.add_argument("--hub-id", default="__hub__")
    parser.add_argument(
        "--allowed-mode",
        action="append",
        dest="allowed_modes",
        help="Explicitly available movement mode; repeat for walk/road/trail/ferry as applicable.",
    )
    parser.add_argument("--undirected-travel-matrix", action="store_true")
    return parser.parse_args()


def plant_protocol() -> dict[str, object]:
    return {
        "daily_field_hours": 8.0,
        "search_minutes_per_cell": 30,
        "access_buffer_minutes_per_cell": 10,
        "protocol_id": "campanula_inverse_development_v1",
        "taxon_group": "plant",
        "surface_domain": "terrestrial",
    }


def prefix_recovery_curve(
    ordered: pd.DataFrame,
    detections: pd.DataFrame,
    *,
    radius_km: float,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for k in range(1, len(ordered) + 1):
        prefix = ordered.iloc[:k].copy()
        recovery = detection_recovery_table(
            prefix,
            detections,
            radii_km=(float(radius_km),),
            candidate_id_col="site_id",
            area_col="survey_area_id",
            detection_area_col="island",
        )
        summary = recovery_summary(recovery, radii_km=(float(radius_km),)).iloc[0]
        rows.append(
            {
                "k": int(k),
                "cumulative_coverage_fraction": float(prefix["cumulative_coverage_fraction"].iloc[-1]),
                "n_recovered_clusters": int(summary["n_recovered"]),
                "detection_recall": float(summary["detection_recall"]),
            }
        )
    curve = pd.DataFrame(rows)
    curve["marginal_recovered_clusters"] = curve["n_recovered_clusters"].diff().fillna(
        curve["n_recovered_clusters"]
    ).astype(int)
    return curve


def candidate_detection_masks(
    pool: pd.DataFrame,
    detections: pd.DataFrame,
    *,
    radius_km: float,
) -> tuple[list[int], list[str], int]:
    """Return field-label coverage bitmasks for the development oracle."""
    masks: list[int] = []
    site_ids: list[str] = []
    for pos, candidate in pool.reset_index(drop=True).iterrows():
        if "survey_area_id" in pool.columns and "island" in detections.columns:
            area = str(candidate["survey_area_id"]).strip().lower()
            subset = detections[detections["island"].astype(str).str.strip().str.lower().eq(area)]
        else:
            subset = detections
        mask = 0
        if not subset.empty:
            distances = haversine_distance_m(
                float(candidate["latitude"]),
                float(candidate["longitude"]),
                subset["latitude"].to_numpy(float),
                subset["longitude"].to_numpy(float),
            ) / 1000.0
            for local_pos, (_, detection) in enumerate(subset.iterrows()):
                if float(distances[local_pos]) <= float(radius_km):
                    bit = int(detection["_oracle_bit"])
                    mask |= 1 << bit
        if mask:
            masks.append(mask)
            site_ids.append(str(candidate.get("site_id", pos + 1)))
    target = 0
    for mask in masks:
        target |= mask
    return masks, site_ids, target


def greedy_upper_bound(masks: list[int], target: int) -> list[int]:
    covered = 0
    chosen: list[int] = []
    unused = set(range(len(masks)))
    while covered != target:
        best = max(unused, key=lambda i: ((masks[i] & ~covered).bit_count(), -i))
        gain = (masks[best] & ~covered).bit_count()
        if gain == 0:
            break
        chosen.append(best)
        covered |= masks[best]
        unused.remove(best)
    return chosen


def exact_set_cover(masks: list[int], target: int) -> list[int]:
    """Exact branch-and-bound set cover for at most 19 development clusters."""
    if target == 0:
        return []
    # Deduplicate identical coverage masks while retaining one representative.
    representative: dict[int, int] = {}
    for index, mask in enumerate(masks):
        representative.setdefault(mask, index)
    unique_masks = list(representative)
    original_index = [representative[mask] for mask in unique_masks]

    greedy_unique = greedy_upper_bound(unique_masks, target)
    if not greedy_unique:
        return []
    best = list(greedy_unique)
    seen_depth: dict[int, int] = {0: 0}

    bits = [bit for bit in range(target.bit_length()) if target & (1 << bit)]
    covering: dict[int, list[int]] = {
        bit: [i for i, mask in enumerate(unique_masks) if mask & (1 << bit)] for bit in bits
    }

    def search(covered: int, chosen: list[int]) -> None:
        nonlocal best
        if covered == target:
            if len(chosen) < len(best):
                best = list(chosen)
            return
        if len(chosen) >= len(best):
            return
        previous = seen_depth.get(covered)
        if previous is not None and previous < len(chosen):
            return
        seen_depth[covered] = len(chosen)

        uncovered = target & ~covered
        max_gain = max((mask & uncovered).bit_count() for mask in unique_masks)
        if max_gain <= 0:
            return
        lower_bound = math.ceil(uncovered.bit_count() / max_gain)
        if len(chosen) + lower_bound >= len(best):
            return

        uncovered_bits = [bit for bit in bits if uncovered & (1 << bit)]
        pivot = min(
            uncovered_bits,
            key=lambda bit: sum(1 for i in covering[bit] if unique_masks[i] & uncovered),
        )
        options = [i for i in covering[pivot] if unique_masks[i] & uncovered]
        options.sort(key=lambda i: (unique_masks[i] & uncovered).bit_count(), reverse=True)
        for index in options:
            if index in chosen:
                continue
            search(covered | unique_masks[index], [*chosen, index])

    search(0, [])
    return [original_index[i] for i in best]


def development_oracle(
    pool: pd.DataFrame,
    detections: pd.DataFrame,
    *,
    radius_km: float,
) -> dict[str, object]:
    work = detections.copy().reset_index(drop=True)
    work["_oracle_bit"] = np.arange(len(work), dtype=int)
    masks, site_ids, target = candidate_detection_masks(pool, work, radius_km=radius_km)
    reachable_bits = target.bit_count()
    unreachable = [
        int(work.loc[bit, "detection_cluster_id"])
        for bit in range(len(work))
        if not (target & (1 << bit))
    ]
    chosen = exact_set_cover(masks, target)
    chosen_site_ids = [site_ids[index] for index in chosen]
    return {
        "reachable_detection_clusters": int(reachable_bits),
        "unreachable_detection_cluster_ids": unreachable,
        "exact_minimum_sites_for_reachable_clusters": int(len(chosen_site_ids)),
        "oracle_site_ids": chosen_site_ids,
        "oracle_uses_field_labels": True,
        "oracle_role": "development_lower_bound_not_deployable_policy",
    }


def main() -> None:
    args = parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)

    pool = pd.read_csv(args.candidate_pool, dtype={"site_id": "string"})
    if pool.empty:
        raise ValueError("candidate pool is empty")

    # Outcome-free stage: use the entire pool; no user site-count budget is imposed.
    ordered, coverage_audit = select_maximum_coverage_sites(
        pool,
        radius_km=float(args.coverage_radius_km),
        max_sites=len(pool),
        group_col="survey_area_id" if "survey_area_id" in pool.columns else None,
    )
    if "site_id" not in ordered.columns:
        ordered["site_id"] = [str(i) for i in range(1, len(ordered) + 1)]
    ordered["site_id"] = ordered["site_id"].astype(str)
    ordered.to_csv(output / "outcome_free_geometry_order.csv", index=False)

    # Development-label stage begins only after the deployable order is fixed.
    detections = pd.read_csv(args.detections)
    oracle = development_oracle(pool, detections, radius_km=float(args.recovery_radius_km))
    (output / "development_oracle.json").write_text(
        json.dumps(oracle, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    curve = prefix_recovery_curve(ordered, detections, radius_km=float(args.recovery_radius_km))
    curve.to_csv(output / "inverse_prefix_recovery_curve.csv", index=False)

    max_recovered = int(curve["n_recovered_clusters"].max())
    first_max = int(curve.loc[curve["n_recovered_clusters"].eq(max_recovered), "k"].min())
    complete = max_recovered == len(detections)
    oracle_min = int(oracle["exact_minimum_sites_for_reachable_clusters"])
    summary: dict[str, object] = {
        "status": "development_only_not_independent_validation",
        "field_labels_used_for_candidate_order": False,
        "field_labels_used_after_order_for_inverse_diagnosis": True,
        "candidate_pool_rows": int(len(pool)),
        "geometry_order_rows": int(len(ordered)),
        "field_detection_clusters": int(len(detections)),
        "coverage_radius_km": float(args.coverage_radius_km),
        "recovery_radius_km": float(args.recovery_radius_km),
        "maximum_recovered_clusters": max_recovered,
        "candidate_generation_complete_for_field_clusters": bool(complete),
        "first_prefix_reaching_maximum_recovery": first_max,
        "development_oracle": oracle,
        "geometry_prefix_minus_oracle_site_count": int(first_max - oracle_min),
        "coverage_selection": coverage_audit.as_dict(),
        "interpretation": (
            "Campanula outcomes are development labels used to measure the gap between the deployable "
            "outcome-free order and a field-label set-cover oracle. The oracle is not a deployable policy."
        ),
    }

    if args.travel_matrix:
        allowed_modes = args.allowed_modes or []
        if not allowed_modes:
            raise ValueError("--travel-matrix requires at least one explicit --allowed-mode")
        matrix = read_travel_time_matrix(args.travel_matrix, undirected=bool(args.undirected_travel_matrix))
        selected, effort_audit, effort_frontier = infer_recommended_effort_from_matrix(
            ordered,
            travel_matrix=matrix,
            hub_id=args.hub_id,
            allowed_modes=allowed_modes,
            survey_protocol=plant_protocol(),
            max_sites=None,
        )
        effort_frontier.to_csv(output / "movement_constrained_effort_frontier.csv", index=False)
        selected.to_csv(output / "auto_recommended_survey_set.csv", index=False)
        recovery = detection_recovery_table(
            selected,
            detections,
            radii_km=(float(args.recovery_radius_km),),
            candidate_id_col="site_id",
            area_col="survey_area_id",
            detection_area_col="island",
        )
        auto_summary = recovery_summary(recovery, radii_km=(float(args.recovery_radius_km),)).iloc[0]
        summary["auto_effort"] = effort_audit.as_dict()
        summary["auto_effort_allowed_modes"] = sorted(set(allowed_modes))
        summary["auto_effort_recovered_clusters"] = int(auto_summary["n_recovered"])
        summary["auto_effort_detection_recall"] = float(auto_summary["detection_recall"])
    else:
        summary["auto_effort"] = None
        summary["auto_effort_status"] = (
            "not computed: a real movement matrix is required; ACSP does not invent straight-line travel"
        )

    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
