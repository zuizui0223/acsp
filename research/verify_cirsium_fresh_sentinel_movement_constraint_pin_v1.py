#!/usr/bin/env python3
"""Verify the immutable pre-geometry pin of the fresh-SENTINEL movement constraint."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
from typing import Any

from research.cirsium_fresh_sentinel_paths_v1 import (
    CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH,
    require_canonical_repo_path,
)
from research.freeze_cirsium_fresh_sentinel_movement_constraint_v1 import (
    SCHEMA,
    SOURCE_IDENTITY,
    STATUS,
)

ROOT = Path(__file__).resolve().parents[1]
VERIFIED_STATUS = "MOVEMENT_CONSTRAINT_COMMITTED_AND_PINNED"
EXPECTED_KEYS = {
    "schema_version",
    "status",
    "source_identity",
    "movement_constraint_mode",
    "max_network_transition_km",
    "private_range_sector_geometry_opened_when_declared",
    "candidate_identity_used_to_set_constraint",
    "prospective_field_outcomes_opened",
    "field_outcomes_used_to_set_constraint",
    "survey_days_input",
    "monetary_budget_input",
    "user_site_count_input",
    "user_coverage_target_input",
    "post_geometry_edits_allowed",
    "post_outcome_edits_allowed",
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
        raise ValueError("could not identify the first commit that added the movement constraint")
    return commits[-1]


def _validate(value: dict[str, Any]) -> float:
    if set(value) != EXPECTED_KEYS:
        raise ValueError("movement constraint keys changed")
    if value.get("schema_version") != SCHEMA or value.get("status") != STATUS:
        raise ValueError("movement constraint schema/status changed")
    if value.get("source_identity") != SOURCE_IDENTITY:
        raise ValueError("movement constraint source identity changed")
    if value.get("movement_constraint_mode") != "osm_weighted_transport_network":
        raise ValueError("movement constraint mode changed")
    raw = value.get("max_network_transition_km")
    if isinstance(raw, bool):
        raise ValueError("max_network_transition_km must be numeric")
    try:
        movement_km = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("max_network_transition_km must be numeric") from exc
    if not math.isfinite(movement_km) or movement_km <= 0:
        raise ValueError("max_network_transition_km must be finite and >0")
    for key in (
        "private_range_sector_geometry_opened_when_declared",
        "candidate_identity_used_to_set_constraint",
        "prospective_field_outcomes_opened",
        "field_outcomes_used_to_set_constraint",
        "survey_days_input",
        "monetary_budget_input",
        "user_site_count_input",
        "user_coverage_target_input",
        "post_geometry_edits_allowed",
        "post_outcome_edits_allowed",
    ):
        if value.get(key) is not False:
            raise ValueError(f"{key} must be false in the frozen movement constraint")
    return movement_km


def verify_movement_constraint_pin(
    protocol_path: Path = Path(CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH),
    *,
    repo_root: Path = ROOT,
    expected_pin_commit: str = "",
    must_be_ancestor_of: str = "",
) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    path = require_canonical_repo_path(
        Path(protocol_path),
        repo_root=repo,
        expected_repo_path=CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH,
        label="movement constraint protocol",
    )
    if not path.is_file():
        raise ValueError(f"missing movement constraint protocol: {path}")
    relative = path.relative_to(repo).as_posix()

    payload = path.read_bytes()
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("movement constraint protocol must be a JSON object")
    movement_km = _validate(value)

    try:
        _git(repo, "ls-files", "--error-unmatch", "--", relative)
    except subprocess.CalledProcessError as exc:
        raise ValueError("movement constraint protocol is not tracked by git") from exc
    if _git(repo, "status", "--porcelain", "--", relative).stdout.strip():
        raise ValueError("movement constraint protocol has uncommitted changes")

    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    head_payload = _git(repo, "show", f"HEAD:{relative}", text=False).stdout
    if head_payload != payload:
        raise ValueError("working movement constraint bytes do not equal HEAD")

    pin_commit = _first_add_commit(repo, relative)
    initial_payload = _git(repo, "show", f"{pin_commit}:{relative}", text=False).stdout
    if initial_payload != payload:
        raise ValueError("movement constraint bytes differ from the immutable first-add pin commit")
    if expected_pin_commit and pin_commit != str(expected_pin_commit).strip():
        raise ValueError("movement constraint pin commit does not match the expected immutable commit")
    try:
        _git(repo, "merge-base", "--is-ancestor", pin_commit, head)
    except subprocess.CalledProcessError as exc:
        raise ValueError("movement constraint pin commit is not an ancestor of HEAD") from exc
    if must_be_ancestor_of:
        try:
            _git(repo, "merge-base", "--is-ancestor", pin_commit, str(must_be_ancestor_of).strip())
        except subprocess.CalledProcessError as exc:
            raise ValueError("movement constraint was not pinned before the candidate/order prescription") from exc

    return {
        "schema_version": "cirsium-fresh-sentinel-movement-constraint-pin-verification-v1",
        "status": VERIFIED_STATUS,
        "protocol_repo_path": relative,
        "protocol_sha256": _sha256_bytes(payload),
        "pin_commit": pin_commit,
        "pin_rule": "first commit adding the canonical movement constraint; later byte changes are forbidden",
        "verified_head": head,
        "movement_constraint_mode": "osm_weighted_transport_network",
        "max_network_transition_km": movement_km,
        "movement_constraint_pin_gate_satisfied": True,
        "prospective_field_outcomes_opened": False,
        "private_candidate_geometry_opened_by_verifier": False,
        "authorization_scope": "pre-geometry operational constraint provenance only; no biological result or field-efficiency claim",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--protocol",
        type=Path,
        default=Path(CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH),
    )
    parser.add_argument("--expected-pin-commit", default="")
    parser.add_argument("--must-be-ancestor-of", default="")
    args = parser.parse_args()
    result = verify_movement_constraint_pin(
        args.protocol,
        expected_pin_commit=args.expected_pin_commit,
        must_be_ancestor_of=args.must_be_ancestor_of,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
