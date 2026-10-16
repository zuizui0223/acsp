#!/usr/bin/env python3
"""Design-stage downstream within-patch site comparison; never reads field outcomes.

This procedure does not change ACSP patch membership. Input cells/assignments
remain private. Its only public product is an aggregate hash and gate report.
It is NOT a field schedule or a newly confirmed independent cohort.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "validation/coverage_then_fine_structure_patch_connectivity_field_trial_design_v1.json"
PREVIOUSLY_EXPOSED = frozenset(("CIR02", "CIR06", "CIR12", "CIR13"))
_OFFSETS = tuple((dr, dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1) if (dr, dc) != (0, 0))


def validate_design_contract() -> dict[str, Any]:
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if (data.get("status") != "METHOD_DESIGN_FROZEN_BEFORE_NEW_COHORT_SELECTION_NO_OUTCOMES"
            or data.get("cohort_identity_frozen") is not False
            or data.get("field_schedule_frozen") is not False
            or data.get("outcomes_may_be_opened") is not False
            or data.get("original_three_arm_fresh_sentinel_protocol_changed") is not False):
        raise ValueError("study design must not bypass frozen existing pre-field gates")
    sampling = data.get("sampling", {})
    if (sampling.get("grid_spacing_m") != 100 or sampling.get("existing_support_fraction") != 0.025
            or sampling.get("existing_complete_link_patch_diameter_m") != 1000
            or sampling.get("projection_identity") != "JAPAN_CENTERED_AEQD_V1"
            or sampling.get("only_internal_disconnected_patches") is not True
            or sampling.get("no_patch_membership_changes_allowed") is not True
            or sampling.get("source_sha_pin_required_before_actual_field_assignment") is not True
            or sampling.get("new_cohort_registry_and_spatial_frame_pin_required") is not True):
        raise ValueError("fixed source or prospective cohort prerequisites changed")
    if data.get("strategy") != {
        "topology": "LARGEST_MOORE8_COMPONENT_MEDOID_V1",
        "geometry": "ALL_RETAINED_PATCH_CELLS_MEDOID_V1",
        "medoid_distance": "MINIMUM_SUM_OF_SQUARED_GRID_CELL_DISTANCES_WITH_GRID_ROW_COL_LEXICOGRAPHIC_TIE_BREAK",
        "largest_fragment_tie": "MOST_CELLS_THEN_SMALLEST_ROW_COL_POINT",
        "both_counterfactual_sites_must_be_existing_retained_cells": True,
        "shared_counterfactual_site_must_be_retained_and_reported": True,
    }:
        raise ValueError("prospective site-selection algorithms changed")
    allocation = data.get("arm_assignment", {})
    if (allocation.get("identity") != "BLINDED_HASH_BALANCED_PATCH_ASSIGNMENT_V1"
            or allocation.get("protocol_salt") != "acsp-topology-field-trial-2026-10-16-v1-no-outcomes"
            or allocation.get("no_postoutcome_resampling_or_substitution") is not True):
        raise ValueError("fixed arm-assignment rule changed")
    if data.get("effort") != {
        "identity": "PERSON_MINUTES_V1",
        "visits_per_assigned_candidate": 3,
        "active_search_minutes_per_visit": 30,
        "observers_per_visit": 1,
        "planned_person_minutes_per_assigned_candidate": 90,
        "planned_effort_equal_between_arms_by_cohort": True,
        "no_day_or_monetary_budget_optimized": True,
    }:
        raise ValueError("planned matched effort changed")
    for key in ("new_original_biological_trial_executed", "equal_effort_field_recovery_effect_established", "topological_high_support_is_habitat_continuity", "full_structural_order_replay_repaired", "original_pr250_gate_unblocked"):
        if data.get("claims", {}).get(key) is not False:
            raise ValueError("unsupported field or connectivity claim")
    return data


def connected_components(points: set[tuple[int, int]]) -> tuple[frozenset[tuple[int, int]], ...]:
    remaining = set(points)
    components: list[frozenset[tuple[int, int]]] = []
    while remaining:
        initial = min(remaining)
        remaining.remove(initial)
        group = {initial}
        todo = [initial]
        while todo:
            r, c = todo.pop()
            for dr, dc in _OFFSETS:
                cell = (r+dr, c+dc)
                if cell in remaining:
                    remaining.remove(cell)
                    group.add(cell)
                    todo.append(cell)
        components.append(frozenset(group))
    return tuple(sorted(components, key=lambda p: (-len(p), min(p))))


def _get_private_patch_points(value: dict[str, Any]) -> tuple[str, str, dict[tuple[int, int], str]]:
    if not isinstance(value, dict):
        raise ValueError("private patch must be an object")
    unit, patch = value.get("cohort_unit_id"), value.get("patch_ref")
    if (not isinstance(unit, str) or re.fullmatch(r"[A-Z0-9_]+", unit) is None
            or not isinstance(patch, str) or not patch or "\n" in patch or "\t" in patch):
        raise ValueError("invalid private patch or cohort identity")
    members = value.get("member_ids")
    if not isinstance(members, (tuple, list)) or not members:
        raise ValueError("missing original retained patch members")
    regex = re.compile(rf"^{re.escape(unit)}_r(-?\d+)_c(-?\d+)$")
    points: dict[tuple[int, int], str] = {}
    for member in members:
        m = regex.fullmatch(member) if isinstance(member, str) else None
        if m is None:
            raise ValueError("invalid original retained cell identity")
        p = (int(m.group(1)), int(m.group(2)))
        if p in points:
            raise ValueError("original patch contains duplicate retained support cell")
        points[p] = member
    if len(points) > 1:
        size_sq = max((a[0]-b[0])**2 + (a[1]-b[1])**2 for a in points for b in points)
        if size_sq > 100:  # sqrt(square distance) * 100 m <= 1000 m
            raise ValueError("original patch exceeds frozen 1 km complete-link maximum diameter")
    if value.get("patch_diameter_limit_m", 1000) != 1000:
        raise ValueError("original complete-link patch scale changed")
    return unit, patch, points


def _medoid(points: frozenset[tuple[int,int]] | set[tuple[int,int]]) -> tuple[int,int]:
    """Exact integer squared-distance sum avoids platform-dependent float ties."""
    return min(points, key=lambda p: (sum((p[0]-q[0])**2 + (p[1]-q[1])**2 for q in points), p))


def choose_counterfactual_sites(patch: dict[str, Any]) -> dict[str, Any]:
    validate_design_contract()
    unit, ref, cells = _get_private_patch_points(patch)
    components = connected_components(set(cells))
    global_medoid = _medoid(set(cells))
    local_medoid = _medoid(components[0])
    return {
        "cohort_unit_id": unit,
        "private_patch_ref": ref,
        "eligible_disconnected": len(components) > 1,
        "within_patch_components": len(components),
        "retained_member_count": len(cells),
        "selected_by_topology": cells[local_medoid],
        "selected_by_geometry": cells[global_medoid],
        "counterfactual_site_shared": local_medoid == global_medoid,
    }


def _allocation_hash(salt: str, cohort: str, private_patch: str) -> str:
    return hashlib.sha256(f"{salt}\t{cohort}\t{private_patch}".encode("utf-8")).hexdigest()


def build_private_trial_assignments(private_patches: list[dict[str, Any]]) -> dict[str, Any]:
    """Pure design-stage preview; does NOT authorize any real field schedules."""
    design = validate_design_contract()
    units: dict[str, list[dict[str, Any]]] = defaultdict(list)
    all_seen: set[tuple[str, str]] = set()
    ineligible_count = 0
    ineligible_by_unit: dict[str, int] = defaultdict(int)
    for patch in private_patches:
        row = choose_counterfactual_sites(patch)
        ident = row["cohort_unit_id"], row["private_patch_ref"]
        if ident in all_seen:
            raise ValueError("duplicate private patch identity")
        all_seen.add(ident)
        if row["eligible_disconnected"]:
            units[ident[0]].append(row)
        else:
            ineligible_count += 1
            ineligible_by_unit[ident[0]] += 1
    assigned: list[dict[str, Any]] = []
    reserved: list[dict[str, Any]] = []
    for unit, rows in sorted(units.items()):
        rows.sort(key=lambda item: (_allocation_hash(design["arm_assignment"]["protocol_salt"],unit,item["private_patch_ref"]), item["private_patch_ref"]))
        n = len(rows) // 2 * 2
        for j, item in enumerate(rows[:n]):
            assigned.append({**item,
                "assigned_arm": "TOPOLOGY" if j % 2 == 0 else "GEOMETRY",
                "assigned_private_candidate_ref": item["selected_by_topology"] if j % 2 == 0 else item["selected_by_geometry"],
                "visits": 3,
                "minutes_per_visit": 30,
                "observers": 1,
                "planned_person_minutes": 90,
            })
        reserved.extend(rows[n:])
    return {
        "status": "PRIVATE_DESIGN_PREVIEW_NOT_A_FROZEN_FIELD_SCHEDULE",
        "assigned": assigned,
        "unassigned_balance_reserve": reserved,
        "ineligible_connected_patch_count": ineligible_count,
        "ineligible_connected_by_cohort": dict(sorted(ineligible_by_unit.items())),
        "can_schedule_equal_effort": bool(assigned),
        "field_outcomes_opened": False,
        "field_schedule_frozen": False,
        "new_cohort_identity_pinned": False,
        "original_patch_sha_pinned_for_new_cohort": False,
    }


def public_design_receipt(private_design: dict[str, Any]) -> dict[str, Any]:
    """Do not publish actual original private IDs/indices; use one aggregate digest."""
    validate_design_contract()
    if (private_design.get("status") != "PRIVATE_DESIGN_PREVIEW_NOT_A_FROZEN_FIELD_SCHEDULE"
            or private_design.get("field_outcomes_opened") is not False
            or private_design.get("field_schedule_frozen") is not False):
        raise ValueError("cannot publish a preview as completed field allocation")
    counts: dict[str, dict[str, Any]] = {}
    def ensure(unit: str) -> dict[str, Any]:
        if unit not in counts:
            counts[unit] = dict(assigned_topology=0, assigned_geometry=0,
                                shared_counterfactual_count=0, planned_person_minutes_per_arm=0,
                                balance_reserve_count=0, ineligible_connected_patch_count=0)
        return counts[unit]

    descriptors = []
    for unit, n in private_design.get("ineligible_connected_by_cohort", {}).items():
        ensure(unit)["ineligible_connected_patch_count"] = n
    for row in private_design.get("unassigned_balance_reserve", []):
        ensure(row["cohort_unit_id"])["balance_reserve_count"] += 1
    for item in private_design.get("assigned", []):
        unit = item["cohort_unit_id"]
        row = ensure(unit)
        arm = item["assigned_arm"]
        if arm not in ("TOPOLOGY", "GEOMETRY"):
            raise ValueError("unexpected trial arm")
        row["assigned_topology" if arm == "TOPOLOGY" else "assigned_geometry"] += 1
        row["shared_counterfactual_count"] += int(item["counterfactual_site_shared"])
        descriptors.append((unit, item["private_patch_ref"], arm, item["assigned_private_candidate_ref"]))
    for unit, v in counts.items():
        if v["assigned_topology"] != v["assigned_geometry"]:
            raise ValueError("unequal within-cohort arm effort")
        v["planned_person_minutes_per_arm"] = 90 * v["assigned_topology"]
        v["cohort_exposure"] = ("PREVIOUSLY_EXPOSED_DEVELOPMENT_ONLY" if unit in PREVIOUSLY_EXPOSED
                                else "UNREGISTERED_NEW_COHORT_CONFIRMATION_NOT_YET_AUTHORIZED")
    digest_input = "\n".join("\t".join(t) for t in sorted(descriptors)) + "\n"
    return {
        "schema_version": "acsp-connectivity-overlay-versus-geometry-site-trial-public-preview-v1",
        "status": "DESIGN_PREVIEW_ONLY_AWAITING_PRIVATE_GEOMETRY_AND_COHORT_PIN",
        "private_assignments_sha256": hashlib.sha256(digest_input.encode()).hexdigest(),
        "by_cohort": dict(sorted(counts.items())),
        "assigned_patch_count": len(descriptors),
        "unassigned_odd_balance_reserve_count": len(private_design["unassigned_balance_reserve"]),
        "ineligible_connected_patch_count": private_design["ineligible_connected_patch_count"],
        "fresh_independent_biological_validation": False,
        "field_outcomes_opened": False,
        "field_schedule_frozen": False,
        "real_candidate_geometry_used_now": False,
        "actual_field_effect_estimated": False,
        "original_three_arm_field_protocol_changed": False,
    }
