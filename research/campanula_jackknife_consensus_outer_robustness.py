#!/usr/bin/env python3
"""Final Campanula development gate: outer-LOO jackknife-consensus robustness.

The freeze candidate is fixed before this audit:
- support fraction: 0.15;
- bounded complete-link merge ceiling: 1 km;
- patch policy coefficients inherited unchanged from the spatial policy;
- operational budget: 42 patches.

For each outer leave-one-prototype-out dataset, an inner jackknife consensus is
rebuilt from the remaining 17 prototypes.  All outer designs are frozen before
2026 field clusters are opened.  No coefficient, support fraction, or patch
budget is changed based on this audit.
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

import campanula_jackknife_consensus as consensus
import campanula_patch_policy as base
from campanula_patch_policy_fast import cached_prefix
from campanula_spatial_policy_robustness import (
    AREA_COST_WEIGHT,
    GAP_WEIGHT,
    GEO_WEIGHT,
    NEW_COMPONENT_WEIGHT,
    SUPPORT_WEIGHT,
    DEFAULT_SEED,
    jaccard,
)
from campanula_worldcover_discovery import evaluate

SUPPORT_FRACTION = 0.15
PATCH_BUDGET = 42
CANDIDATE_DIAGNOSTIC_FRACTION = 0.05


def geometry_for_subset(
    universe: pd.DataFrame,
    prototypes: pd.DataFrame,
    removed: tuple[int, ...],
) -> dict:
    keep = ~prototypes.index.isin(removed)
    subset = prototypes.loc[keep].reset_index(drop=True)
    responsibility, support_rank, proto_rows, kernel_scale = base.environmental_geometry(
        universe, subset
    )
    return {
        "removed": tuple(int(value) for value in removed),
        "responsibility": responsibility.astype("float32", copy=False),
        "support_rank": support_rank.astype("float32", copy=False),
        "proto_rows": proto_rows,
        "kernel_scale": float(kernel_scale),
    }


def build_consensus_design(universe: pd.DataFrame, worlds: list[dict]) -> dict:
    support_stack = np.vstack([world["support_rank"] for world in worlds])
    support_rank = np.median(support_stack, axis=0)

    _, zones = base.make_zones(universe, support_rank, SUPPORT_FRACTION)
    order, rank_diagnostics = consensus.consensus_order_for_zones(
        universe,
        zones,
        support_rank,
        worlds,
    )
    positions = order[: min(PATCH_BUDGET, len(order))]
    selected_zones = zones.iloc[positions].copy()
    selected_indices: set[int] = set()
    for _, zone in selected_zones.iterrows():
        selected_indices.update(base.patch.member_indices(zone))

    candidate_indices = np.flatnonzero(
        support_rank <= CANDIDATE_DIAGNOSTIC_FRACTION
    ).astype(int)
    return {
        "support_rank": support_rank,
        "zones": zones,
        "order": order,
        "selected_indices": sorted(selected_indices),
        "selected_zone_ids": selected_zones["zone_id"].astype(str).tolist(),
        "n_patches": int(len(selected_zones)),
        "n_cells": int(len(selected_indices)),
        "total_patch_universe": int(len(zones)),
        "island_patch_counts": {
            str(key): int(value)
            for key, value in selected_zones["survey_area_id"]
            .astype(str)
            .value_counts()
            .to_dict()
            .items()
        },
        "candidate_5pct_indices": candidate_indices.tolist(),
        "candidate_5pct_cells": int(len(candidate_indices)),
        "rank_diagnostics": rank_diagnostics,
        "support_rank_sd_mean": float(np.mean(np.std(support_stack, axis=0))),
        "support_rank_sd_q95": float(np.quantile(np.std(support_stack, axis=0), 0.95)),
    }


def summarize(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0}
    recovered = np.asarray([row["recovered"] for row in rows], dtype=float)
    candidate_recovered = np.asarray(
        [row["candidate_5pct_recovered"] for row in rows], dtype=float
    )
    total = float(rows[0]["total"])
    prefixes = np.asarray(
        [
            row["complete_recovery_prefix_n_patches"]
            if row["complete_recovery_prefix_n_patches"] is not None
            else np.nan
            for row in rows
        ],
        dtype=float,
    )
    finite_prefix = prefixes[np.isfinite(prefixes)]
    return {
        "n": int(len(rows)),
        "fixed_42_complete_recovery_rate": float(np.mean(recovered == total)),
        "fixed_42_mean_recovered": float(np.mean(recovered)),
        "fixed_42_min_recovered": int(np.min(recovered)),
        "candidate_5pct_complete_recovery_rate": float(
            np.mean(candidate_recovered == total)
        ),
        "candidate_5pct_mean_recovered": float(np.mean(candidate_recovered)),
        "mean_selected_cell_jaccard_to_canonical": float(
            np.mean([row["selected_cell_jaccard_to_canonical"] for row in rows])
        ),
        "min_selected_cell_jaccard_to_canonical": float(
            np.min([row["selected_cell_jaccard_to_canonical"] for row in rows])
        ),
        "mean_required_complete_prefix_patches": float(np.mean(finite_prefix))
        if len(finite_prefix)
        else None,
        "max_required_complete_prefix_patches": int(np.max(finite_prefix))
        if len(finite_prefix)
        else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--microterrain-universe", type=Path, required=True)
    parser.add_argument("--gbif-prototypes", type=Path, required=True)
    parser.add_argument("--ndvi", type=Path, required=True)
    parser.add_argument("--detections", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    universe = pd.read_csv(args.microterrain_universe)
    prototypes = pd.read_csv(args.gbif_prototypes)
    universe, prototypes = base.attach_ndvi(universe, prototypes, args.ndvi)
    prototypes = prototypes.reset_index(drop=True)
    n = len(prototypes)
    if n < 6:
        raise RuntimeError("Too few prototypes for nested jackknife consensus")

    # Generator stage only.  Precompute unique single- and pair-deletion worlds.
    single_worlds = {
        (i,): geometry_for_subset(universe, prototypes, (i,))
        for i in range(n)
    }
    pair_worlds = {
        tuple(pair): geometry_for_subset(universe, prototypes, tuple(pair))
        for pair in itertools.combinations(range(n), 2)
    }

    canonical_worlds = [single_worlds[(i,)] for i in range(n)]
    canonical = build_consensus_design(universe, canonical_worlds)
    frozen = [
        {
            "outer_removed": None,
            "design": canonical,
        }
    ]

    for outer in range(n):
        internal = [
            pair_worlds[tuple(sorted((outer, inner)))]
            for inner in range(n)
            if inner != outer
        ]
        design = build_consensus_design(universe, internal)
        frozen.append(
            {
                "outer_removed": int(outer),
                "design": design,
            }
        )

    # Development scoring starts only here.
    detections = pd.read_csv(args.detections)
    canonical_cells = canonical["selected_indices"]
    rows = []
    for item in frozen:
        design = item["design"]
        selected = design["selected_indices"]
        result = evaluate(universe.loc[selected], detections, 1.0)
        candidate_indices = design["candidate_5pct_indices"]
        candidate_result = evaluate(
            universe.loc[candidate_indices], detections, 1.0
        )
        ranked = base.ranked_zones_for_order(design["zones"], design["order"])
        prefix = cached_prefix(universe, ranked, detections, 1.0)
        row = {
            "outer_removed": item["outer_removed"],
            "n_patches": design["n_patches"],
            "n_cells": design["n_cells"],
            "total_patch_universe": design["total_patch_universe"],
            "island_patch_counts": design["island_patch_counts"],
            "selected_zone_ids": design["selected_zone_ids"],
            "candidate_5pct_cells": design["candidate_5pct_cells"],
            "rank_diagnostics": design["rank_diagnostics"],
            "support_rank_sd_mean": design["support_rank_sd_mean"],
            "support_rank_sd_q95": design["support_rank_sd_q95"],
            "selected_cell_jaccard_to_canonical": jaccard(
                selected, canonical_cells
            ),
            **result,
            "candidate_5pct_recovered": int(candidate_result["recovered"]),
            "candidate_5pct_max_nearest_km": float(
                candidate_result["max_nearest_km"]
            ),
            "complete_recovery_prefix_n_patches": None
            if prefix is None
            else int(prefix["n_patches"]),
            "complete_recovery_prefix_n_cells": None
            if prefix is None
            else int(prefix["n_cells"]),
        }
        rows.append(row)

    canonical_row = rows[0]
    outer_rows = rows[1:]
    outer_summary = summarize(outer_rows)
    freeze_gate = {
        "canonical_fixed_42_complete": bool(
            canonical_row["recovered"] == canonical_row["total"]
        ),
        "all_outer_loo_fixed_42_complete": bool(
            outer_summary["fixed_42_complete_recovery_rate"] == 1.0
        ),
        "all_outer_loo_candidate_5pct_complete": bool(
            outer_summary["candidate_5pct_complete_recovery_rate"] == 1.0
        ),
    }
    freeze_gate["pass"] = bool(all(freeze_gate.values()))

    args.out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).drop(columns=["nearest_km"], errors="ignore").to_csv(
        args.out / "jackknife_consensus_outer_loo.csv", index=False
    )
    report = {
        "status": "development_only_outer_loo_freeze_gate",
        "field_coordinates_used_by_generator": False,
        "policy_weights_support_fraction_and_budget_were_fixed": True,
        "fixed_method": {
            "support_consensus": "median internal leave-one-prototype-out support rank",
            "patch_consensus": "median normalized fixed-policy rank across internal jackknife worlds",
            "support_fraction": SUPPORT_FRACTION,
            "patch_budget": PATCH_BUDGET,
            "candidate_diagnostic_fraction": CANDIDATE_DIAGNOSTIC_FRACTION,
            "support_weight": SUPPORT_WEIGHT,
            "new_component_weight": NEW_COMPONENT_WEIGHT,
            "area_cost_weight": AREA_COST_WEIGHT,
            "geo_weight": GEO_WEIGHT,
            "gap_weight": GAP_WEIGHT,
            "merge_distance_m": base.MERGE_DISTANCE_M,
        },
        "prototype_count": int(n),
        "pair_deletion_worlds_precomputed": int(len(pair_worlds)),
        "canonical": canonical_row,
        "outer_leave_one_out": outer_summary,
        "freeze_gate": freeze_gate,
        "outer_rows": outer_rows,
    }
    (args.out / "jackknife_consensus_outer_robustness_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
