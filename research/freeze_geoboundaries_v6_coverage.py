#!/usr/bin/env python3
"""Freeze the country-code coverage of the pinned geoBoundaries v6 provider.

This is infrastructure-only development for issue #167. It inspects only the
commit-pinned geoBoundaries repository tree/metadata and the already-frozen ISO
alpha-2 -> alpha-3 mapping. It must not inspect taxa, GBIF species facets,
historical focal-species declarations, or heldout outcomes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
ISO_MAPPING_PATH = ROOT / "validation" / "iso3166_alpha2_to_alpha3_pycountry_24_6_1.json"

CONTRACT_ID = "acsp_geoboundaries_v6_adm0_coverage_v1"
PARENT_ISSUE = 167
GEOBOUNDARIES_RELEASE_TAG = "v6.0.0"
GEOBOUNDARIES_RELEASE_COMMIT = "1289e40e366c7b320550be1ee0614a9472d572d4"
GBOPEN_TREE_SHA = "b322bddf7414625806dbe1bdb1632a4dcbe5eabe"
OPEN_METADATA_BLOB_SHA = "37e379c344b79ee6a132d61dd105699ed76b4e57"
SOURCE_FAMILY = "gbOpen"
TREE_URL = (
    "https://api.github.com/repos/wmgeolab/geoBoundaries/git/trees/"
    f"{GBOPEN_TREE_SHA}?recursive=1"
)
METADATA_URL = (
    "https://raw.githubusercontent.com/wmgeolab/geoBoundaries/"
    f"{GEOBOUNDARIES_RELEASE_COMMIT}/releaseData/geoBoundariesOpen-meta.csv"
)
SIMPLIFIED_RE = re.compile(
    r"^(?P<iso3>[A-Z]{3})/ADM0/geoBoundaries-(?P=iso3)-ADM0_simplified\\.geojson$"
)
ISO3_RE = re.compile(r"^[A-Z]{3}$")


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _get_bytes(url: str, timeout: int = 120) -> bytes:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "acsp-provider-coverage-freezer",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_json(url: str) -> dict[str, Any]:
    payload = json.loads(_get_bytes(url).decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object from {url}")
    return payload


def fetch_text(url: str) -> str:
    return _get_bytes(url).decode("utf-8")


def load_iso_mapping(path: Path = ISO_MAPPING_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mapping = payload.get("alpha2_to_alpha3")
    if payload.get("generated_with_pycountry") != "24.6.1":
        raise ValueError("unexpected frozen ISO mapping generator version")
    if payload.get("count") != 249 or not isinstance(mapping, dict) or len(mapping) != 249:
        raise ValueError("frozen ISO mapping is incomplete")
    normalized = {str(k).upper(): str(v).upper() for k, v in mapping.items()}
    if any(len(k) != 2 or not ISO3_RE.fullmatch(v) for k, v in normalized.items()):
        raise ValueError("frozen ISO mapping contains malformed codes")
    return {
        "generated_with_pycountry": "24.6.1",
        "count": 249,
        "alpha2_to_alpha3": dict(sorted(normalized.items())),
        "file_sha256": _sha256_bytes(path.read_bytes()),
    }


def parse_recursive_tree(payload: dict[str, Any]) -> tuple[set[str], dict[str, str]]:
    if payload.get("sha") != GBOPEN_TREE_SHA:
        raise ValueError("unexpected geoBoundaries gbOpen tree SHA")
    if payload.get("truncated") is True:
        raise ValueError("recursive geoBoundaries tree response was truncated")
    entries = payload.get("tree")
    if not isinstance(entries, list):
        raise ValueError("geoBoundaries recursive tree is malformed")

    root_dirs: set[str] = set()
    simplified_blobs: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("geoBoundaries recursive tree contains malformed entry")
        path = str(entry.get("path", ""))
        if entry.get("type") == "tree" and "/" not in path and ISO3_RE.fullmatch(path):
            root_dirs.add(path)
        match = SIMPLIFIED_RE.fullmatch(path)
        if match is None:
            continue
        if entry.get("type") != "blob":
            raise ValueError(f"simplified ADM0 path is not a blob: {path}")
        iso3 = match.group("iso3")
        blob_sha = str(entry.get("sha", ""))
        if not re.fullmatch(r"[0-9a-f]{40}", blob_sha):
            raise ValueError(f"malformed simplified ADM0 blob SHA: {path}")
        if iso3 in simplified_blobs:
            raise ValueError(f"duplicate simplified ADM0 geometry for {iso3}")
        simplified_blobs[iso3] = blob_sha
    return root_dirs, dict(sorted(simplified_blobs.items()))


def parse_open_metadata(text: str) -> dict[str, dict[str, str]]:
    reader = csv.DictReader(text.splitlines())
    required = {"boundaryID", "boundaryISO", "boundaryType", "staticDownloadLink"}
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise ValueError("geoBoundaries open metadata columns drifted")
    rows: dict[str, dict[str, str]] = {}
    for row in reader:
        if str(row.get("boundaryType", "")).strip().upper() != "ADM0":
            continue
        iso3 = str(row.get("boundaryISO", "")).strip().upper()
        if not ISO3_RE.fullmatch(iso3):
            raise ValueError(f"malformed ADM0 boundaryISO: {iso3!r}")
        if iso3 in rows:
            raise ValueError(f"duplicate ADM0 metadata row for {iso3}")
        rows[iso3] = {
            "boundary_id": str(row.get("boundaryID", "")).strip(),
            "static_download_link": str(row.get("staticDownloadLink", "")).strip(),
        }
    return dict(sorted(rows.items()))


def build_coverage_contract(
    *,
    tree_payload: dict[str, Any],
    metadata_text: str,
    iso_payload: dict[str, Any],
) -> dict[str, Any]:
    root_dirs, simplified_blobs = parse_recursive_tree(tree_payload)
    metadata = parse_open_metadata(metadata_text)
    mapping = dict(iso_payload["alpha2_to_alpha3"])

    simplified = set(simplified_blobs)
    metadata_codes = set(metadata)
    iso_codes = set(mapping.values())

    unsupported_iso = [
        {"alpha2": alpha2, "alpha3": alpha3}
        for alpha2, alpha3 in sorted(mapping.items())
        if alpha3 not in simplified
    ]
    provider_only = sorted(simplified - iso_codes)
    root_without_simplified = sorted(root_dirs - simplified)
    simplified_without_root = sorted(simplified - root_dirs)
    metadata_without_simplified = sorted(metadata_codes - simplified)
    simplified_without_metadata = sorted(simplified - metadata_codes)

    payload: dict[str, Any] = {
        "contract_id": CONTRACT_ID,
        "status": "provider_coverage_development_before_any_new_observability_identity",
        "parent_issue": PARENT_ISSUE,
        "provider": {
            "repository": "wmgeolab/geoBoundaries",
            "release_tag": GEOBOUNDARIES_RELEASE_TAG,
            "release_commit": GEOBOUNDARIES_RELEASE_COMMIT,
            "source_family": SOURCE_FAMILY,
            "gbopen_tree_sha": GBOPEN_TREE_SHA,
            "open_metadata_blob_sha": OPEN_METADATA_BLOB_SHA,
            "recursive_tree_url": TREE_URL,
            "metadata_url": METADATA_URL,
            "required_geometry_template": (
                "{alpha3}/ADM0/geoBoundaries-{alpha3}-ADM0_simplified.geojson"
            ),
        },
        "iso_mapping": {
            "path": str(ISO_MAPPING_PATH.relative_to(ROOT)),
            "generated_with_pycountry": iso_payload["generated_with_pycountry"],
            "count": int(iso_payload["count"]),
            "file_sha256": str(iso_payload["file_sha256"]),
        },
        "coverage": {
            "provider_root_directory_count": len(root_dirs),
            "simplified_adm0_count": len(simplified),
            "metadata_adm0_count": len(metadata_codes),
            "iso_mapping_alpha3_count": len(iso_codes),
            "supported_alpha3": sorted(simplified),
            "unsupported_iso_alpha2_alpha3": unsupported_iso,
            "provider_only_alpha3": provider_only,
            "root_without_simplified_adm0": root_without_simplified,
            "simplified_adm0_without_root_directory": simplified_without_root,
            "metadata_adm0_without_simplified_geometry": metadata_without_simplified,
            "simplified_geometry_without_adm0_metadata": simplified_without_metadata,
            "simplified_adm0_blob_sha_by_alpha3": simplified_blobs,
        },
        "future_experiment_boundary": {
            "provider_eligibility_must_be_fixed_before_fresh_identity_selection": True,
            "provider_eligibility_must_be_fixed_before_historical_species_facets": True,
            "provider_eligibility_must_be_fixed_before_heldout_outcomes": True,
            "unsupported_code_may_not_be_replaced_after_identity_selection": True,
            "alternate_geometry_provider_fallback_allowed": False,
            "parent_confirmation_163_may_be_resumed": False,
        },
        "development_inputs": {
            "fresh_taxon_identities_opened": False,
            "historical_focal_species_facets_opened": False,
            "heldout_2021_2025_opened": False,
            "candidate_or_recall_outcomes_opened": False,
        },
    }
    payload["coverage_fingerprint"] = _sha256_bytes(_canonical_bytes(payload))
    return payload


def freeze_coverage(
    *,
    tree_fetcher: Callable[[str], dict[str, Any]] = fetch_json,
    metadata_fetcher: Callable[[str], str] = fetch_text,
    iso_path: Path = ISO_MAPPING_PATH,
) -> dict[str, Any]:
    return build_coverage_contract(
        tree_payload=tree_fetcher(TREE_URL),
        metadata_text=metadata_fetcher(METADATA_URL),
        iso_payload=load_iso_mapping(iso_path),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    payload = freeze_coverage()
    rendered = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
