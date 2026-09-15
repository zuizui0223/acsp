#!/usr/bin/env python3
"""Verify that the exact public fresh-SENTINEL hash receipt is committed and immutable.

Receipt generation is intentionally insufficient. This verifier is the only
repository-side transition that may report the public pre-outcome provenance gate
as satisfied. It requires a tracked, clean receipt whose bytes equal HEAD and,
critically, whose current bytes still equal the bytes in the *first commit that
added the receipt*. A later commit therefore cannot silently re-pin a modified
receipt after outcomes are known.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_STATUS = "PUBLIC_HASH_FREEZE_READY_FOR_COMMIT"
VERIFIED_STATUS = "PUBLIC_HASH_FREEZE_COMMITTED_AND_PINNED"


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


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


def _validate_receipt(value: dict[str, Any]) -> None:
    if value.get("status") != EXPECTED_STATUS:
        raise ValueError("public receipt is not in the commit-ready frozen state")
    if value.get("coordinate_bearing_data_included") is not False:
        raise ValueError("public receipt cannot include coordinate-bearing data")
    if value.get("private_paths_included") is not False:
        raise ValueError("public receipt cannot include private paths")
    if value.get("prospective_field_outcomes_opened") is not False:
        raise ValueError("public receipt cannot declare opened prospective outcomes")
    if value.get("field_outcomes_used_to_choose_or_rank") is not False:
        raise ValueError("public receipt cannot use field outcomes to choose or rank")
    if value.get("outcome_opening_authorized_by_generation_alone") is not False:
        raise ValueError("receipt generation alone must not authorize outcome opening")
    if value.get("public_receipt_commit_required_before_outcome_opening") is not True:
        raise ValueError("receipt must require commit/pin before outcome opening")
    if value.get("public_receipt_commit_verified") is not False:
        raise ValueError("receipt bytes must not self-assert that their own commit was verified")


def _first_add_commit(repo: Path, relative: str) -> str:
    commits = [
        line.strip()
        for line in _git(repo, "log", "--diff-filter=A", "--format=%H", "--", relative).stdout.splitlines()
        if line.strip()
    ]
    if not commits:
        raise ValueError("could not identify the first commit that added the public receipt")
    return commits[-1]


def verify_public_freeze_pin(
    receipt_path: Path,
    *,
    repo_root: Path = ROOT,
    expected_pin_commit: str = "",
) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    path = Path(receipt_path)
    path = (repo / path).resolve() if not path.is_absolute() else path.resolve()
    if not _inside(path, repo):
        raise ValueError("public receipt must be inside the repository")
    if not path.is_file():
        raise ValueError(f"missing public receipt: {path}")
    relative = path.relative_to(repo).as_posix()
    if not relative.startswith("validation/"):
        raise ValueError("public receipt must be under validation/")

    payload = path.read_bytes()
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("public receipt must be a JSON object")
    _validate_receipt(value)

    try:
        _git(repo, "ls-files", "--error-unmatch", "--", relative)
    except subprocess.CalledProcessError as exc:
        raise ValueError("public receipt is not tracked by git") from exc
    status = _git(repo, "status", "--porcelain", "--", relative).stdout.strip()
    if status:
        raise ValueError("public receipt has uncommitted changes")

    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    head_payload = _git(repo, "show", f"HEAD:{relative}", text=False).stdout
    if head_payload != payload:
        raise ValueError("working public receipt bytes do not equal the receipt stored at HEAD")

    pin_commit = _first_add_commit(repo, relative)
    initial_payload = _git(repo, "show", f"{pin_commit}:{relative}", text=False).stdout
    if initial_payload != payload:
        raise ValueError("public receipt bytes differ from the immutable first-add pin commit")
    if expected_pin_commit and pin_commit != str(expected_pin_commit).strip():
        raise ValueError("public receipt pin commit does not match the expected immutable commit")
    try:
        _git(repo, "merge-base", "--is-ancestor", pin_commit, head)
    except subprocess.CalledProcessError as exc:
        raise ValueError("public receipt pin commit is not an ancestor of HEAD") from exc

    return {
        "schema_version": "cirsium-fresh-sentinel-public-freeze-pin-verification-v1",
        "status": VERIFIED_STATUS,
        "receipt_repo_path": relative,
        "receipt_sha256": _sha256_bytes(payload),
        "pin_commit": pin_commit,
        "pin_rule": "first commit adding the receipt; later byte changes are forbidden",
        "verified_head": head,
        "public_receipt_commit_verified": True,
        "prospective_field_outcomes_opened": False,
        "outcome_opening_gate_satisfied": True,
        "authorization_scope": "provenance gate only; does not assert biological success or field efficiency",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--expected-pin-commit", default="")
    args = parser.parse_args()
    result = verify_public_freeze_pin(args.receipt, expected_pin_commit=args.expected_pin_commit)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
