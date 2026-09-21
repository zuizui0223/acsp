#!/usr/bin/env python3
"""Derive fresh-SENTINEL field prefix depth from one movement constraint.

This adapter is strictly downstream G_F. It never changes the frozen ecological
candidate frame or any arm order. For each cohort unit it:

1. collapses the common 100-m candidate frame to one outcome-blind representative
   per already-frozen 5-km coarse coverage cell using only a stable candidate hash;
2. retrieves OSM road/trail/ferry reachability using one movement input;
3. runs the existing complete-coverage downstream selector at the frozen 5-km
   coarse redundancy scale;
4. uses only the resulting automatic selected count as the common no-skip prefix
   depth for all three frozen method arms;
5. combines that count with a separately frozen, outcome-blind per-candidate
   observation-effort protocol.

No site-count, Top-k, target-coverage, survey-day, monetary-budget, structural
score, field outcome, or arm-specific effort input is accepted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from acsp.osm_reachability import build_osm_patch_reachability_edges
from acsp.reachability import select_reachability_constrained_patches
from research.cirsium_fresh_sentinel_paths_v1 import (
    CANONICAL_OPERATIONAL_CAPACITY_PROFILE_REPO_PATH,
    CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH,
)

ROOT = Path(__file__).resolve().parents[1]
UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
COARSE_REDUNDANCY_M = 5000.0
CAPACITY_SCHEMA = "cirsium-fresh-sentinel-operational-capacity-profile-v1"
CAPACITY_STATUS = "PRE_OUTCOME_OPERATIONAL_CAPACITY_FROZEN"
EFFORT_SCHEMA = "cirsium-fresh-sentinel-standardized-effort-protocol-v1"
EFFORT_STATUS = "PRE_OUTCOME_STANDARDIZED_EFFORT_PROTOCOL_FROZEN"
PREFIX_METHOD = "OSM_COMPLETE_COARSE_COVERAGE_SELECTED_COUNT_V1"


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stable_hash(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _positive_float(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not number > 0:
        raise ValueError(f"{label} must be >0")
    return number


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be an integer >=1")
    return value


def validate_effort_protocol(value: dict[str, Any]) -> dict[str, dict[str, Any]]:
    expected = {
        "schema_version",
        "status",
        "cohort_unit_ids",
        "protocol_source_identity",
        "unit_effort",
        "prospective_field_outcomes_opened",
        "field_outcomes_used_to_set_effort",
        "candidate_identity_used_to_set_effort",
        "arm_specific_effort_allowed",
        "movement_constraint_used_to_set_effort",
        "post_outcome_effort_edits_allowed",
    }
    if set(value) != expected:
        raise ValueError("standardized effort protocol keys changed")
    if value.get("schema_version") != EFFORT_SCHEMA or value.get("status") != EFFORT_STATUS:
        raise ValueError("standardized effort protocol schema/status changed")
    if tuple(value.get("cohort_unit_ids") or ()) != UNITS:
        raise ValueError("standardized effort protocol cohort changed")
    if not str(value.get("protocol_source_identity") or "").strip():
        raise ValueError("protocol_source_identity must be non-empty")
    for key in (
        "prospective_field_outcomes_opened",
        "field_outcomes_used_to_set_effort",
        "candidate_identity_used_to_set_effort",
        "arm_specific_effort_allowed",
        "movement_constraint_used_to_set_effort",
        "post_outcome_effort_edits_allowed",
    ):
        if value.get(key) is not False:
            raise ValueError(f"{key} must be false before prospective outcome opening")

    rows = value.get("unit_effort")
    if not isinstance(rows, dict) or set(rows) != set(UNITS):
        raise ValueError("unit_effort must contain exactly the four frozen cohort units")
    required = {"visits_per_candidate", "search_minutes_per_visit", "observer_count"}
    out: dict[str, dict[str, Any]] = {}
    for unit in UNITS:
        row = rows[unit]
        if not isinstance(row, dict) or set(row) != required:
            raise ValueError(f"{unit} effort keys changed")
        out[unit] = {
            "visits_per_candidate": _positive_int(row["visits_per_candidate"], f"{unit}.visits_per_candidate"),
            "search_minutes_per_visit": _positive_float(row["search_minutes_per_visit"], f"{unit}.search_minutes_per_visit"),
            "observer_count": _positive_int(row["observer_count"], f"{unit}.observer_count"),
        }
    return out


def build_outcome_blind_coarse_representatives(frame: pd.DataFrame, *, unit_id: str) -> pd.DataFrame:
    required = {"candidate_cell_id", "coverage_cell_id", "latitude", "longitude"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"candidate frame missing required columns: {missing}")
    work = frame[list(required)].copy()
    if work.isna().any().any():
        raise ValueError("candidate frame representative columns must be complete")
    if work["candidate_cell_id"].astype(str).duplicated().any():
        raise ValueError("candidate_cell_id must be unique")
    work["_stable_hash"] = [_stable_hash(value) for value in work["candidate_cell_id"].astype(str)]
    reps = (
        work.sort_values(["coverage_cell_id", "_stable_hash"], kind="mergesort")
        .groupby("coverage_cell_id", sort=True, as_index=False)
        .first()
    )
    reps = reps.rename(columns={"coverage_cell_id": "candidate_patch_id"})
    reps["survey_area_id"] = str(unit_id)
    reps["patch_merge_distance_m"] = float(COARSE_REDUNDANCY_M)
    reps["representative_rule"] = "STABLE_HASH_WITHIN_FROZEN_COARSE_CELL_V1"
    return reps[
        [
            "candidate_patch_id",
            "survey_area_id",
            "latitude",
            "longitude",
            "patch_merge_distance_m",
            "representative_rule",
        ]
    ].reset_index(drop=True)


def automatic_prefix_depth_from_reachability(
    coarse_representatives: pd.DataFrame,
    reachability_edges: pd.DataFrame,
) -> tuple[int, dict[str, Any]]:
    selected, audit = select_reachability_constrained_patches(
        coarse_representatives,
        reachability_edges,
        id_col="candidate_patch_id",
        coverage_group_col="survey_area_id",
        radius_col="candidate_patch_radius_m",
    )
    depth = int(len(selected))
    if depth < 1:
        raise ValueError("automatic downstream selector returned no operational representatives")
    return depth, audit.as_dict()


def derive_operational_capacity_profile(
    private_pre_field_root: Path,
    effort_protocol_path: Path,
    *,
    max_network_transition_km: float,
    out_json: Path,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    movement_km = _positive_float(max_network_transition_km, "max_network_transition_km")
    repo = Path(repo_root).resolve()
    private_root = Path(private_pre_field_root).resolve()
    effort_path = Path(effort_protocol_path).resolve()
    out_path = Path(out_json).resolve()

    if _inside(private_root, repo):
        raise ValueError("private pre-field root must remain outside the public repository")
    if out_path.exists():
        raise ValueError("refusing to overwrite an existing operational capacity profile")
    if not effort_path.is_file():
        raise ValueError("missing standardized effort protocol")
    effort = validate_effort_protocol(_load_json(effort_path))

    capacity: dict[str, Any] = {}
    frame_hashes: dict[str, str] = {}
    audits: dict[str, Any] = {}
    for unit in UNITS:
        frame_path = private_root / unit / "candidate_frame_pre_field.csv"
        if not frame_path.is_file():
            raise ValueError(f"missing frozen candidate frame: {frame_path}")
        frame = pd.read_csv(frame_path)
        frame_hashes[unit] = _sha256(frame_path)
        reps = build_outcome_blind_coarse_representatives(frame, unit_id=unit)

        patch_edges, _attachments, _nodes, _network_edges, _area_audit, osm_audit = (
            build_osm_patch_reachability_edges(
                reps,
                max_network_transition_km=movement_km,
                area_col="survey_area_id",
            )
        )
        provider = osm_audit.get("provider")
        if not isinstance(provider, dict) or int(provider.get("successful_area_count", 0)) < 1:
            raise RuntimeError(f"{unit} OSM movement provider unavailable; prefix depth not inferred")

        depth, selection_audit = automatic_prefix_depth_from_reachability(reps, patch_edges)
        row = effort[unit]
        capacity[unit] = {
            "prefix_depth": depth,
            "visits_per_candidate": row["visits_per_candidate"],
            "search_minutes_per_visit": row["search_minutes_per_visit"],
            "observer_count": row["observer_count"],
        }
        provider_success[unit] = True

    result = {
        "schema_version": CAPACITY_SCHEMA,
        "status": CAPACITY_STATUS,
        "cohort_unit_ids": list(UNITS),
        "capacity_source_identity": PREFIX_METHOD,
        "movement_constraint_mode": "osm_weighted_transport_network",
        "max_network_transition_km": movement_km,
        "automatic_prefix_depth_method": PREFIX_METHOD,
        "coarse_redundancy_scale_m": COARSE_REDUNDANCY_M,
        "coarse_representative_rule": "STABLE_HASH_WITHIN_FROZEN_COARSE_CELL_V1",
        "standardized_effort_protocol_sha256": _sha256(effort_path),
        "private_candidate_frame_sha256_by_unit": frame_hashes,
        "unit_capacity": capacity,
        "movement_provider_successful_by_unit": provider_success,
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used_to_set_capacity": False,
        "frozen_common_candidate_geometry_used_for_movement_capacity": True,
        "arm_rank_used_to_set_prefix_depth": False,
        "candidate_identity_or_coordinates_exported": False,
        "structural_score_used_to_set_prefix_depth": False,
        "arm_specific_capacity_allowed": False,
        "survey_days_input": False,
        "monetary_budget_input": False,
        "user_site_count_input": False,
        "user_coverage_target_input": False,
        "post_outcome_capacity_edits_allowed": False,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-pre-field-root", type=Path, required=True)
    parser.add_argument("--effort-protocol", type=Path, default=Path(CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH))
    parser.add_argument("--max-network-transition-km", type=float, required=True)
    parser.add_argument("--out-json", type=Path, default=Path(CANONICAL_OPERATIONAL_CAPACITY_PROFILE_REPO_PATH))
    args = parser.parse_args()
    result = derive_operational_capacity_profile(
        args.private_pre_field_root,
        args.effort_protocol,
        max_network_transition_km=args.max_network_transition_km,
        out_json=args.out_json,
    )
    print(json.dumps({
        "status": result["status"],
        "max_network_transition_km": result["max_network_transition_km"],
        "prefix_depth_by_unit": {
            unit: result["unit_capacity"][unit]["prefix_depth"] for unit in UNITS
        },
        "out_json": str(args.out_json),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
