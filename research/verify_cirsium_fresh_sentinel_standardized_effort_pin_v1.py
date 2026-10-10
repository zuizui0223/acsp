#!/usr/bin/env python3
"""Verify the immutable pre-outcome pin of the canonical fresh-SENTINEL effort protocol.

The canonical standardized effort protocol is fixed before private range-sector
geometry is supplied. Current bytes must equal the bytes in the first commit that
added the canonical path, preventing later geometry- or outcome-informed effort
retuning.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from research.cirsium_fresh_sentinel_paths_v1 import (
    CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH,
    require_canonical_repo_path,
)
from research.derive_cirsium_fresh_sentinel_movement_capacity_v1 import (
    validate_effort_protocol,
)

ROOT = Path(__file__).resolve().parents[1]
VERIFIED_STATUS = "STANDARDIZED_EFFORT_PROTOCOL_COMMITTED_AND_PINNED"
EXPECTED_SOURCE_IDENTITY = "ACSP_CIRSIUM_FIXED_TIMED_SEARCH_3X30MIN_1OBSERVER_V1"
EXPECTED_UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
EXPECTED_EFFORT = {
    "visits_per_candidate": 3,
    "search_minutes_per_visit": 30.0,
    "observer_count": 1,
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
        raise ValueError("could not identify the first commit that added the standardized effort protocol")
    return commits[-1]


def _validate_frozen_values(value: dict[str, Any]) -> None:
    normalized = validate_effort_protocol(value)
    if value.get("protocol_source_identity") != EXPECTED_SOURCE_IDENTITY:
        raise ValueError("standardized effort protocol source identity changed")
    if tuple(value.get("cohort_unit_ids") or ()) != EXPECTED_UNITS:
        raise ValueError("standardized effort protocol cohort changed")
    for unit in EXPECTED_UNITS:
        if normalized[unit] != EXPECTED_EFFORT:
            raise ValueError(f"standardized effort protocol values changed for {unit}; current bytes are not the exact current standardized effort protocol")


def verify_standardized_effort_pin(
    protocol_path: Path = Path(CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH),
    *,
    repo_root: Path = ROOT,
    expected_pin_commit: str = "",
) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    path = require_canonical_repo_path(
        Path(protocol_path),
        repo_root=repo,
        expected_repo_path=CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH,
        label="standardized effort protocol",
    )
    if not path.is_file():
        raise ValueError(f"missing standardized effort protocol: {path}")
    relative = path.relative_to(repo).as_posix()

    payload = path.read_bytes()
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("standardized effort protocol must be a JSON object")
    _validate_frozen_values(value)

    try:
        _git(repo, "ls-files", "--error-unmatch", "--", relative)
    except subprocess.CalledProcessError as exc:
        raise ValueError("standardized effort protocol is not tracked by git") from exc
    if _git(repo, "status", "--porcelain", "--", relative).stdout.strip():
        raise ValueError("standardized effort protocol has uncommitted changes")

    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    head_payload = _git(repo, "show", f"HEAD:{relative}", text=False).stdout
    if head_payload != payload:
        raise ValueError("working standardized effort bytes do not equal HEAD")

    pin_commit = _first_add_commit(repo, relative)
    initial_payload = _git(repo, "show", f"{pin_commit}:{relative}", text=False).stdout
    if initial_payload != payload:
        raise ValueError("standardized effort bytes differ from the immutable first-add pin commit")
    if expected_pin_commit and pin_commit != str(expected_pin_commit).strip():
        raise ValueError("standardized effort pin commit does not match the expected immutable commit")
    try:
        _git(repo, "merge-base", "--is-ancestor", pin_commit, head)
    except subprocess.CalledProcessError as exc:
        raise ValueError("standardized effort pin commit is not an ancestor of HEAD") from exc

    return {
        "schema_version": "cirsium-fresh-sentinel-standardized-effort-pin-verification-v1",
        "status": VERIFIED_STATUS,
        "protocol_repo_path": relative,
        "protocol_sha256": _sha256_bytes(payload),
        "pin_commit": pin_commit,
        "pin_rule": "first commit adding the canonical effort protocol; later byte changes are forbidden",
        "verified_head": head,
        "standardized_effort_protocol_pin_gate_satisfied": True,
        "prospective_field_outcomes_opened": False,
        "private_candidate_geometry_opened_by_verifier": False,
        "authorization_scope": "effort-protocol provenance gate only; no biological result, occupancy, or effort optimality claim",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--protocol",
        type=Path,
        default=Path(CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH),
    )
    parser.add_argument("--expected-pin-commit", default="")
    args = parser.parse_args()
    result = verify_standardized_effort_pin(
        args.protocol,
        expected_pin_commit=args.expected_pin_commit,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
