#!/usr/bin/env python3
"""Verify a private field schedule against the exact frozen private candidate orders.

This verifier reads only pre-outcome private artifacts. It proves that every
scheduled private_candidate_ref exists in the correct frozen arm order and that
the selected unique candidates form a no-skip prefix of that exact order.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
EXPECTED_CANDIDATE_STATUS = "PUBLIC_HASH_FREEZE_READY_FOR_COMMIT"
EXPECTED_PRIVATE_TOP_STATUS = "ALL_FOUR_PRE_FIELD_METHOD_AND_COMPARATORS_FROZEN"
EXPECTED_PRIVATE_UNIT_STATUS = "PRE_FIELD_METHOD_AND_COMPARATORS_FROZEN"
EXPECTED_ASSIGNMENT_IDENTITY = "FROZEN_ORDER_PREFIX_V1"
ARM_TO_ORDER = {
    "COVERAGE_THEN_FINE_STRUCTURE_V1": "coverage_then_fine_structure",
    "COVERAGE_ONLY_STABLE_WITHIN_CELL_V1": "coverage_only",
    "MORTON_DYADIC_COVERAGE_ORDER_V1": "fine_spatial_balance",
}


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"missing JSON input: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON input must be an object: {path}")
    return value


def _candidate_ids(path: Path, *, require_rank: bool) -> list[str]:
    if not path.is_file():
        raise ValueError(f"missing frozen private CSV: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        if "candidate_cell_id" not in fieldnames:
            raise ValueError(f"frozen private CSV lacks candidate_cell_id: {path}")
        rows = list(reader)
    ids = [str(row.get("candidate_cell_id") or "").strip() for row in rows]
    if not ids or any(not value for value in ids) or len(set(ids)) != len(ids):
        raise ValueError(f"candidate_cell_id must be complete and unique: {path}")
    if require_rank:
        if "decision_rank" not in fieldnames:
            raise ValueError(f"frozen order lacks decision_rank: {path}")
        try:
            ranks = [int(str(row.get("decision_rank") or "")) for row in rows]
        except ValueError as exc:
            raise ValueError(f"decision_rank must be integer-valued: {path}") from exc
        if ranks != list(range(1, len(rows) + 1)):
            raise ValueError(f"frozen order decision_rank must be exact 1..N in row order: {path}")
    return ids


def validate_private_schedule_membership(
    schedule_path: Path,
    candidate_receipt_path: Path,
    private_pre_field_root: Path,
    *,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    schedule_path = Path(schedule_path).resolve()
    candidate_receipt_path = Path(candidate_receipt_path).resolve()
    private_root = Path(private_pre_field_root).resolve()

    if _inside(schedule_path, repo):
        raise ValueError("private field schedule must remain outside the public repository")
    if _inside(private_root, repo):
        raise ValueError("private pre-field root must remain outside the public repository")
    if not private_root.is_dir():
        raise ValueError(f"missing private pre-field root: {private_root}")
    if not _inside(candidate_receipt_path, repo):
        raise ValueError("candidate/order public receipt must be inside the repository")

    schedule = _load_json(schedule_path)
    if schedule.get("comparator_assignment_identity") != EXPECTED_ASSIGNMENT_IDENTITY:
        raise ValueError("comparator assignment must use the frozen no-skip order-prefix identity")

    candidate = _load_json(candidate_receipt_path)
    if candidate.get("status") != EXPECTED_CANDIDATE_STATUS:
        raise ValueError("candidate/order public receipt is not in the frozen commit-ready state")

    top_path = private_root / "pre_field_freeze_receipt.json"
    top = _load_json(top_path)
    if top.get("status") != EXPECTED_PRIVATE_TOP_STATUS:
        raise ValueError("private pre-field root is not in the all-four frozen state")
    if tuple(top.get("units") or ()) != EXPECTED_UNITS:
        raise ValueError("private pre-field root cohort differs from the frozen fresh cohort")
    if candidate.get("private_top_receipt_sha256") != _sha256(top_path):
        raise ValueError("private pre-field root does not match the public candidate/order receipt")

    public_units = candidate.get("units")
    if not isinstance(public_units, dict) or tuple(public_units) != EXPECTED_UNITS:
        raise ValueError("public candidate/order receipt must contain the exact four frozen units in order")

    ordered_ids: dict[str, dict[str, list[str]]] = {unit: {} for unit in EXPECTED_UNITS}
    for unit in EXPECTED_UNITS:
        unit_dir = private_root / unit
        unit_receipt_path = unit_dir / "pre_field_freeze_receipt.json"
        unit_receipt = _load_json(unit_receipt_path)
        public_unit = public_units[unit]
        if not isinstance(public_unit, dict):
            raise ValueError(f"public candidate/order unit block malformed: {unit}")
        if unit_receipt.get("status") != EXPECTED_PRIVATE_UNIT_STATUS or unit_receipt.get("cohort_unit_id") != unit:
            raise ValueError(f"private unit receipt is not frozen for {unit}")
        if public_unit.get("private_unit_receipt_sha256") != _sha256(unit_receipt_path):
            raise ValueError(f"private unit receipt hash does not match public receipt: {unit}")

        candidate_frame = unit_dir / "candidate_frame_pre_field.csv"
        candidate_frame_hash = _sha256(candidate_frame)
        if unit_receipt.get("candidate_frame_sha256") != candidate_frame_hash:
            raise ValueError(f"private candidate-frame hash drifted: {unit}")
        if public_unit.get("candidate_frame_sha256") != candidate_frame_hash:
            raise ValueError(f"public candidate-frame hash does not match private frame: {unit}")
        frame_set = set(_candidate_ids(candidate_frame, require_rank=False))

        order_files = unit_receipt.get("order_files")
        order_hashes = unit_receipt.get("order_sha256")
        public_order_hashes = public_unit.get("order_sha256")
        expected_order_names = set(ARM_TO_ORDER.values())
        if not isinstance(order_files, dict) or set(order_files) != expected_order_names:
            raise ValueError(f"private unit order-file map incomplete: {unit}")
        if not isinstance(order_hashes, dict) or set(order_hashes) != expected_order_names:
            raise ValueError(f"private unit order hashes incomplete: {unit}")
        if not isinstance(public_order_hashes, dict) or set(public_order_hashes) != expected_order_names:
            raise ValueError(f"public unit order hashes incomplete: {unit}")

        for arm, order_name in ARM_TO_ORDER.items():
            order_path = (unit_dir / str(order_files[order_name])).resolve()
            if not _inside(order_path, unit_dir):
                raise ValueError(f"private order path escapes unit directory: {unit}/{order_name}")
            order_hash = _sha256(order_path)
            if str(order_hashes[order_name]) != order_hash:
                raise ValueError(f"private frozen order hash drifted: {unit}/{order_name}")
            if str(public_order_hashes[order_name]) != order_hash:
                raise ValueError(f"public receipt order hash does not match private frozen order: {unit}/{order_name}")
            ids = _candidate_ids(order_path, require_rank=True)
            if set(ids) != frame_set:
                raise ValueError(f"frozen arm order candidate set differs from frozen candidate frame: {unit}/{order_name}")
            ordered_ids[unit][arm] = ids

    assignments = schedule.get("assignments")
    if not isinstance(assignments, list) or not assignments:
        raise ValueError("private field schedule must contain assignments")

    selected: dict[str, dict[str, list[str]]] = {
        unit: {arm: [] for arm in ARM_TO_ORDER} for unit in EXPECTED_UNITS
    }
    for index, row in enumerate(assignments):
        if not isinstance(row, dict):
            raise ValueError(f"assignment {index} must be an object")
        unit = str(row.get("cohort_unit_id") or "")
        arm = str(row.get("method_arm") or "")
        candidate_ref = str(row.get("private_candidate_ref") or "").strip()
        if unit not in EXPECTED_UNITS or arm not in ARM_TO_ORDER or not candidate_ref:
            raise ValueError(f"assignment {index} has invalid unit/arm/candidate reference")
        if candidate_ref not in set(ordered_ids[unit][arm]):
            raise ValueError(f"assignment {index} candidate is not present in the exact frozen order for {unit}/{arm}")
        if candidate_ref not in selected[unit][arm]:
            selected[unit][arm].append(candidate_ref)

    prefix_lengths: dict[str, dict[str, int]] = {unit: {} for unit in EXPECTED_UNITS}
    for unit in EXPECTED_UNITS:
        for arm in ARM_TO_ORDER:
            chosen = selected[unit][arm]
            expected_prefix = ordered_ids[unit][arm][: len(chosen)]
            if set(chosen) != set(expected_prefix):
                raise ValueError(f"scheduled unique candidates are not a no-skip frozen-order prefix for {unit}/{arm}")
            prefix_lengths[unit][arm] = len(chosen)

    return {
        "status": "PRIVATE_FIELD_SCHEDULE_MEMBERSHIP_AND_PREFIX_VALID",
        "cohort_unit_ids": list(EXPECTED_UNITS),
        "private_pre_field_top_receipt_sha256": _sha256(top_path),
        "private_candidate_membership_verified": True,
        "private_pre_field_receipt_hash_linkage_verified": True,
        "frozen_order_hash_linkage_verified": True,
        "frozen_order_prefix_verified": True,
        "selected_unique_candidate_count_by_unit_arm": prefix_lengths,
        "prospective_field_outcomes_opened": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schedule", type=Path, required=True)
    parser.add_argument("--candidate-receipt", type=Path, required=True)
    parser.add_argument("--private-pre-field-root", type=Path, required=True)
    args = parser.parse_args()
    result = validate_private_schedule_membership(args.schedule, args.candidate_receipt, args.private_pre_field_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
