#!/usr/bin/env python3
"""Run private fresh-SENTINEL freezing and emit one commit-ready public hash receipt.

This command is the operational entry point after the frozen private four-feature
range-sector GeoJSON exists. It runs the outcome-blind private pre-field pipeline,
then exports the coordinate-free public hash receipt into validation/. It never
commits the receipt and therefore never authorizes prospective outcome opening by
itself. A separate pin verifier must pass on a committed checkout first.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from research.export_cirsium_fresh_sentinel_public_freeze_receipt_v1 import build_public_freeze_receipt
from research.orchestrate_cirsium_fresh_sentinel_pre_field_v1 import run_private_pre_field_pipeline

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT_STATUS = "PRIVATE_AND_PUBLIC_HASH_FREEZE_GENERATED_AWAITING_COMMIT"


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _public_path(path: Path, *, repo_root: Path) -> Path:
    value = path if path.is_absolute() else repo_root / path
    value = value.resolve()
    if not _inside(value, repo_root):
        raise ValueError("public freeze receipt must be written inside the repository")
    relative = value.relative_to(repo_root.resolve())
    if not relative.parts or relative.parts[0] != "validation":
        raise ValueError("public freeze receipt must be written under validation/")
    if value.exists():
        raise ValueError("refusing to overwrite an existing public freeze receipt")
    return value


def run_full_pre_field_freeze(
    bundle_geojson: Path,
    private_root: Path,
    public_receipt: Path,
    *,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    bundle = Path(bundle_geojson).resolve()
    private = Path(private_root).resolve()
    repo = Path(repo_root).resolve()
    public = _public_path(Path(public_receipt), repo_root=repo)

    if not bundle.is_file():
        raise ValueError(f"missing private range-sector bundle: {bundle}")
    if _inside(bundle, repo):
        raise ValueError("private range-sector bundle must remain outside the public repository")
    if _inside(private, repo):
        raise ValueError("private output root must remain outside the public repository")
    if private.exists():
        raise ValueError("private output root must not already exist")

    private_receipt = run_private_pre_field_pipeline(bundle, private)
    if private_receipt.get("ready_for_future_prospective_outcome_opening") is not False:
        raise ValueError("private freeze unexpectedly authorizes outcome opening")
    if private_receipt.get("ready_for_public_hash_receipt_freeze") is not True:
        raise ValueError("private freeze did not reach the public hash receipt gate")

    receipt = build_public_freeze_receipt(private)
    if receipt.get("outcome_opening_authorized_by_generation_alone") is not False:
        raise ValueError("public receipt generation must not authorize outcome opening")
    if receipt.get("public_receipt_commit_required_before_outcome_opening") is not True:
        raise ValueError("public receipt must require commit/pin before outcome opening")

    public.parent.mkdir(parents=True, exist_ok=True)
    public.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    relative_public = public.relative_to(repo).as_posix()
    return {
        "schema_version": "cirsium-fresh-sentinel-freeze-entry-v1",
        "status": ENTRYPOINT_STATUS,
        "private_freeze_status": str(private_receipt.get("status") or ""),
        "public_receipt_status": str(receipt.get("status") or ""),
        "public_receipt_repo_path": relative_public,
        "field_outcomes_opened": False,
        "outcome_opening_authorized": False,
        "next_gate": "Commit the public receipt, then pass verify_cirsium_fresh_sentinel_public_freeze_pin_v1.py on that committed checkout.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-geojson", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--public-receipt", type=Path, required=True)
    args = parser.parse_args()
    result = run_full_pre_field_freeze(args.bundle_geojson, args.private_root, args.public_receipt)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
