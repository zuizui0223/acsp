#!/usr/bin/env python3
"""Pre-freeze robustness audit for the fixed Campanula spatial patch policy.

The policy under audit is frozen from the completed Campanula development line:
5% NDVI support universe, bounded complete-link patches, prototype-coverage
weighting plus within-component geographic complementarity and survey-gap value,
and a fixed budget of 32 patches.

This script does not search policy weights.  It perturbs only the pre-2026 GBIF
prototype set, rebuilds the same fixed policy, freezes every perturbed design,
and only then opens the inspected 2026 field clusters for sensitivity scoring.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

import campanula_patch_policy as base
import campanula_patch_policy_spatial as spatial
from campanula_worldcover_discovery import evaluate

SUPPORT_FRACTION = 0.05
PATCH_BUDGET = 32
SUPPORT_WEIGHT = 0.25
NEW_COMPONENT_WEIGHT = 0.10
AREA_COST_WEIGHT = 0.02
GEO_WEIGHT = 1.00
GAP_WEIGHT = 0.05
DEFAULT_SEED = 20260815


def selected_design(universe: pd.DataFrame, prototype_subset: pd.DataFrame) -> dict:
    responsibility, support_rank, proto_rows, kernel_scale = base.environmental_geometry(
        universe, prototype_subset
    )
    _, zones = base.make_zones(universe, support_rank, SUPPORT_FRACTION)
    if zones.empty:
        return {
            "status": "empty_patch_universe",
            "selected_indices": [],
            "selected_zone_ids": [],
            "n_patches": 0,
            "n_cells": 0,
            "island_patch_counts": {},
            "prototype_count": int(len(proto_rows)),
            "prototype_kernel_scale": float(kernel_scale),
        }

    matrix, support, area_cost, islands = base.patch_responsibilities(
        zones, responsibility, support_rank
    )
    gap, spatial_scale, islands, lat, lon = spatial.patch_spatial_features(
        zones, proto_rows
    )
    order = spatial.greedy_spatial_order(
        matrix,
        support,
        area_cost,
        islands,
        lat,
        lon,
        gap,
        spatial_scale,
        SUPPORT_WEIGHT,
        NEW_COMPONENT_WEIGHT,
        AREA_COST_WEIGHT,
        GEO_WEIGHT,
        GAP_WEIGHT,
    )
    selected_positions = order[: min(PATCH_BUDGET, len(order))]
    selected_zones = zones.iloc[selected_positions].copy()
    selected_indices: set[int] = set()
    for _, zone in selected_zones.iterrows():
        selected_indices.update(base.patch.member_indices(zone))

    return {
        "status": "ok",
        "selected_indices": sorted(int(value) for value in selected_indices),
        "selected_zone_ids": selected_zones["zone_id"].astype(str).tolist(),
        "n_patches": int(len(selected_zones)),
        "n_cells": int(len(selected_indices)),
        "island_patch_counts": {
            str(key): int(value)
            for key, value in selected_zones["survey_area_id"]
            .astype(str)
            .value_counts()
            .to_dict()
            .items()
        },
        "prototype_count": int(len(proto_rows)),
        "prototype_kernel_scale": float(kernel_scale),
    }


def jaccard(left: list[int], right: list[int]) -> float:
    a = set(int(value) for value in left)
    b = set(int(value) for value in right)
    union = a | b
    if not union:
        return 1.0
    return float(len(a & b) / len(union))


def score_designs(universe: pd.DataFrame, designs: list[dict], detections: pd.DataFrame) -> list[dict]:
    rows = []
    canonical_cells = designs[0]["selected_indices"] if designs else []
    for design in designs:
        selected = design.get("selected_indices", [])
        if selected:
            result = evaluate(universe.loc[selected], detections, 1.0)
        else:
            result = {
                "recovered": 0,
                "total": int(len(detections)),
                "max_nearest_km": float("inf"),
                "nearest_km": [float("inf")] * len(detections),
            }
        rows.append(
            {
                **{key: value for key, value in design.items() if key != "selected_indices"},
                "selected_cell_jaccard_to_canonical": jaccard(selected, canonical_cells),
                **result,
            }
        )
    return rows


def summarize(rows: list[dict], kind: str) -> dict:
    subset = [row for row in rows if row.get("perturbation") == kind]
    if not subset:
        return {"n": 0}
    recovered = np.asarray([float(row["recovered"]) for row in subset], dtype=float)
    complete = recovered == float(subset[0]["total"])
    jaccards = np.asarray(
        [float(row["selected_cell_jaccard_to_canonical"]) for row in subset], dtype=float
    )
    max_nearest = np.asarray([float(row["max_nearest_km"]) for row in subset], dtype=float)
    cells = np.asarray([float(row["n_cells"]) for row in subset], dtype=float)
    return {
        "n": int(len(subset)),
        "complete_recovery_rate": float(np.mean(complete)),
        "mean_recovered": float(np.mean(recovered)),
        "min_recovered": int(np.min(recovered)),
        "mean_selected_cell_jaccard_to_canonical": float(np.mean(jaccards)),
        "q05_selected_cell_jaccard_to_canonical": float(np.quantile(jaccards, 0.05)),
        "mean_max_nearest_km": float(np.mean(max_nearest)),
        "q95_max_nearest_km": float(np.quantile(max_nearest, 0.95)),
        "mean_selected_cells": float(np.mean(cells)),
        "q05_selected_cells": float(np.quantile(cells, 0.05)),
        "q95_selected_cells": float(np.quantile(cells, 0.95)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--microterrain-universe", type=Path, required=True)
    parser.add_argument("--gbif-prototypes", type=Path, required=True)
    parser.add_argument("--ndvi", type=Path, required=True)
    parser.add_argument("--detections", type=Path, required=True)
    parser.add_argument("--leave20-repeats", type=int, default=50)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    universe = pd.read_csv(args.microterrain_universe)
    prototypes = pd.read_csv(args.gbif_prototypes)
    universe, prototypes = base.attach_ndvi(universe, prototypes, args.ndvi)
    prototypes = prototypes.reset_index(drop=True)
    if len(prototypes) < 5:
        raise RuntimeError("Too few prototypes for the declared robustness audit")

    # Generator/sensitivity stage.  Every subset and every resulting 32-patch
    # design is built before the 2026 field outcomes are opened below.
    designs: list[dict] = []

    canonical = selected_design(universe, prototypes)
    canonical.update(
        {
            "perturbation": "canonical",
            "replicate": 0,
            "removed_prototype_indices": [],
        }
    )
    designs.append(canonical)

    for index in range(len(prototypes)):
        keep = prototypes.index != index
        design = selected_design(universe, prototypes.loc[keep].reset_index(drop=True))
        design.update(
            {
                "perturbation": "leave_one_out",
                "replicate": int(index),
                "removed_prototype_indices": [int(index)],
            }
        )
        designs.append(design)

    rng = np.random.default_rng(args.seed)
    remove_n = max(1, int(math.ceil(0.20 * len(prototypes))))
    seen_subsets: set[tuple[int, ...]] = set()
    attempts = 0
    while len(seen_subsets) < int(args.leave20_repeats):
        attempts += 1
        if attempts > int(args.leave20_repeats) * 100:
            break
        removed = tuple(
            sorted(
                int(value)
                for value in rng.choice(
                    len(prototypes), size=remove_n, replace=False
                ).tolist()
            )
        )
        if removed in seen_subsets:
            continue
        seen_subsets.add(removed)
        keep = ~prototypes.index.isin(removed)
        design = selected_design(universe, prototypes.loc[keep].reset_index(drop=True))
        design.update(
            {
                "perturbation": "leave_20_percent",
                "replicate": int(len(seen_subsets) - 1),
                "removed_prototype_indices": list(removed),
            }
        )
        designs.append(design)

    # Development scoring stage: field coordinates become visible only here.
    detections = pd.read_csv(args.detections)
    scored = score_designs(universe, designs, detections)
    canonical_score = scored[0]
    loo = summarize(scored, "leave_one_out")
    leave20 = summarize(scored, "leave_20_percent")

    # Predeclared freeze gate: the canonical policy must remain complete; every
    # single-prototype deletion must remain complete; and >=90% of harsher
    # leave-20% perturbations must retain all 19 clusters at the fixed 32-patch
    # budget.  These thresholds are evaluated, not tuned, here.
    freeze_gate = {
        "canonical_complete": bool(canonical_score["recovered"] == canonical_score["total"]),
        "all_leave_one_out_complete": bool(
            loo.get("n", 0) > 0 and loo.get("complete_recovery_rate") == 1.0
        ),
        "leave20_complete_rate_at_least_0_90": bool(
            leave20.get("n", 0) > 0
            and leave20.get("complete_recovery_rate", 0.0) >= 0.90
        ),
    }
    freeze_gate["pass"] = bool(all(freeze_gate.values()))

    args.out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(scored).drop(columns=["nearest_km"], errors="ignore").to_csv(
        args.out / "spatial_policy_robustness_replicates.csv", index=False
    )
    report = {
        "status": "development_only_pre_freeze_robustness",
        "field_coordinates_used_by_generator": False,
        "policy_weights_were_searched_in_this_audit": False,
        "fixed_policy": {
            "support_fraction": SUPPORT_FRACTION,
            "patch_budget": PATCH_BUDGET,
            "support_weight": SUPPORT_WEIGHT,
            "new_component_weight": NEW_COMPONENT_WEIGHT,
            "area_cost_weight": AREA_COST_WEIGHT,
            "geo_weight": GEO_WEIGHT,
            "gap_weight": GAP_WEIGHT,
            "merge_distance_m": base.MERGE_DISTANCE_M,
        },
        "prototype_count": int(len(prototypes)),
        "leave20_remove_n": int(remove_n),
        "canonical": canonical_score,
        "leave_one_out": loo,
        "leave_20_percent": leave20,
        "freeze_gate": freeze_gate,
    }
    (args.out / "spatial_policy_robustness_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
