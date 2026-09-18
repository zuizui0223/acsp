#!/usr/bin/env python3
"""Export a public-safe hash-only freeze receipt from private fresh-SENTINEL outputs.

This is the candidate/order prescription provenance step. It never reads candidate
coordinates or field outcomes. It selects only method identities, unit identities
and SHA-256 fingerprints from already-completed private pre-field receipts. The
resulting JSON is safe to commit publicly, but generation and prescription pinning
alone do not authorize prospective outcome opening: field evaluation semantics and
the actual allocation/effort schedule must also be frozen and pinned pre-outcome.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from research.cirsium_fresh_sentinel_paths_v1 import (
    CANONICAL_CANDIDATE_RECEIPT_REPO_PATH,
    CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH,
    CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH,
    CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH,
    require_canonical_repo_path,
)

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
PRIVATE_TOP_STATUS = "ALL_FOUR_PRE_FIELD_METHOD_AND_COMPARATORS_FROZEN"
PRIVATE_UNIT_STATUS = "PRE_FIELD_METHOD_AND_COMPARATORS_FROZEN"
FIELD_EVALUATION_CONTRACT = CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH


def _inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT.resolve())
        return True
    except ValueError:
        return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"missing private freeze receipt: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"receipt must be a JSON object: {path}")
    return value


def build_public_freeze_receipt(private_root: Path) -> dict[str, Any]:
    private_root = private_root.resolve()
    if _inside_repo(private_root):
        raise ValueError("private pre-field root must remain outside the public repository")
    top_path = private_root / "pre_field_freeze_receipt.json"
    top = _load(top_path)
    if top.get("status") != PRIVATE_TOP_STATUS:
        raise ValueError("private orchestration has not reached the all-four frozen state")
    if tuple(top.get("units") or ()) != EXPECTED_UNITS:
        raise ValueError("private orchestration unit set does not match the frozen fresh cohort")
    if top.get("field_outcomes_opened") is not False:
        raise ValueError("private top receipt cannot declare opened field outcomes")
    if top.get("replacement_taxon_allowed") is not False:
        raise ValueError("private top receipt must preserve the no-replacement rule")
    if top.get("ready_for_future_prospective_outcome_opening") is not False:
        raise ValueError("private top receipt must not authorize outcome opening before all public pre-outcome gates")
    if top.get("public_hash_receipt_committed") is not False:
        raise ValueError("private top receipt cannot pre-claim that the public receipt is committed")

    units: dict[str, Any] = {}
    for unit_id in EXPECTED_UNITS:
        unit_path = private_root / unit_id / "pre_field_freeze_receipt.json"
        unit = _load(unit_path)
        if unit.get("status") != PRIVATE_UNIT_STATUS or unit.get("cohort_unit_id") != unit_id:
            raise ValueError(f"private unit receipt is not terminal/frozen for {unit_id}")
        if unit.get("field_outcomes_opened") is not False:
            raise ValueError(f"private unit receipt declares opened field outcomes: {unit_id}")
        if unit.get("replacement_taxon_allowed") is not False or unit.get("retuning_after_failure_allowed") is not False:
            raise ValueError(f"private unit receipt weakens frozen failure semantics: {unit_id}")
        candidate_hash = str(unit.get("candidate_frame_sha256") or "")
        order_hashes = unit.get("order_sha256")
        if len(candidate_hash) != 64 or not isinstance(order_hashes, dict) or set(order_hashes) != {
            "coverage_then_fine_structure", "coverage_only", "fine_spatial_balance"
        }:
            raise ValueError(f"private unit receipt lacks complete frozen hashes: {unit_id}")
        if any(len(str(value)) != 64 for value in order_hashes.values()):
            raise ValueError(f"private unit order hash is malformed: {unit_id}")
        units[unit_id] = {
            "species_binomial": str(unit.get("species_binomial") or ""),
            "feature_family": str(unit.get("feature_family") or ""),
            "candidate_frame_sha256": candidate_hash,
            "order_sha256": {key: str(order_hashes[key]) for key in sorted(order_hashes)},
            "private_unit_receipt_sha256": _sha256(unit_path),
        }

    return {
        "schema_version": "cirsium-fresh-sentinel-public-pre-field-freeze-v1",
        "status": "PUBLIC_HASH_FREEZE_READY_FOR_COMMIT",
        "private_top_receipt_sha256": _sha256(top_path),
        "units": units,
        "method_identity": str(top.get("method_identity") or ""),
        "coverage_identity": str(top.get("coverage_identity") or ""),
        "coverage_only_comparator": str(top.get("coverage_only_comparator") or ""),
        "fine_spatial_comparator": str(top.get("fine_spatial_comparator") or ""),
        "fine_candidate_spacing_m": int(top.get("fine_candidate_spacing_m")),
        "coarse_coverage_cell_size_m": int(top.get("coarse_coverage_cell_size_m")),
        "graph_radius_cells": int(top.get("graph_radius_cells")),
        "coordinate_bearing_data_included": False,
        "private_paths_included": False,
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used_to_choose_or_rank": False,
        "replacement_taxon_allowed": False,
        "post_freeze_retuning_allowed": False,
        "public_safe_to_commit": True,
        "outcome_opening_authorized_by_generation_alone": False,
        "public_receipt_commit_required_before_outcome_opening": True,
        "public_receipt_commit_verified": False,
        "canonical_receipt_repo_path": CANONICAL_CANDIDATE_RECEIPT_REPO_PATH,
        "canonical_field_schedule_receipt_repo_path": CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH,
        "field_evaluation_contract": FIELD_EVALUATION_CONTRACT,
        "field_log_template": CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH,
        "field_allocation_and_effort_schedule_required_before_outcome_opening": True,
        "field_allocation_and_effort_schedule_pinned": False,
        "outcome_opening_gate": "Pinning this exact receipt closes only the candidate/order prescription gate. Freeze and publicly pin the field analysis unit, repeated-visit rule, comparator assignment, numeric effort metric, and candidate-specific allocation/effort schedule before prospective outcomes are opened."
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, default=Path(CANONICAL_CANDIDATE_RECEIPT_REPO_PATH))
    args = parser.parse_args()
    out_json = require_canonical_repo_path(
        args.out_json,
        repo_root=ROOT,
        expected_repo_path=CANONICAL_CANDIDATE_RECEIPT_REPO_PATH,
        label="public candidate/order receipt",
    )
    if out_json.exists():
        raise SystemExit("refusing to overwrite an existing public freeze receipt")
    receipt = build_public_freeze_receipt(args.private_root)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "out_json": str(out_json)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
