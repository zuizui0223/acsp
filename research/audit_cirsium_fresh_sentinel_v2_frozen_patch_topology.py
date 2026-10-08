#!/usr/bin/env python3
"""Audit frozen 100-m high-support patch *membership* topology, not the GSI world.

Only the exact gzip file hash already frozen by PR #247/#248 is an eligible
input. The candidate-cell IDs encode the fixed integer 100-m grid lattice, so
the retained support mask can be audited without refitting / reopening the
entire upstream structural order. This is not an exception to PR #250's stricter
full-order provenance gate: it answers a different, explicitly limited question.

No private coordinates, tile names, field outcomes or routes are exported.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "validation/coverage_then_fine_structure_fresh_sentinel_v2_patch_only_topology_v1.json"
FROZEN_PATH = ROOT / "validation/coverage_then_fine_structure_fresh_sentinel_v2_fine_patch_transfer_result_v1.json"
UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
OFFSETS = tuple(
    (dr, dc)
    for dr in (-1, 0, 1)
    for dc in (-1, 0, 1)
    if (dr, dc) != (0, 0)
)


def _within_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT.resolve())
        return True
    except ValueError:
        return False


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _contract() -> dict[str, Any]:
    value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if value.get("status") != "FROZEN_BEFORE_PATCH_MEMBERSHIP_ONLY_TOPOLOGY_AUDIT":
        raise ValueError("patch-only topology contract not frozen")
    if tuple(value.get("cohort_unit_ids", ())) != UNITS:
        raise ValueError("patch-only audit cohort changed")
    if (value.get("support_fraction"), value.get("complete_link_max_distance_m"), value.get("grid_spacing_m")) != (0.025, 1000, 100):
        raise ValueError("frozen patch scale or support fraction changed")
    flags = value.get("interpretation", {})
    if any(flags.get(k) is not False for k in (
        "source_input_integrity_evaluated", "ecological_connectivity_validated",
        "full_structural_order_hash_gate_waived", "field_selector_validated",
        "prospective_field_outcomes_opened", "support_gap_is_biological_absence",
    )):
        raise ValueError("patch topology audit cannot promote biological or full-source evidence")
    if flags.get("existing_strict_pr250_gate_unchanged") is not True:
        raise ValueError("PR250 strict structural-order audit must remain separate")
    return value


def _component_count(locations: set[tuple[int, int]]) -> int:
    remaining = set(locations)
    total = 0
    while remaining:
        total += 1
        frontier = [remaining.pop()]
        while frontier:
            row, col = frontier.pop()
            for dr, dc in OFFSETS:
                candidate = (row + dr, col + dc)
                if candidate in remaining:
                    remaining.remove(candidate)
                    frontier.append(candidate)
    return total


def _counts(values: pd.Series, *, label: str) -> list[int]:
    numbers = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    import numpy as np
    if not np.isfinite(numbers).all() or not np.array_equal(numbers, np.floor(numbers)):
        raise ValueError(f"{label} must contain only finite integers")
    if (numbers < 1).any() or (numbers > 2 ** 53).any():
        raise ValueError(f"{label} contains non-positive or out-of-range values")
    return [int(x) for x in numbers]


def audit_frozen_patch_membership(
    patches: pd.DataFrame,
    *,
    unit_id: str,
    expected_cells: int,
    expected_patches: int,
    expected_singletons: int,
) -> dict[str, Any]:
    _contract()
    if unit_id not in UNITS:
        raise ValueError("unknown frozen Cirsium cohort unit")
    required = {
        "zone_id", "cohort_unit_id", "zone_member_site_ids",
        "zone_member_count", "zone_merge_threshold_m", "zone_radius_m",
    }
    if not required.issubset(patches.columns):
        raise ValueError("frozen patch export schema missing required columns")
    if patches.empty or len(patches) != expected_patches:
        raise ValueError("frozen patch count mismatch")
    if patches[list(required)].isna().any().any():
        raise ValueError("patch export includes missing required fields")
    if set(patches["cohort_unit_id"].astype(str)) != {unit_id}:
        raise ValueError("frozen patch cohort identity mismatch")
    if patches["zone_id"].astype(str).duplicated().any():
        raise ValueError("patch IDs are not unique")
    thresholds = pd.to_numeric(patches["zone_merge_threshold_m"], errors="coerce")
    radii = pd.to_numeric(patches["zone_radius_m"], errors="coerce")
    if not thresholds.eq(1000.0).all() or not radii.between(0, 1000.0).all():
        raise ValueError("frozen complete-link 1-km patch geometry drifted")

    sizes = _counts(patches["zone_member_count"], label="zone_member_count")
    pattern = re.compile(rf"^{re.escape(unit_id)}_r(-?\d+)_c(-?\d+)$")
    seen: set[str] = set()
    coordinates: set[tuple[int, int]] = set()
    fragmented = 0
    fragmented_cells = 0
    extra_components = 0
    component_total = 0
    max_components = 0
    singleton_count = 0

    for i, row in enumerate(patches.itertuples(index=False)):
        member_ids = str(row.zone_member_site_ids).split(";")
        if len(member_ids) != sizes[i] or len(set(member_ids)) != sizes[i]:
            raise ValueError("patch member identity/count mismatch")
        members: set[tuple[int, int]] = set()
        for member_id in member_ids:
            match = pattern.fullmatch(member_id)
            if match is None:
                raise ValueError("patch membership does not use the frozen 100-m grid ID schema")
            if member_id in seen:
                raise ValueError("retained support cell appears in multiple patches")
            seen.add(member_id)
            grid_position = (int(match.group(1)), int(match.group(2)))
            if grid_position in coordinates:
                raise ValueError("different retained cells encode the same grid coordinate")
            coordinates.add(grid_position)
            members.add(grid_position)
        if len(members) != sizes[i]:
            raise ValueError("patch contains duplicate grid coordinates")
        components = _component_count(members)
        component_total += components
        max_components = max(max_components, components)
        extra_components += components - 1
        if components > 1:
            fragmented += 1
            fragmented_cells += sizes[i]
        if sizes[i] == 1:
            singleton_count += 1

    if len(seen) != expected_cells or sum(sizes) != expected_cells:
        raise ValueError("frozen retained-support denominator is not conserved")
    if singleton_count != expected_singletons:
        raise ValueError("frozen singleton-patch count differs from original")
    overall_components = _component_count(coordinates)
    return {
        "schema_version": "cirsium-fresh-sentinel-v2-frozen-patch-only-topology-v1",
        "status": "FROZEN_PATCH_MASK_TOPOLOGY_AUDITED_UPSTREAM_UNCERTAINTY_RETAINED",
        "cohort_unit_id": unit_id,
        "retained_support_cell_count": len(seen),
        "complete_link_patch_count": len(patches),
        "connected_patch_count": len(patches) - fragmented,
        "disconnected_patch_count": fragmented,
        "disconnected_patch_fraction": fragmented / len(patches),
        "cells_in_disconnected_patches": fragmented_cells,
        "cells_in_disconnected_patch_fraction": fragmented_cells / len(seen),
        "global_mask_component_count": overall_components,
        "within_patch_component_count_total": component_total,
        "extra_within_patch_components": extra_components,
        "maximum_components_per_patch": max_components,
        "singleton_patch_count": singleton_count,
        "all_retained_cells_accounted_for": True,
        "patch_membership_unchanged": True,
        "original_structural_order_reproduced": None,
        "original_structural_order_reproduction_tested_by_this_route": False,
        "source_integrity_claim_authorized": False,
        "ecological_connectivity_claim_authorized": False,
        "field_selector_validation": False,
        "prospective_field_outcomes_opened": False,
        "coordinates_or_candidate_ids_in_public_output": False,
    }


def run_frozen_patch_topology(
    *,
    unit_id: str,
    private_patches: Path,
    public_summary: Path,
) -> dict[str, Any]:
    contract = _contract()
    if unit_id not in UNITS:
        raise ValueError("unknown frozen Cirsium cohort unit")
    private_patches = Path(private_patches).resolve()
    public_summary = Path(public_summary).resolve()
    if _within_repo(private_patches) or not private_patches.is_file():
        raise ValueError("private patch input must exist outside public repository")
    if public_summary.exists():
        raise ValueError("refusing to overwrite patch-only topology report")

    frozen = json.loads(FROZEN_PATH.read_text(encoding="utf-8"))
    if (
        frozen.get("status") != "FINE_PATCH_REPRESENTATION_FEASIBLE_SELECTOR_UNVALIDATED"
        or frozen.get("source_pr") != contract["frozen_patch_source_pr"]
    ):
        raise ValueError("original frozen fine-patch representation receipt changed")
    units = frozen.get("units", {})
    if set(units) != set(UNITS):
        raise ValueError("original frozen four-unit cohort changed")
    info = units[unit_id]
    observed_sha = _file_sha256(private_patches)
    if observed_sha != info["private_patch_sha256"]:
        raise ValueError("patch SHA differs from original frozen PR247 membership; audit prohibited")
    patches = pd.read_csv(private_patches, low_memory=False)
    report = audit_frozen_patch_membership(
        patches,
        unit_id=unit_id,
        expected_cells=int(info["transferred_2p5pct_retained_cell_count"]),
        expected_patches=int(info["complete_link_patch_count"]),
        expected_singletons=int(info["singleton_patch_count"]),
    )
    report["verified_original_patch_sha256"] = observed_sha
    public_summary.parent.mkdir(parents=True, exist_ok=True)
    public_summary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-id", required=True, choices=UNITS)
    parser.add_argument("--private-patches-csv-gz", required=True, type=Path)
    parser.add_argument("--public-safe-summary-json", required=True, type=Path)
    args = parser.parse_args()
    report = run_frozen_patch_topology(
        unit_id=args.unit_id,
        private_patches=args.private_patches_csv_gz,
        public_summary=args.public_safe_summary_json,
    )
    print(json.dumps({
        "unit_id": report["cohort_unit_id"],
        "retained_support_cells": report["retained_support_cell_count"],
        "complete_link_patches": report["complete_link_patch_count"],
        "disconnected_patches": report["disconnected_patch_count"],
        "source_integrity_claim_authorized": False,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
