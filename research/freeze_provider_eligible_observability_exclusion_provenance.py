#!/usr/bin/env python3
"""Inventory byte provenance for already-consumed identity exclusions only.

This script is static and local-only. It must not call GBIF, geoBoundaries, or
any other network provider. It reads only identity/cohort files that were
already committed before issue #169 and emits their exact byte hashes and an
aggregate exclusion-set fingerprint for the new preregistration.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
BASE_PROTOCOL_PATH = ROOT / "validation" / "acsp_country_framed_fresh_heterogeneity_confirmation_v1.json"
TERMINAL_FRESH_PATH = ROOT / "validation" / "acsp_country_framed_fresh_heterogeneity_confirmation_identities_v1.csv"
EXPECTED_BASE_PROTOCOL_FINGERPRINT = "65ba06f174f4bdc9a49c24e54e8f7c67958757ab527fc23e4ccf427bf2d91a01"


def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("utf-8") + data).hexdigest()


def _canonical_sha256(payload: object) -> str:
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def exclusion_paths() -> list[str]:
    payload = json.loads(BASE_PROTOCOL_PATH.read_text(encoding="utf-8"))
    if payload.get("protocol_fingerprint") != EXPECTED_BASE_PROTOCOL_FINGERPRINT:
        raise ValueError("base fresh protocol fingerprint drifted")
    exclusions = payload.get("exclusions")
    if not isinstance(exclusions, dict):
        raise ValueError("base fresh exclusions block is malformed")
    paths = [
        str(exclusions["v4_96"]),
        str(exclusions["framing_confirmation"]),
        *[str(x) for x in exclusions["upstream"]],
        str(TERMINAL_FRESH_PATH.relative_to(ROOT)),
    ]
    if len(paths) != len(set(paths)):
        raise ValueError("duplicate exclusion path")
    return paths


def _identity_summary(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        lowered = {str(name).lower(): str(name) for name in fields}
        key_col = lowered.get("specieskey") or lowered.get("species_key")
        name_col = lowered.get("scientific_name") or lowered.get("scientificname")
        rows = 0
        keys: set[int] = set()
        names: set[str] = set()
        for row in reader:
            rows += 1
            if key_col and str(row.get(key_col, "")).strip():
                try:
                    keys.add(int(float(str(row[key_col]).strip())))
                except ValueError:
                    pass
            if name_col and str(row.get(name_col, "")).strip():
                names.add(str(row[name_col]).strip())
    return {
        "row_count": rows,
        "unique_species_keys": len(keys),
        "unique_scientific_names": len(names),
        "has_species_key_column": key_col is not None,
        "has_scientific_name_column": name_col is not None,
    }


def build_manifest() -> dict[str, object]:
    files: list[dict[str, object]] = []
    for relative in exclusion_paths():
        path = ROOT / relative
        if not path.is_file():
            raise FileNotFoundError(relative)
        data = path.read_bytes()
        files.append(
            {
                "path": relative,
                "byte_count": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "git_blob_sha": _git_blob_sha(data),
                **_identity_summary(path),
            }
        )
    payload: dict[str, object] = {
        "manifest_id": "acsp_provider_eligible_observability_exclusion_provenance_v1",
        "parent_issue": 169,
        "base_exclusion_protocol": str(BASE_PROTOCOL_PATH.relative_to(ROOT)),
        "base_exclusion_protocol_fingerprint": EXPECTED_BASE_PROTOCOL_FINGERPRINT,
        "terminal_fresh_identity_only": str(TERMINAL_FRESH_PATH.relative_to(ROOT)),
        "source_file_count": len(files),
        "files": files,
        "network_access": False,
        "fresh_candidate_identity_opened": False,
        "focal_species_historical_facet_opened": False,
        "heldout_2021_2025_opened": False,
        "aborted_163_partial_audit_replayed": False,
    }
    payload["exclusion_provenance_fingerprint"] = _canonical_sha256(payload)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    payload = build_manifest()
    rendered = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
