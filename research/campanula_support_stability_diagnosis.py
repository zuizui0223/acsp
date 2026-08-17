#!/usr/bin/env python3
"""Diagnose Campanula prototype sensitivity and test one structural stabilizer.

The fixed 32-patch spatial policy failed a strong prototype-deletion robustness
check.  This script separates two possible causes without searching policy
weights:

1. ``fixed_universe`` keeps the canonical 5% patch universe fixed and perturbs
   only pre-2026 prototype responsibilities / survey-gap values.  This measures
   patch-order sensitivity conditional on a stable candidate universe.
2. ``equal_prototype_quota`` replaces the global nearest-prototype Top-5%
   candidate rule with one outcome-blind structural regularizer: every retained
   pre-2026 prototype contributes the same maximum number of its best-matching
   grid cells before their union is aggregated into patches.  No coefficient is
   fitted from field outcomes.

Every perturbation subset and every policy order is frozen before the inspected
2026 field clusters are opened.
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
from campanula_persistent_patch_hash import fast_random_patch_audit
from campanula_spatial_policy_robustness import (
    AREA_COST_WEIGHT,
    GAP_WEIGHT,
    GEO_WEIGHT,
    NEW_COMPONENT_WEIGHT,
    PATCH_BUDGET,
    SUPPORT_FRACTION,
    SUPPORT_WEIGHT,
    DEFAULT_SEED,
    jaccard,
)
from campanula_worldcover_discovery import evaluate


def make_policy_design(
    universe: pd.DataFrame,
    zones: pd.DataFrame,
    responsibility: np.ndarray,
    support_rank: np.ndarray,
    proto_rows: pd.DataFrame,
) -> dict:
    if zones.empty:
        return {
            "status": "empty_patch_universe",
            "selected_indices": [],
            "selected_zone_ids": [],
            "n_patches": 0,
            "n_cells": 0,
            "island_patch_counts": {},
            "total_patch_universe": 0,
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
    positions = order[: min(PATCH_BUDGET, len(order))]
    selected_zones = zones.iloc[positions].copy()
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
        "total_patch_universe": int(len(zones)),
    }


def equal_quota_rank(
    responsibility: np.ndarray,
    nominal_fraction: float,
) -> tuple[np.ndarray, dict]:
    """Build a bounded union in which every prototype has equal cell quota."""
    n_cells, n_prototypes = responsibility.shape
    if n_prototypes < 1:
        return np.ones(n_cells, dtype=float), {
            "quota_per_prototype": 0,
            "union_cells": 0,
            "union_fraction": 0.0,
        }
    total_nominal = max(1, int(math.ceil(float(nominal_fraction) * n_cells)))
    quota = max(1, int(math.ceil(total_nominal / n_prototypes)))
    selected: set[int] = set()
    for proto_index in range(n_prototypes):
        values = responsibility[:, proto_index]
        finite = np.flatnonzero(np.isfinite(values) & (values > 0))
        if not len(finite):
            continue
        take = min(quota, len(finite))
        # Stable descending responsibility, then lower universe index.
        order = finite[np.argsort(-values[finite], kind="mergesort")[:take]]
        selected.update(int(value) for value in order)

    rank = np.ones(n_cells, dtype=float)
    if selected:
        idx = np.asarray(sorted(selected), dtype=int)
        support = np.max(responsibility[idx], axis=1)
        order = np.argsort(-support, kind="mergesort")
        # Keep all selected cells under the existing 5% threshold interface,
        # without pretending that the union itself occupies exactly 5%.
        assigned = np.linspace(
            0.0,
            max(float(nominal_fraction) - 1e-9, 0.0),
            len(idx),
            endpoint=True,
        )
        rank[idx[order]] = assigned
    return rank, {
        "quota_per_prototype": int(quota),
        "union_cells": int(len(selected)),
        "union_fraction": float(len(selected) / n_cells),
    }


def perturbation_subsets(prototypes: pd.DataFrame, repeats: int, seed: int) -> list[dict]:
    specs = [
        {
            "perturbation": "canonical",
            "replicate": 0,
            "removed": tuple(),
        }
    ]
    for index in range(len(prototypes)):
        specs.append(
            {
                "perturbation": "leave_one_out",
                "replicate": int(index),
                "removed": (int(index),),
            }
        )
    remove_n = max(1, int(math.ceil(0.20 * len(prototypes))))
    rng = np.random.default_rng(seed)
    seen: set[tuple[int, ...]] = set()
    attempts = 0
    while len(seen) < int(repeats):
        attempts += 1
        if attempts > int(repeats) * 100:
            break
        removed = tuple(
            sorted(
                int(value)
                for value in rng.choice(len(prototypes), size=remove_n, replace=False)
            )
        )
        if removed in seen:
            continue
        seen.add(removed)
        specs.append(
            {
                "perturbation": "leave_20_percent",
                "replicate": int(len(seen) - 1),
                "removed": removed,
            }
        )
    return specs


def summarize(rows: list[dict], arm: str, perturbation: str) -> dict:
    subset = [
        row for row in rows
        if row["arm"] == arm and row["perturbation"] == perturbation
    ]
    if not subset:
        return {"n": 0}
    recovered = np.asarray([row["recovered"] for row in subset], dtype=float)
    total = float(subset[0]["total"])
    jac = np.asarray([row["selected_cell_jaccard_to_arm_canonical"] for row in subset], dtype=float)
    return {
        "n": int(len(subset)),
        "complete_recovery_rate": float(np.mean(recovered == total)),
        "mean_recovered": float(np.mean(recovered)),
        "min_recovered": int(np.min(recovered)),
        "mean_selected_cell_jaccard_to_arm_canonical": float(np.mean(jac)),
        "q05_selected_cell_jaccard_to_arm_canonical": float(np.quantile(jac, 0.05)),
        "mean_cells": float(np.mean([row["n_cells"] for row in subset])),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--microterrain-universe", type=Path, required=True)
    parser.add_argument("--gbif-prototypes", type=Path, required=True)
    parser.add_argument("--ndvi", type=Path, required=True)
    parser.add_argument("--detections", type=Path, required=True)
    parser.add_argument("--leave20-repeats", type=int, default=50)
    parser.add_argument("--random-iterations", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    universe = pd.read_csv(args.microterrain_universe)
    prototypes = pd.read_csv(args.gbif_prototypes)
    universe, prototypes = base.attach_ndvi(universe, prototypes, args.ndvi)
    prototypes = prototypes.reset_index(drop=True)

    # Canonical full-prototype geometry and patch universe, all outcome-blind.
    full_resp, full_rank, full_proto_rows, full_kernel = base.environmental_geometry(
        universe, prototypes
    )
    _, canonical_zones = base.make_zones(universe, full_rank, SUPPORT_FRACTION)

    specs = perturbation_subsets(prototypes, args.leave20_repeats, args.seed)
    frozen: list[dict] = []

    for spec in specs:
        removed = tuple(spec["removed"])
        keep = ~prototypes.index.isin(removed)
        subset = prototypes.loc[keep].reset_index(drop=True)
        sub_resp, sub_rank, sub_rows, sub_kernel = base.environmental_geometry(
            universe, subset
        )

        # Arm A: patch universe fixed, only prototype-derived policy evidence moves.
        fixed_design = make_policy_design(
            universe,
            canonical_zones,
            sub_resp,
            full_rank,
            sub_rows,
        )
        fixed_design.update(
            {
                **spec,
                "arm": "fixed_universe",
                "removed_prototype_indices": list(removed),
                "prototype_count": int(len(sub_rows)),
                "prototype_kernel_scale": float(sub_kernel),
                "support_universe_cells": int(
                    sum(len(base.patch.member_indices(row)) for _, row in canonical_zones.iterrows())
                ),
            }
        )
        frozen.append(fixed_design)

        # Arm B: equal per-prototype candidate quota, then the identical fixed policy.
        quota_rank, quota_info = equal_quota_rank(sub_resp, SUPPORT_FRACTION)
        _, quota_zones = base.make_zones(universe, quota_rank, SUPPORT_FRACTION)
        quota_design = make_policy_design(
            universe,
            quota_zones,
            sub_resp,
            quota_rank,
            sub_rows,
        )
        quota_design.update(
            {
                **spec,
                "arm": "equal_prototype_quota",
                "removed_prototype_indices": list(removed),
                "prototype_count": int(len(sub_rows)),
                "prototype_kernel_scale": float(sub_kernel),
                **quota_info,
                "support_universe_cells": int(quota_info["union_cells"]),
            }
        )
        # Keep zones internally only for the canonical random audit below.
        if spec["perturbation"] == "canonical":
            quota_design["_zones"] = quota_zones
        frozen.append(quota_design)

    # Development scoring begins only after every design above has been frozen.
    detections = pd.read_csv(args.detections)
    arm_canonical_cells = {
        row["arm"]: row["selected_indices"]
        for row in frozen
        if row["perturbation"] == "canonical"
    }
    scored = []
    canonical_quota_zones = None
    for design in frozen:
        selected = design["selected_indices"]
        result = evaluate(universe.loc[selected], detections, 1.0) if selected else {
            "recovered": 0,
            "total": int(len(detections)),
            "max_nearest_km": float("inf"),
            "nearest_km": [float("inf")] * len(detections),
        }
        row = {
            key: value
            for key, value in design.items()
            if key not in {"selected_indices", "_zones"}
        }
        row["selected_cell_jaccard_to_arm_canonical"] = jaccard(
            selected,
            arm_canonical_cells[design["arm"]],
        )
        row.update(result)
        scored.append(row)
        if (
            design["arm"] == "equal_prototype_quota"
            and design["perturbation"] == "canonical"
        ):
            canonical_quota_zones = design.get("_zones")

    summary = {}
    for arm in ("fixed_universe", "equal_prototype_quota"):
        canonical = next(
            row for row in scored
            if row["arm"] == arm and row["perturbation"] == "canonical"
        )
        summary[arm] = {
            "canonical": canonical,
            "leave_one_out": summarize(scored, arm, "leave_one_out"),
            "leave_20_percent": summarize(scored, arm, "leave_20_percent"),
        }

    # Random audit only the canonical equal-quota design if it actually achieves
    # complete field recovery; this is evaluation, never generator input.
    quota_canonical = summary["equal_prototype_quota"]["canonical"]
    if (
        canonical_quota_zones is not None
        and quota_canonical["recovered"] == quota_canonical["total"]
    ):
        quota_canonical["matched_random_patches"] = fast_random_patch_audit(
            universe,
            canonical_quota_zones,
            detections,
            quota_canonical,
            1.0,
            args.random_iterations,
            args.seed,
        )

    diagnosis = {
        "status": "development_only_structural_diagnosis",
        "field_coordinates_used_by_generator": False,
        "policy_weights_were_searched_in_this_diagnosis": False,
        "fixed_policy": {
            "support_fraction_interface": SUPPORT_FRACTION,
            "patch_budget": PATCH_BUDGET,
            "support_weight": SUPPORT_WEIGHT,
            "new_component_weight": NEW_COMPONENT_WEIGHT,
            "area_cost_weight": AREA_COST_WEIGHT,
            "geo_weight": GEO_WEIGHT,
            "gap_weight": GAP_WEIGHT,
            "merge_distance_m": base.MERGE_DISTANCE_M,
        },
        "prototype_count": int(len(prototypes)),
        "full_prototype_kernel_scale": float(full_kernel),
        "arms": summary,
        "interpretation_rule": {
            "fixed_universe_stable_but_full_rebuild_unstable": (
                "candidate/support-universe instability dominates"
            ),
            "fixed_universe_also_unstable": (
                "prototype-derived patch ordering itself is unstable"
            ),
            "equal_quota_passes": (
                "equal prototype influence is a viable structural stabilizer"
            ),
        },
    }

    args.out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(scored).drop(columns=["nearest_km"], errors="ignore").to_csv(
        args.out / "support_stability_diagnosis_replicates.csv", index=False
    )
    (args.out / "support_stability_diagnosis_report.json").write_text(
        json.dumps(diagnosis, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(diagnosis, indent=2))


if __name__ == "__main__":
    main()
