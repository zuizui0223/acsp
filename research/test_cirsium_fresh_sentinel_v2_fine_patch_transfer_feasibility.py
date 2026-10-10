#!/usr/bin/env python3
"""Test validated 2.5% / 1-km patch constants on dense fine structural orders.

This is representation feasibility only. The full source-complete structural
order is already frozen upstream. The strongest 2.5% are retained using that
transferred constant and aggregated with the same deterministic greedy
complete-link rule at 1 km.

A KD-tree is used only to restrict which existing patches can possibly accept
the next point. Any compatible patch must contain at least one prior member
within 1 km, so this candidate restriction is exact. Synthetic tests require
membership parity with the reference implementation.
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
from scipy.spatial import cKDTree

from acsp.robust_patches import (
    EARTH_RADIUS_M,
    _complete_link_support_patches,
    _haversine_m,
    _safe_area_token,
)
from acsp.validated_robust import (
    VALIDATED_ROBUST_PATCH_MERGE_DISTANCE_M,
    VALIDATED_ROBUST_SUPPORT_FRACTION,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_v2_fine_patch_transfer_feasibility_v1.json"
UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")


def _load_contract() -> dict[str, Any]:
    value = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if value.get("status") != "FROZEN_BEFORE_FINE_PATCH_TRANSFER_FEASIBILITY":
        raise ValueError("fine patch-transfer contract is not frozen")
    constants = value["transferred_constants"]
    if float(constants["support_fraction"]) != VALIDATED_ROBUST_SUPPORT_FRACTION:
        raise ValueError("fine patch transfer support fraction drifted")
    if float(constants["patch_merge_distance_m"]) != VALIDATED_ROBUST_PATCH_MERGE_DISTANCE_M:
        raise ValueError("fine patch transfer merge distance drifted")
    return value


def _unit_vectors(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    lat_r = np.radians(np.asarray(lat, dtype=float))
    lon_r = np.radians(np.asarray(lon, dtype=float))
    cos_lat = np.cos(lat_r)
    return np.column_stack(
        (cos_lat * np.cos(lon_r), cos_lat * np.sin(lon_r), np.sin(lat_r))
    )


def _chord_radius(distance_m: float) -> float:
    angle = float(distance_m) / EARTH_RADIUS_M
    return float(2.0 * np.sin(angle / 2.0))


def _fast_complete_link_support_patches(
    selected: pd.DataFrame,
    *,
    merge_distance_m: float,
    latitude_col: str = "latitude",
    longitude_col: str = "longitude",
    area_col: str = "cohort_unit_id",
) -> pd.DataFrame:
    """Exact accelerated equivalent of the frozen greedy complete-link rule."""
    if selected.empty:
        return pd.DataFrame()
    threshold = float(merge_distance_m)
    if threshold <= 0:
        raise ValueError("merge_distance_m must be positive")

    work = selected.copy().reset_index(drop=True)
    work[latitude_col] = pd.to_numeric(work[latitude_col], errors="coerce")
    work[longitude_col] = pd.to_numeric(work[longitude_col], errors="coerce")
    work = work.dropna(subset=[latitude_col, longitude_col]).reset_index(drop=True)
    if work.empty:
        return pd.DataFrame()

    patch_members: list[tuple[object, int, list[int]]] = []
    for area, group in work.groupby(area_col, sort=True, dropna=False):
        ordered = group.assign(
            _stable_numeric=pd.to_numeric(group["site_id"], errors="coerce"),
            _stable_id=group["site_id"].astype(str),
        ).sort_values(
            ["_stable_numeric", "_stable_id", latitude_col, longitude_col],
            kind="mergesort",
            na_position="last",
        )
        ordered_indices = ordered.index.to_numpy(dtype=int)
        lat = work.loc[ordered_indices, latitude_col].to_numpy(float)
        lon = work.loc[ordered_indices, longitude_col].to_numpy(float)
        tree = cKDTree(_unit_vectors(lat, lon))
        neighbours = tree.query_ball_point(
            _unit_vectors(lat, lon),
            r=float(np.nextafter(_chord_radius(threshold), np.inf)),
        )

        area_patches: list[list[int]] = []
        ordered_pos_patch = np.full(len(ordered_indices), -1, dtype=int)

        for pos, work_index in enumerate(ordered_indices):
            candidate_patch_ids: set[int] = set()
            for previous_pos in neighbours[pos]:
                previous_pos = int(previous_pos)
                if previous_pos >= pos:
                    continue
                patch_id = int(ordered_pos_patch[previous_pos])
                if patch_id >= 0:
                    candidate_patch_ids.add(patch_id)

            compatible: list[tuple[float, int]] = []
            for patch_index in sorted(candidate_patch_ids):
                member_indices = area_patches[patch_index]
                members = work.loc[member_indices]
                distances = _haversine_m(
                    work.at[work_index, latitude_col],
                    work.at[work_index, longitude_col],
                    members[latitude_col].to_numpy(float),
                    members[longitude_col].to_numpy(float),
                )
                maximum = float(distances.max()) if len(distances) else 0.0
                if maximum <= threshold:
                    compatible.append((maximum, patch_index))

            if compatible:
                patch_index = min(compatible)[1]
                area_patches[patch_index].append(int(work_index))
            else:
                patch_index = len(area_patches)
                area_patches.append([int(work_index)])
            ordered_pos_patch[pos] = int(patch_index)

        for patch_number, indices in enumerate(area_patches, start=1):
            patch_members.append((area, patch_number, indices))

    rows: list[dict[str, object]] = []
    for area, patch_number, indices in patch_members:
        members = work.loc[indices].copy()
        representative = members.assign(
            _support_rank=pd.to_numeric(
                members["ecological_support_rank"], errors="coerce"
            ),
            _stable_id=members["site_id"].astype(str),
        ).sort_values(
            ["_support_rank", "_stable_id", latitude_col, longitude_col],
            kind="mergesort",
            na_position="last",
        ).iloc[0]
        distances = _haversine_m(
            representative[latitude_col],
            representative[longitude_col],
            members[latitude_col].to_numpy(float),
            members[longitude_col].to_numpy(float),
        )
        zone_id = f"{_safe_area_token(area)}-Z{patch_number:03d}"
        rows.append(
            {
                "zone_id": zone_id,
                area_col: area,
                "zone_member_count": int(len(members)),
                "zone_radius_m": round(
                    float(distances.max()) if len(distances) else 0.0, 1
                ),
                "zone_merge_threshold_m": round(threshold, 1),
                "representative_site_id": str(representative["site_id"]),
                "latitude": float(representative[latitude_col]),
                "longitude": float(representative[longitude_col]),
                "zone_member_site_ids": ";".join(
                    members["site_id"].astype(str).tolist()
                ),
            }
        )

    zones = pd.DataFrame(rows)
    if zones.empty:
        return zones
    zones["_neutral_area_sort"] = zones[area_col].astype(str)
    return zones.sort_values(
        ["_neutral_area_sort", "zone_id"], kind="mergesort"
    ).drop(columns="_neutral_area_sort").reset_index(drop=True)


def _patch_membership_signature(frame: pd.DataFrame) -> list[tuple[str, ...]]:
    if frame.empty:
        return []
    return sorted(
        tuple(row.split(";"))
        for row in frame["zone_member_site_ids"].astype(str).tolist()
    )


def assert_reference_parity(selected: pd.DataFrame) -> None:
    reference = _complete_link_support_patches(
        selected,
        merge_distance_m=VALIDATED_ROBUST_PATCH_MERGE_DISTANCE_M,
        latitude_col="latitude",
        longitude_col="longitude",
        area_col="cohort_unit_id",
    )
    accelerated = _fast_complete_link_support_patches(
        selected,
        merge_distance_m=VALIDATED_ROBUST_PATCH_MERGE_DISTANCE_M,
        latitude_col="latitude",
        longitude_col="longitude",
        area_col="cohort_unit_id",
    )
    if _patch_membership_signature(reference) != _patch_membership_signature(accelerated):
        raise AssertionError("accelerated fine complete-link membership differs from reference")


def build_fine_patch_transfer(
    structural_order: pd.DataFrame,
    *,
    unit_id: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    _load_contract()
    if unit_id not in UNITS:
        raise ValueError(f"unknown fresh-SENTINEL unit: {unit_id}")
    required = {
        "candidate_cell_id",
        "cohort_unit_id",
        "structural_rank",
        "structural_support",
        "latitude",
        "longitude",
    }
    missing = sorted(required.difference(structural_order.columns))
    if missing:
        raise ValueError(f"fine structural order missing columns: {missing}")
    if structural_order.empty:
        raise ValueError("fine structural order cannot be empty")
    if set(structural_order["cohort_unit_id"].astype(str)) != {unit_id}:
        raise ValueError("fine structural order unit identity drifted")
    candidate_ids = structural_order["candidate_cell_id"]
    if candidate_ids.isna().any() or candidate_ids.astype(str).str.strip().eq("").any():
        raise ValueError("fine structural candidate IDs must be nonempty")
    if candidate_ids.astype(str).str.contains(";", regex=False).any():
        raise ValueError("fine structural candidate IDs contain a reserved separator")
    if candidate_ids.astype(str).duplicated().any():
        raise ValueError("fine structural order candidate IDs must be unique")

    # Never coerce fractional ranks to integers: that can silently alter the
    # frozen 2.5% membership even if the truncated sequence looks complete.
    rank_values = pd.to_numeric(
        structural_order["structural_rank"], errors="raise"
    ).to_numpy(dtype=np.float64)
    if not np.isfinite(rank_values).all() or not np.array_equal(
        rank_values, np.floor(rank_values)
    ):
        raise ValueError("fine structural ranks must be finite integers")
    rank = pd.Series(rank_values.astype(np.int64), index=structural_order.index)
    if not np.array_equal(
        np.sort(rank.to_numpy()),
        np.arange(1, len(structural_order) + 1, dtype=np.int64),
    ):
        raise ValueError("fine structural rank must be a complete 1..N order")

    if not np.isfinite(
        pd.to_numeric(structural_order["structural_support"], errors="coerce").to_numpy(float)
    ).all():
        raise ValueError("source-complete structural support must be finite")
    # The reference patcher drops missing coordinates; source-complete fine
    # cells cannot be silently dropped after being counted in the 2.5% tier.
    for column, low, high in (
        ("latitude", -90.0, 90.0),
        ("longitude", -180.0, 180.0),
    ):
        values = pd.to_numeric(structural_order[column], errors="coerce").to_numpy(float)
        if not np.isfinite(values).all() or np.any((values < low) | (values > high)):
            raise ValueError(f"source-complete {column} must be finite and in range")
    normalized_rank = rank.astype(float) / float(len(structural_order))
    keep = normalized_rank <= float(VALIDATED_ROBUST_SUPPORT_FRACTION)
    retained = (
        structural_order.loc[keep]
        .copy()
        .sort_values("structural_rank", kind="mergesort")
        .reset_index(drop=True)
    )
    retain_n = int(len(retained))
    if retain_n < 1:
        raise ValueError(
            "validated 0.025 rank-fraction tier is empty for this structural order"
        )
    selected = pd.DataFrame(
        {
            "site_id": retained["candidate_cell_id"].astype(str),
            "cohort_unit_id": unit_id,
            "ecological_support_rank": (
                pd.to_numeric(retained["structural_rank"], errors="raise").astype(float)
                / float(len(structural_order))
            ),
            "latitude": pd.to_numeric(retained["latitude"], errors="raise").astype(float),
            "longitude": pd.to_numeric(retained["longitude"], errors="raise").astype(float),
        }
    )
    patches = _fast_complete_link_support_patches(
        selected,
        merge_distance_m=VALIDATED_ROBUST_PATCH_MERGE_DISTANCE_M,
        latitude_col="latitude",
        longitude_col="longitude",
        area_col="cohort_unit_id",
    )
    if patches.empty:
        raise AssertionError("retained fine support cells produced no patches")

    # Every retained fine cell must belong to exactly one exported patch.
    patch_member_ids = [
        cell_id
        for member_ids in patches["zone_member_site_ids"].astype(str)
        for cell_id in member_ids.split(";")
    ]
    retained_ids = selected["site_id"].astype(str).tolist()
    if (
        len(patch_member_ids) != retain_n
        or len(set(patch_member_ids)) != retain_n
        or set(patch_member_ids) != set(retained_ids)
        or int(pd.to_numeric(patches["zone_member_count"], errors="raise").sum()) != retain_n
    ):
        raise AssertionError("fine patch aggregation lost or duplicated retained cells")

    members = pd.to_numeric(
        patches["zone_member_count"], errors="raise"
    ).astype(int).to_numpy()
    patch_count = int(len(patches))
    singleton_count = int(np.count_nonzero(members == 1))
    summary = {
        "schema_version": "cirsium-fresh-sentinel-v2-fine-patch-transfer-result-v1",
        "status": "FINE_PATCH_TRANSFER_REPRESENTATION_FEASIBILITY_COMPLETE",
        "cohort_unit_id": unit_id,
        "source_complete_structural_order_rows": int(len(structural_order)),
        "retained_support_cell_count": retain_n,
        "support_fraction": float(VALIDATED_ROBUST_SUPPORT_FRACTION),
        "patch_merge_distance_m": float(
            VALIDATED_ROBUST_PATCH_MERGE_DISTANCE_M
        ),
        "patch_count": patch_count,
        "compression_ratio_patch_per_retained_cell": float(
            patch_count / retain_n
        ),
        "singleton_patch_count": singleton_count,
        "singleton_patch_fraction": float(
            singleton_count / patch_count
        ),
        "median_patch_member_count": float(np.median(members)),
        "maximum_patch_member_count": int(members.max()),
        "source_indeterminate_included": False,
        "source_indeterminate_ranked": False,
        "field_outcomes_opened": False,
        "recovery_used": False,
        "transfer_is_validated_selector": False,
        "top_k_added_beyond_transferred_fraction": False,
        "support_threshold_refit": False,
        "target_patch_count_used": False,
    }
    return patches, summary


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-id", choices=UNITS, required=True)
    parser.add_argument("--structural-order-csv-gz", type=Path, required=True)
    parser.add_argument("--private-patches-csv-gz", type=Path, required=True)
    parser.add_argument("--public-safe-summary-json", type=Path, required=True)
    args = parser.parse_args()

    if not args.structural_order_csv_gz.is_file():
        raise SystemExit(f"missing private structural order: {args.structural_order_csv_gz}")
    order = pd.read_csv(args.structural_order_csv_gz, low_memory=False)
    patches, summary = build_fine_patch_transfer(order, unit_id=args.unit_id)

    args.private_patches_csv_gz.parent.mkdir(parents=True, exist_ok=True)
    args.public_safe_summary_json.parent.mkdir(parents=True, exist_ok=True)
    patches.to_csv(
        args.private_patches_csv_gz,
        index=False,
        compression={"method": "gzip", "mtime": 0},
    )
    summary["private_patch_sha256"] = _sha256(args.private_patches_csv_gz)
    args.public_safe_summary_json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
