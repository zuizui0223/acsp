#!/usr/bin/env python3
"""Offline access to the frozen geoBoundaries v6 ADM0 coverage contract.

This module never fetches network data. It validates the byte-pinned coverage
registry and exposes provider eligibility for future independently
preregistered experiments. It does not alter the historical #163 protocol.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "validation" / "acsp_geoboundaries_v6_adm0_coverage_v1.json"
ISO_MAPPING_PATH = ROOT / "validation" / "iso3166_alpha2_to_alpha3_pycountry_24_6_1.json"
EXPECTED_CONTRACT_FINGERPRINT = "377f6374e077cc38ea7fc026de6dc289abc2716aca8c83d66ddcd42826139520"
EXPECTED_SUPPORTED_ALPHA3_SHA256 = "34fd29a5b64baa9517c6a9b7d1211aa021fe0662680b16ed8bebe2c728503dab"
EXPECTED_UNSUPPORTED_SHA256 = "faedebf7157faacacfa08516f3d4ce0db1b32887cc8aedafd8becdd21608552d"
EXPECTED_BLOB_MAP_SHA256 = "3b48693eae7d4b40d75e1671c0c9b99200cdc78d0bbb8b7da3632b4e6bbd20cb"


class ProviderCoverageError(ValueError):
    """Raised when a country code is outside the frozen geometry coverage."""


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256_json(payload: object) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_iso_mapping(path: Path = ISO_MAPPING_PATH) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mapping = payload.get("alpha2_to_alpha3")
    if payload.get("generated_with_pycountry") != "24.6.1":
        raise ValueError("ISO mapping generator version drifted")
    if payload.get("count") != 249 or not isinstance(mapping, dict) or len(mapping) != 249:
        raise ValueError("ISO mapping is incomplete")
    return {str(k).upper(): str(v).upper() for k, v in mapping.items()}


def validate_contract(payload: dict[str, Any], *, iso_path: Path = ISO_MAPPING_PATH) -> dict[str, Any]:
    if payload.get("contract_id") != "acsp_geoboundaries_v6_adm0_coverage_v1":
        raise ValueError("provider coverage contract id drifted")
    if payload.get("status") != "provider_coverage_frozen_before_any_new_observability_identity":
        raise ValueError("provider coverage contract is not frozen")
    if payload.get("parent_issue") != 167:
        raise ValueError("provider coverage parent issue drifted")

    expected_fingerprint = str(payload.get("coverage_contract_fingerprint", ""))
    fingerprint_payload = copy.deepcopy(payload)
    fingerprint_payload.pop("coverage_contract_fingerprint", None)
    actual_fingerprint = _sha256_json(fingerprint_payload)
    if expected_fingerprint != EXPECTED_CONTRACT_FINGERPRINT or actual_fingerprint != expected_fingerprint:
        raise ValueError("provider coverage contract fingerprint drifted")

    provider = payload.get("provider")
    if not isinstance(provider, dict):
        raise ValueError("provider coverage provider block is malformed")
    expected_provider = {
        "repository": "wmgeolab/geoBoundaries",
        "release_tag": "v6.0.0",
        "release_commit": "1289e40e366c7b320550be1ee0614a9472d572d4",
        "source_family": "gbOpen",
        "gbopen_tree_sha": "b322bddf7414625806dbe1bdb1632a4dcbe5eabe",
        "open_metadata_blob_sha": "37e379c344b79ee6a132d61dd105699ed76b4e57",
        "required_geometry_template": "{alpha3}/ADM0/geoBoundaries-{alpha3}-ADM0_simplified.geojson",
    }
    if provider != expected_provider:
        raise ValueError("provider provenance drifted")

    iso_block = payload.get("iso_mapping")
    if not isinstance(iso_block, dict):
        raise ValueError("provider coverage ISO block is malformed")
    if iso_block.get("path") != "validation/iso3166_alpha2_to_alpha3_pycountry_24_6_1.json":
        raise ValueError("provider coverage ISO path drifted")
    if iso_block.get("generated_with_pycountry") != "24.6.1" or iso_block.get("count") != 249:
        raise ValueError("provider coverage ISO provenance drifted")
    if iso_block.get("file_sha256") != _sha256_file(iso_path):
        raise ValueError("provider coverage ISO file hash drifted")

    coverage = payload.get("coverage")
    if not isinstance(coverage, dict):
        raise ValueError("provider coverage block is malformed")
    supported = list(coverage.get("supported_alpha3", []))
    unsupported = list(coverage.get("unsupported_iso_alpha2_alpha3", []))
    if supported != sorted(set(supported)) or len(supported) != 230:
        raise ValueError("supported provider alpha3 set drifted")
    if coverage.get("simplified_adm0_count") != len(supported):
        raise ValueError("simplified ADM0 count drifted")
    if coverage.get("provider_root_directory_count") != 231:
        raise ValueError("provider root directory count drifted")
    if coverage.get("metadata_adm0_count") != 228:
        raise ValueError("provider ADM0 metadata count drifted")
    if coverage.get("iso_mapping_alpha3_count") != 249:
        raise ValueError("provider coverage ISO count drifted")
    if _sha256_json(supported) != EXPECTED_SUPPORTED_ALPHA3_SHA256:
        raise ValueError("supported alpha3 digest drifted")
    if coverage.get("supported_alpha3_sha256") != EXPECTED_SUPPORTED_ALPHA3_SHA256:
        raise ValueError("stored supported alpha3 digest drifted")
    if _sha256_json(unsupported) != EXPECTED_UNSUPPORTED_SHA256:
        raise ValueError("unsupported ISO digest drifted")
    if coverage.get("unsupported_iso_alpha2_alpha3_sha256") != EXPECTED_UNSUPPORTED_SHA256:
        raise ValueError("stored unsupported ISO digest drifted")
    if coverage.get("simplified_adm0_blob_map_sha256") != EXPECTED_BLOB_MAP_SHA256:
        raise ValueError("simplified ADM0 blob-map digest drifted")

    mapping = load_iso_mapping(iso_path)
    supported_set = set(supported)
    expected_unsupported = [
        {"alpha2": alpha2, "alpha3": alpha3}
        for alpha2, alpha3 in sorted(mapping.items())
        if alpha3 not in supported_set
    ]
    if unsupported != expected_unsupported or len(unsupported) != 20:
        raise ValueError("unsupported ISO set is not the exact mapping-minus-provider complement")
    if coverage.get("provider_only_alpha3") != sorted(supported_set - set(mapping.values())):
        raise ValueError("provider-only alpha3 set drifted")
    if coverage.get("root_without_simplified_adm0") != ["PRI"]:
        raise ValueError("root-without-simplified set drifted")
    if coverage.get("metadata_adm0_without_simplified_geometry") != []:
        raise ValueError("metadata-without-geometry set drifted")
    if coverage.get("simplified_geometry_without_adm0_metadata") != ["LBN", "PER"]:
        raise ValueError("geometry-without-metadata set drifted")

    policy = payload.get("policy")
    if not isinstance(policy, dict):
        raise ValueError("provider coverage policy block is malformed")
    required_policy = {
        "provider_supported_definition": (
            "alpha3 has the exact simplified ADM0 blob path in the pinned gbOpen recursive tree"
        ),
        "metadata_row_required_for_geometry_support": False,
        "provider_root_directory_alone_counts_as_support": False,
        "unsupported_iso_codes_are_ineligible_before_any_future_fresh_identity_selection": True,
        "alternate_geometry_provider_fallback_allowed": False,
        "country_substitution_allowed": False,
        "taxon_replacement_after_unsupported_country_allowed": False,
        "parent_confirmation_163_may_be_resumed": False,
    }
    if policy != required_policy:
        raise ValueError("provider coverage policy drifted")

    provenance = payload.get("development_provenance")
    if not isinstance(provenance, dict):
        raise ValueError("provider coverage development provenance is malformed")
    for key in (
        "fresh_taxon_identities_opened",
        "historical_focal_species_facets_opened",
        "heldout_2021_2025_opened",
    ):
        if provenance.get(key) is not False:
            raise ValueError(f"forbidden development input was opened: {key}")
    return payload


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("provider coverage contract must be a JSON object")
    return validate_contract(payload)


def supported_alpha3(path: Path = CONTRACT_PATH) -> frozenset[str]:
    return frozenset(load_contract(path)["coverage"]["supported_alpha3"])


def alpha2_to_alpha3_if_supported(alpha2: str, *, path: Path = CONTRACT_PATH) -> str | None:
    code = str(alpha2).strip().upper()
    mapping = load_iso_mapping()
    alpha3 = mapping.get(code)
    if alpha3 is None:
        return None
    return alpha3 if alpha3 in supported_alpha3(path) else None


def require_supported_alpha2(alpha2: str, *, path: Path = CONTRACT_PATH) -> str:
    code = str(alpha2).strip().upper()
    mapping = load_iso_mapping()
    if code not in mapping:
        raise ProviderCoverageError(f"unknown frozen ISO alpha-2 code: {code}")
    alpha3 = mapping[code]
    if alpha3 not in supported_alpha3(path):
        raise ProviderCoverageError(
            f"country {code}/{alpha3} is outside frozen geoBoundaries v6 ADM0 coverage"
        )
    return alpha3
