#!/usr/bin/env python3
"""Audit retained-support *mask* connectivity inside frozen fine-grid patches.

This is an outcome-blind representation audit, not ecological habitat
connectivity, a biological non-detection, a path/access model, or a new
field-selector rule. The 8-neighbour rule is inherited from frozen G_E
grid primitives. A support gap is NOT a biological barrier.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
CONTRACT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_v2_patch_support_connectivity_audit_v1.json"
RECEIPT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_v2_fine_patch_transfer_result_v1.json"
NEIGHBOURS = tuple(
    (dr, dc)
    for dr in (-1, 0, 1)
    for dc in (-1, 0, 1)
    if dr or dc
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT.resolve())
        return True
    except ValueError:
        return False


def _contract() -> dict[str, Any]:
    value = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if value["status"] != "FROZEN_BEFORE_SUPPORT_MASK_CONNECTIVITY_AUDIT":
        raise ValueError("support-mask topology contract not frozen")
    settings = value["frozen_inputs"]
    if settings["support_fraction"] != 0.025:
        raise ValueError("support fraction drift")
    if settings["patch_merge_distance_m"] != 1000:
        raise ValueError("patch merge threshold drift")
    if settings["support_mask_neighborhood"] != "EXACT_GRID_MOORE_8_NEIGHBOR":
        raise ValueError("grid neighbourhood drift")
    if settings["neighborhood_radius_cells"] != 1:
        raise ValueError("grid radius drift")
    if value["interpretation"]["diagnostic_only"] is not True:
        raise ValueError("topology audit cannot promote a field selector")
    if value["interpretation"]["prospective_field_outcomes_read"] is not False:
        raise ValueError("topology audit cannot use field outcomes")
    if tuple(value["cohort_unit_ids"]) != UNITS:
        raise ValueError("unit cohort drift")
    return value


def _integers(series: pd.Series, name: str) -> np.ndarray:
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(values).all() or not np.array_equal(values, np.floor(values)):
        raise ValueError(f"{name} must be complete finite integers")
    if (np.abs(values) > 2 ** 53).any():
        raise ValueError(f"{name} exceeds exactly representable integer range")
    return values.astype(np.int64)


def _component_count(positions: set[tuple[int, int]]) -> int:
    remaining = positions.copy()
    count = 0
    while remaining:
        count += 1
        frontier = [remaining.pop()]
        while frontier:
            r, c = frontier.pop()
            for dr, dc in NEIGHBOURS:
                candidate = (r + dr, c + dc)
                if candidate in remaining:
                    remaining.remove(candidate)
                    frontier.append(candidate)
    return count


def audit_patch_support_connectivity(
    structural_order: pd.DataFrame,
    patches: pd.DataFrame,
    *,
    unit_id: str,
) -> dict[str, Any]:
    """Check all-cell coverage then audit 8-neighbour support connectivity.

    Never re-clusters patches, changes support rank, or accesses field outcomes.
    """
    _contract()
    if unit_id not in UNITS:
        raise ValueError("unknown fresh-SENTINEL unit")
    required_order = {"candidate_cell_id", "cohort_unit_id", "structural_rank", "grid_row", "grid_col"}
    required_patches = {"cohort_unit_id", "zone_id", "zone_member_count", "zone_member_site_ids"}
    if not required_order.issubset(structural_order.columns):
        raise ValueError(f"fine structural order missing {sorted(required_order - set(structural_order.columns))}")
    if not required_patches.issubset(patches.columns):
        raise ValueError(f"fine patch CSV missing {sorted(required_patches - set(patches.columns))}")
    if structural_order.empty or patches.empty:
        raise ValueError("source-complete order and patches must be nonempty")
    if set(structural_order["cohort_unit_id"].astype(str)) != {unit_id}:
        raise ValueError("structural order unit drift")
    if set(patches["cohort_unit_id"].astype(str)) != {unit_id}:
        raise ValueError("patch unit drift")

    ids = structural_order["candidate_cell_id"].astype(str)
    if structural_order["candidate_cell_id"].isna().any() or ids.str.strip().eq("").any():
        raise ValueError("structural order candidate IDs missing")
    if ids.str.contains(";", regex=False).any() or ids.duplicated().any():
        raise ValueError("structural order candidate IDs malformed or duplicated")
    n = len(structural_order)
    ranks = _integers(structural_order["structural_rank"], "structural_rank")
    if not np.array_equal(np.sort(ranks), np.arange(1, n + 1, dtype=np.int64)):
        raise ValueError("fine structural ranks must be complete 1..N")

    # Identical rank fraction to the previously frozen patch transfer; no
    # threshold or parameter is fitted from observed connectivity.
    chosen = ranks.astype(float) / float(n) <= 0.025
    retained_ids = ids[chosen].tolist()
    retained_rows = _integers(structural_order.loc[chosen, "grid_row"], "grid_row")
    retained_cols = _integers(structural_order.loc[chosen, "grid_col"], "grid_col")
    positions_by_id = dict(zip(retained_ids, zip(retained_rows.tolist(), retained_cols.tolist())))
    if not positions_by_id:
        raise ValueError("frozen 2.5% tier is empty")
    if len(set(positions_by_id.values())) != len(positions_by_id):
        raise ValueError("retained fine-grid coordinates are not unique")

    if patches["zone_id"].astype(str).duplicated().any():
        raise ValueError("patch IDs are duplicated")
    expected_counts = _integers(patches["zone_member_count"], "zone_member_count")
    if (expected_counts <= 0).any():
        raise ValueError("patch member count must be positive")

    used: set[str] = set()
    fragmented_patches = 0
    fragmented_cells = 0
    component_sum = 0
    largest_component_count = 0
    for index, row in enumerate(patches.itertuples(index=False)):
        member_text = str(row.zone_member_site_ids)
        member_ids = member_text.split(";")
        if not member_text or any(not k for k in member_ids):
            raise ValueError("patch has empty or malformed member ID")
        if len(member_ids) != int(expected_counts[index]):
            raise ValueError("patch member count disagrees with IDs")
        if len(set(member_ids)) != len(member_ids):
            raise ValueError("patch repeats a retained cell")
        if any(k not in positions_by_id for k in member_ids):
            raise ValueError("patch contains a cell outside the frozen retained support tier")
        if used.intersection(member_ids):
            raise ValueError("retained cell appears in multiple patches")
        used.update(member_ids)
        positions = {positions_by_id[k] for k in member_ids}
        if len(positions) != len(member_ids):
            raise ValueError("multiple cells share a patch grid coordinate")
        components = _component_count(positions)
        largest_component_count = max(largest_component_count, components)
        component_sum += components
        if components > 1:
            fragmented_patches += 1
            fragmented_cells += len(member_ids)

    if used != set(retained_ids):
        raise ValueError("patches do not conserve the full retained support tier")
    patch_count = len(patches)
    retained_n = len(retained_ids)
    global_components = _component_count(set(positions_by_id.values()))

    return {
        "schema_version": "cirsium-fresh-sentinel-v2-support-mask-connectivity-result-v1",
        "status": "RETAINED_SUPPORT_MASK_CONNECTIVITY_AUDITED_PRE_OUTCOME",
        "cohort_unit_id": unit_id,
        "retained_support_cell_count": retained_n,
        "complete_link_patch_count": patch_count,
        "connected_patch_count": patch_count - fragmented_patches,
        "fragmented_patch_count": fragmented_patches,
        "fragmented_patch_fraction": fragmented_patches / patch_count,
        "retained_cells_in_fragmented_patches": fragmented_cells,
        "retained_cells_in_fragmented_fraction": fragmented_cells / retained_n,
        "support_mask_connected_component_count": global_components,
        "within_patch_component_count_total": component_sum,
        "extra_within_patch_components": component_sum - patch_count,
        "maximum_components_per_patch": largest_component_count,
        "all_retained_cells_represented_once": True,
        "source_indeterminate_reclassified_as_absence": False,
        "support_mask_gap_interpreted_as_biological_barrier": False,
        "geographic_patch_selector_unchanged": True,
        "prospective_field_outcomes_opened": False,
        "field_selector_validation": False,
        "coordinates_in_public_summary": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-id", required=True, choices=UNITS)
    parser.add_argument("--structural-order-csv-gz", type=Path, required=True)
    parser.add_argument("--private-patches-csv-gz", type=Path, required=True)
    parser.add_argument("--public-safe-summary-json", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.structural_order_csv_gz, args.private_patches_csv_gz):
        if _inside_repo(path) or not path.is_file():
            raise SystemExit("private input must exist outside the public repository")
    if args.public_safe_summary_json.exists():
        raise SystemExit("refusing to overwrite an existing public-safe summary")

    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    if receipt.get("status") != "FINE_PATCH_REPRESENTATION_FEASIBLE_SELECTOR_UNVALIDATED":
        raise SystemExit("source receipt is not frozen at representation-only boundary")
    frozen = receipt["units"][args.unit_id]
    order_hash = _sha256(args.structural_order_csv_gz)
    patch_hash = _sha256(args.private_patches_csv_gz)
    if order_hash != frozen["structural_order_sha256"]:
        raise SystemExit("fine structural order hash differs from frozen source")
    if patch_hash != frozen["private_patch_sha256"]:
        raise SystemExit("fine patch file hash differs from frozen representation")

    order = pd.read_csv(args.structural_order_csv_gz, low_memory=False)
    patches = pd.read_csv(args.private_patches_csv_gz, low_memory=False)
    summary = audit_patch_support_connectivity(order, patches, unit_id=args.unit_id)
    expected = (
        frozen["structural_source_complete_count"],
        frozen["transferred_2p5pct_retained_cell_count"],
        frozen["complete_link_patch_count"],
    )
    actual = (len(order), summary["retained_support_cell_count"], summary["complete_link_patch_count"])
    if actual != expected:
        raise SystemExit(f"frozen representation denominator drift: {actual} vs {expected}")
    summary["frozen_structural_order_sha256"] = order_hash
    summary["frozen_private_patch_sha256"] = patch_hash
    args.public_safe_summary_json.parent.mkdir(parents=True, exist_ok=True)
    args.public_safe_summary_json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
