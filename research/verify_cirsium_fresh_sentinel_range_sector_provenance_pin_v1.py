#!/usr/bin/env python3
"""Verify immutable public-safe range-sector provenance before private geometry.

This gate prevents fresh-SENTINEL private geometry from being opened merely
because a Polygon exists. Every frozen unit must first have an upstream aza3
exact-site freeze attestation, and CIR12/CIR13 must additionally attest the
predeclared P02 first-validated-wild-population dependency.

The canonical receipt is coordinate-free, public-safe, and first-add immutable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
import subprocess
from typing import Any

from research.cirsium_fresh_sentinel_paths_v1 import (
    CANONICAL_RANGE_SECTOR_PROVENANCE_REPO_PATH,
    require_canonical_repo_path,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "cirsium-fresh-sentinel-range-sector-provenance-v1"
STATUS = "PRE_GEOMETRY_RANGE_SECTOR_PROVENANCE_FROZEN"
VERIFIED_STATUS = "RANGE_SECTOR_PROVENANCE_COMMITTED_AND_PINNED"
CONTRACT_VERSION = "chapter3_exact_site_freeze_v8"
EXPECTED_UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
EXPECTED = {
    "CIR02": {
        "species_binomial": "Cirsium inundatum",
        "aza3_slot_id": "P1_Cirsium_inundatum_A",
        "range_sector_label": "青森県側の確認済み野生集団",
        "p02_required": False,
    },
    "CIR06": {
        "species_binomial": "Cirsium yezoalpinum",
        "aza3_slot_id": "P1_Cirsium_yezoalpinum_A",
        "range_sector_label": "知床山系の確認済み野生集団",
        "p02_required": False,
    },
    "CIR12": {
        "species_binomial": "Cirsium dipsacolepis",
        "aza3_slot_id": "P6_Cirsium_dipsacolepis_OWN",
        "range_sector_label": "P02で最初に検証される野生集団セクター",
        "p02_required": True,
    },
    "CIR13": {
        "species_binomial": "Cirsium lineare",
        "aza3_slot_id": "P6_Cirsium_lineare_OWN",
        "range_sector_label": "P02で最初に検証される野生集団セクター",
        "p02_required": True,
    },
}
TOP_KEYS = {
    "schema_version",
    "status",
    "cohort_unit_ids",
    "aza3_exact_site_contract_version",
    "upstream_snapshot_commit",
    "unit_provenance",
    "exact_coordinates_included",
    "sensitive_access_instructions_included",
    "prospective_acsp_field_outcomes_opened",
    "acsp_field_outcomes_used_to_define_sector",
    "post_geometry_edits_allowed",
    "post_outcome_edits_allowed",
    "public_safe_to_commit",
}
UNIT_KEYS = {
    "species_binomial",
    "aza3_slot_id",
    "range_sector_label",
    "freeze_status",
    "current_occurrence_supported",
    "permission_gate_satisfied",
    "target_locality_id",
    "private_exact_site_record_exists",
    "range_sector_geometry_may_now_be_materialized",
    "p02_first_validated_wild_population_required",
    "p02_first_validated_wild_population_link_satisfied",
}


def _git(repo_root: Path, *args: str, text: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=text,
    )


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _first_add_commit(repo: Path, relative: str) -> str:
    commits = [
        line.strip()
        for line in _git(repo, "log", "--diff-filter=A", "--format=%H", "--", relative).stdout.splitlines()
        if line.strip()
    ]
    if not commits:
        raise ValueError("could not identify first commit adding range-sector provenance")
    return commits[-1]


def validate_range_sector_provenance(value: dict[str, Any]) -> None:
    if set(value) != TOP_KEYS:
        raise ValueError("range-sector provenance top-level keys changed")
    if value.get("schema_version") != SCHEMA_VERSION or value.get("status") != STATUS:
        raise ValueError("range-sector provenance schema/status changed")
    if tuple(value.get("cohort_unit_ids") or ()) != EXPECTED_UNITS:
        raise ValueError("range-sector provenance cohort changed")
    if value.get("aza3_exact_site_contract_version") != CONTRACT_VERSION:
        raise ValueError("aza3 exact-site contract identity changed")
    commit = str(value.get("upstream_snapshot_commit") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("upstream_snapshot_commit must be a lowercase 40-hex commit SHA")

    units = value.get("unit_provenance")
    if not isinstance(units, dict) or set(units) != set(EXPECTED_UNITS):
        raise ValueError("unit_provenance must contain exactly the frozen four units")
    for unit in EXPECTED_UNITS:
        row = units[unit]
        if not isinstance(row, dict) or set(row) != UNIT_KEYS:
            raise ValueError(f"{unit} provenance keys changed")
        expected = EXPECTED[unit]
        for key in ("species_binomial", "aza3_slot_id", "range_sector_label"):
            if row.get(key) != expected[key]:
                raise ValueError(f"{unit} {key} changed")
        if row.get("freeze_status") != "FROZEN_FOR_FIELD_COLLECTION":
            raise ValueError(f"{unit} exact site is not frozen for field collection")
        for key in (
            "current_occurrence_supported",
            "permission_gate_satisfied",
            "private_exact_site_record_exists",
            "range_sector_geometry_may_now_be_materialized",
        ):
            if row.get(key) is not True:
                raise ValueError(f"{unit} {key} must be true before private geometry")
        locality_id = str(row.get("target_locality_id") or "").strip()
        if not locality_id:
            raise ValueError(f"{unit} target_locality_id must be non-empty")
        p02_required = bool(expected["p02_required"])
        if row.get("p02_first_validated_wild_population_required") is not p02_required:
            raise ValueError(f"{unit} P02 dependency identity changed")
        if row.get("p02_first_validated_wild_population_link_satisfied") is not p02_required:
            raise ValueError(f"{unit} P02 dependency linkage is not satisfied as frozen")

    for key in (
        "exact_coordinates_included",
        "sensitive_access_instructions_included",
        "prospective_acsp_field_outcomes_opened",
        "acsp_field_outcomes_used_to_define_sector",
        "post_geometry_edits_allowed",
        "post_outcome_edits_allowed",
    ):
        if value.get(key) is not False:
            raise ValueError(f"{key} must be false in public pre-geometry provenance")
    if value.get("public_safe_to_commit") is not True:
        raise ValueError("range-sector provenance must be public-safe before pinning")


def verify_range_sector_provenance_pin(
    provenance_path: Path = Path(CANONICAL_RANGE_SECTOR_PROVENANCE_REPO_PATH),
    *,
    repo_root: Path = ROOT,
    expected_pin_commit: str = "",
    must_be_ancestor_of: str = "",
) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    path = require_canonical_repo_path(
        Path(provenance_path),
        repo_root=repo,
        expected_repo_path=CANONICAL_RANGE_SECTOR_PROVENANCE_REPO_PATH,
        label="range-sector provenance",
    )
    if not path.is_file():
        raise ValueError(f"missing range-sector provenance: {path}")
    relative = path.relative_to(repo).as_posix()

    payload = path.read_bytes()
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("range-sector provenance must be a JSON object")
    validate_range_sector_provenance(value)

    try:
        _git(repo, "ls-files", "--error-unmatch", "--", relative)
    except subprocess.CalledProcessError as exc:
        raise ValueError("range-sector provenance is not tracked by git") from exc
    if _git(repo, "status", "--porcelain", "--", relative).stdout.strip():
        raise ValueError("range-sector provenance has uncommitted changes")

    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    head_payload = _git(repo, "show", f"HEAD:{relative}", text=False).stdout
    if head_payload != payload:
        raise ValueError("working range-sector provenance bytes do not equal HEAD")

    pin_commit = _first_add_commit(repo, relative)
    initial_payload = _git(repo, "show", f"{pin_commit}:{relative}", text=False).stdout
    if initial_payload != payload:
        raise ValueError("range-sector provenance bytes differ from the immutable first-add pin commit")
    if expected_pin_commit and pin_commit != str(expected_pin_commit).strip():
        raise ValueError("range-sector provenance pin commit does not match expected immutable commit")
    try:
        _git(repo, "merge-base", "--is-ancestor", pin_commit, head)
    except subprocess.CalledProcessError as exc:
        raise ValueError("range-sector provenance pin commit is not an ancestor of HEAD") from exc

    if must_be_ancestor_of:
        target = str(must_be_ancestor_of).strip()
        if target == pin_commit:
            raise ValueError("range-sector provenance must be pinned before candidate/order prescription")
        try:
            _git(repo, "merge-base", "--is-ancestor", pin_commit, target)
        except subprocess.CalledProcessError as exc:
            raise ValueError("range-sector provenance was not pinned before candidate/order prescription") from exc

    return {
        "schema_version": "cirsium-fresh-sentinel-range-sector-provenance-pin-verification-v1",
        "status": VERIFIED_STATUS,
        "provenance_repo_path": relative,
        "provenance_sha256": _sha256_bytes(payload),
        "pin_commit": pin_commit,
        "pin_rule": "first commit adding canonical range-sector provenance; later byte changes are forbidden",
        "verified_head": head,
        "upstream_snapshot_commit": value["upstream_snapshot_commit"],
        "range_sector_provenance_pin_gate_satisfied": True,
        "prospective_acsp_field_outcomes_opened": False,
        "private_geometry_opened_by_verifier": False,
        "authorization_scope": "upstream source provenance only; does not authorize outcome opening or expose coordinates",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provenance",
        type=Path,
        default=Path(CANONICAL_RANGE_SECTOR_PROVENANCE_REPO_PATH),
    )
    parser.add_argument("--expected-pin-commit", default="")
    parser.add_argument("--must-be-ancestor-of", default="")
    args = parser.parse_args()
    result = verify_range_sector_provenance_pin(
        args.provenance,
        expected_pin_commit=args.expected_pin_commit,
        must_be_ancestor_of=args.must_be_ancestor_of,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
