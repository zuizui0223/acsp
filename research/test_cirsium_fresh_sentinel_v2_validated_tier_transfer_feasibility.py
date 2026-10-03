#!/usr/bin/env python3
"""Test representation feasibility of transferring validated 2.5% / 1-km constants.

This is not a validation of the fresh coarse score. It asks only whether applying
the already-confirmed robust-product constants to the source-ready coarse order
would mechanically compress the sparse broad-frame points into a compact bounded
patch representation. No field or heldout outcome is read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from acsp.robust_patches import _complete_link_support_patches
from acsp.validated_robust import (
    VALIDATED_ROBUST_PATCH_MERGE_DISTANCE_M,
    VALIDATED_ROBUST_SUPPORT_FRACTION,
)
from acsp.global_geometry import fetch_geoboundaries_country_geometry
from research.build_cirsium_fresh_sentinel_public_broad_frame_v2 import (
    build_fresh_sentinel_v2_outer_frame,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_v2_validated_tier_transfer_feasibility_v1.json"
UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
READY = "SOURCE_READY_FOR_FAMILY_COARSE_STAGE"
EXPECTED_CANDIDATES = 39200


def _validate_contract() -> None:
    value = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if value.get("status") != "FROZEN_BEFORE_VALIDATED_TIER_TRANSFER_FEASIBILITY":
        raise ValueError("validated-tier transfer contract is not frozen")
    constants = value["transferred_constants"]
    if float(constants["support_fraction"]) != VALIDATED_ROBUST_SUPPORT_FRACTION:
        raise ValueError("support fraction differs from validated ACSP constant")
    if float(constants["patch_merge_distance_m"]) != VALIDATED_ROBUST_PATCH_MERGE_DISTANCE_M:
        raise ValueError("merge distance differs from validated ACSP constant")


def transfer_unit(
    order: pd.DataFrame,
    outer: pd.DataFrame,
    unit: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    required = {"candidate_cell_id", "source_state", "coarse_evidence_rank"}
    missing = sorted(required.difference(order.columns))
    if missing:
        raise ValueError(f"{unit} coarse order missing columns: {missing}")
    if len(order) != len(outer):
        raise ValueError(f"{unit} order/outer-frame row count mismatch")
    if set(order["candidate_cell_id"].astype(str)) != set(outer["candidate_cell_id"].astype(str)):
        raise ValueError(f"{unit} candidate identity set differs from outer frame")

    ready = order.loc[order["source_state"].astype(str).eq(READY)].copy()
    ready["coarse_evidence_rank"] = pd.to_numeric(ready["coarse_evidence_rank"], errors="raise").astype(int)
    ready = ready.sort_values("coarse_evidence_rank", kind="mergesort").reset_index(drop=True)
    expected_ranks = list(range(1, len(ready) + 1))
    if ready["coarse_evidence_rank"].tolist() != expected_ranks:
        raise ValueError(f"{unit} source-ready order is not complete 1..N")

    retain_n = int(math.ceil(VALIDATED_ROBUST_SUPPORT_FRACTION * len(ready)))
    retained = ready.iloc[:retain_n].copy()
    coords = outer.set_index(outer["candidate_cell_id"].astype(str))[
        ["latitude", "longitude", "regional_tile_id"]
    ]
    retained.index = retained["candidate_cell_id"].astype(str)
    retained = retained.join(coords, how="left").reset_index(drop=True)
    if retained[["latitude", "longitude", "regional_tile_id"]].isna().any().any():
        raise ValueError(f"{unit} failed to restore frozen outer-frame geometry")

    selected = pd.DataFrame({
        "site_id": retained["candidate_cell_id"].astype(str),
        "ecological_support_rank": retained["coarse_evidence_rank"].astype(float) / float(len(ready)),
        "latitude": pd.to_numeric(retained["latitude"], errors="raise"),
        "longitude": pd.to_numeric(retained["longitude"], errors="raise"),
        "regional_tile_id": retained["regional_tile_id"].astype(str),
    })
    patches = _complete_link_support_patches(
        selected,
        merge_distance_m=VALIDATED_ROBUST_PATCH_MERGE_DISTANCE_M,
        latitude_col="latitude",
        longitude_col="longitude",
        area_col="regional_tile_id",
    )
    if patches.empty and retain_n:
        raise AssertionError(f"{unit} retained points unexpectedly produced no patches")
    members = pd.to_numeric(patches["zone_member_count"], errors="raise").astype(int).to_numpy()
    patch_count = int(len(patches))
    singleton_count = int(np.count_nonzero(members == 1))
    summary = {
        "cohort_unit_id": unit,
        "source_ready_candidate_count": int(len(ready)),
        "retained_point_count": retain_n,
        "support_fraction": float(VALIDATED_ROBUST_SUPPORT_FRACTION),
        "patch_merge_distance_m": float(VALIDATED_ROBUST_PATCH_MERGE_DISTANCE_M),
        "patch_count": patch_count,
        "compression_ratio_patch_per_retained_point": float(patch_count / retain_n) if retain_n else 0.0,
        "singleton_patch_count": singleton_count,
        "singleton_patch_fraction": float(singleton_count / patch_count) if patch_count else 0.0,
        "median_patch_member_count": float(np.median(members)) if patch_count else 0.0,
        "maximum_patch_member_count": int(members.max()) if patch_count else 0,
        "source_indeterminate_included": False,
        "field_outcome_used": False,
        "recovery_used": False,
        "transfer_already_validated": False,
    }
    return patches, summary


def run_all(orders: dict[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    _validate_contract()
    if set(orders) != set(UNITS):
        raise ValueError("unit set drifted")
    for unit in UNITS:
        if len(orders[unit]) != EXPECTED_CANDIDATES:
            raise ValueError(f"{unit} production coarse order must contain 39,200 candidates")
    geometry = fetch_geoboundaries_country_geometry("JP")
    outer, outer_summary = build_fresh_sentinel_v2_outer_frame(geometry)
    if int(outer_summary["candidate_count"]) != EXPECTED_CANDIDATES:
        raise ValueError("frozen Japan outer frame candidate count drifted")

    outputs: dict[str, pd.DataFrame] = {}
    unit_results: dict[str, Any] = {}
    for unit in UNITS:
        patches, summary = transfer_unit(orders[unit], outer, unit)
        outputs[unit] = patches
        unit_results[unit] = summary
    return outputs, {
        "schema_version": "cirsium-fresh-sentinel-v2-validated-tier-transfer-feasibility-result-v1",
        "status": "VALIDATED_TIER_TRANSFER_REPRESENTATION_FEASIBILITY_COMPLETE",
        "unit_results": unit_results,
        "support_fraction": float(VALIDATED_ROBUST_SUPPORT_FRACTION),
        "patch_merge_distance_m": float(VALIDATED_ROBUST_PATCH_MERGE_DISTANCE_M),
        "field_outcomes_opened": False,
        "recovery_used": False,
        "source_indeterminate_ranked": False,
        "transfer_is_validated_selector": False,
        "next_gate": "Interpret representation compression only; do not tune transferred constants or claim recovery.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order", action="append", required=True, help="UNIT=path.csv.gz")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    orders: dict[str, pd.DataFrame] = {}
    for spec in args.order:
        unit, path = spec.split("=", 1)
        orders[unit] = pd.read_csv(path, low_memory=False)
    outputs, summary = run_all(orders)
    out = args.out_dir
    if out.exists():
        raise ValueError("refusing to overwrite validated-tier transfer output")
    out.mkdir(parents=True)
    hashes = {}
    for unit, patches in outputs.items():
        path = out / f"{unit}_transferred_2p5pct_1km_patches.csv.gz"
        patches.to_csv(path, index=False, compression={"method":"gzip","mtime":0})
        hashes[unit] = hashlib.sha256(path.read_bytes()).hexdigest()
    summary["private_patch_sha256_by_unit"] = hashes
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
