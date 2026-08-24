#!/usr/bin/env python3
"""Frozen geoBoundaries v6.0.0 ADM0 provider for integration development.

This provider is intentionally research-only. It converts the confirmed GBIF
country facet code (ISO-3166 alpha-2) to the geoBoundaries gbOpen alpha-3 path
using a committed static mapping, fetches a commit-pinned simplified ADM0
GeoJSON, unions all polygonal features, and returns the external country land
geometry required by ``country_framed_robust_integration``.

No live geocoder, neighbour-country expansion, alternate boundary provider,
bounding-box fallback, or focal-occurrence envelope fallback is permitted.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from shapely.geometry import shape
from shapely.ops import unary_union

from acsp.benchmarking import get_json
from country_framed_robust_integration import CountryLandGeometry

GEOBOUNDARIES_RELEASE_TAG = "v6.0.0"
GEOBOUNDARIES_RELEASE_COMMIT = "1289e40e366c7b320550be1ee0614a9472d572d4"
GEOBOUNDARIES_LICENSE = "CC BY 4.0"
GEOBOUNDARIES_LICENSE_BLOB_SHA = "82e5f0190c068568b975ebb42d77f7f25e4d09ef"
GEOBOUNDARIES_SOURCE_ID = "geoBoundaries-gbOpen-ADM0-simplified"
ISO_MAPPING_PATH = (
    Path(__file__).resolve().parents[1]
    / "validation"
    / "iso3166_alpha2_to_alpha3_pycountry_24_6_1.json"
)
URL_TEMPLATE = (
    "https://media.githubusercontent.com/media/wmgeolab/geoBoundaries/"
    f"{GEOBOUNDARIES_RELEASE_COMMIT}/releaseData/gbOpen/{{iso3}}/ADM0/"
    "geoBoundaries-{iso3}-ADM0_simplified.geojson"
)


def load_iso_alpha2_to_alpha3(path: Path = ISO_MAPPING_PATH) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mapping = payload.get("alpha2_to_alpha3")
    if payload.get("generated_with_pycountry") != "24.6.1":
        raise ValueError("unexpected frozen ISO mapping generator version")
    if payload.get("count") != 249 or not isinstance(mapping, dict) or len(mapping) != 249:
        raise ValueError("frozen ISO mapping is incomplete")
    normalized = {str(k).upper(): str(v).upper() for k, v in mapping.items()}
    if any(len(k) != 2 or len(v) != 3 for k, v in normalized.items()):
        raise ValueError("frozen ISO mapping contains malformed codes")
    return normalized


def alpha3_for_country(country_code: str) -> str:
    code = str(country_code).strip().upper()
    if len(code) != 2:
        raise ValueError(f"invalid two-letter country code: {country_code!r}")
    mapping = load_iso_alpha2_to_alpha3()
    try:
        return mapping[code]
    except KeyError as exc:
        raise ValueError(
            f"country code {code!r} is absent from the frozen ISO mapping; no fallback is allowed"
        ) from exc


def geoboundaries_url(country_code: str) -> tuple[str, str]:
    iso3 = alpha3_for_country(country_code)
    return iso3, URL_TEMPLATE.format(iso3=iso3)


def _canonical_payload_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _polygonal_union(payload: dict[str, Any], country_code: str):
    if payload.get("type") != "FeatureCollection":
        raise ValueError(f"geoBoundaries payload for {country_code} is not a FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError(f"geoBoundaries payload for {country_code} contains no features")

    geometries = []
    for feature in features:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError(f"geoBoundaries payload for {country_code} contains malformed features")
        geometry_payload = feature.get("geometry")
        if not geometry_payload:
            raise ValueError(f"geoBoundaries payload for {country_code} contains a missing geometry")
        geometry = shape(geometry_payload)
        if geometry.is_empty or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            raise ValueError(
                f"geoBoundaries payload for {country_code} contains non-polygonal geometry"
            )
        if not geometry.is_valid:
            raise ValueError(
                f"geoBoundaries payload for {country_code} contains invalid geometry; no repair fallback is allowed"
            )
        geometries.append(geometry)

    merged = unary_union(geometries)
    if merged.is_empty or merged.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError(f"geoBoundaries union for {country_code} is not polygonal")
    if not merged.is_valid:
        raise ValueError(
            f"geoBoundaries union for {country_code} is invalid; no repair fallback is allowed"
        )
    return merged


def fetch_geoboundaries_country_geometry(country_code: str) -> CountryLandGeometry:
    """Fetch one commit-pinned gbOpen ADM0 geometry with explicit provenance."""
    code = str(country_code).strip().upper()
    iso3, url = geoboundaries_url(code)
    payload = get_json(url, timeout=120, attempts=5)
    digest = _canonical_payload_sha256(payload)
    geometry = _polygonal_union(payload, code)
    version = (
        f"{GEOBOUNDARIES_RELEASE_TAG}@{GEOBOUNDARIES_RELEASE_COMMIT};"
        f"iso3={iso3};canonical_geojson_sha256={digest};license={GEOBOUNDARIES_LICENSE}"
    )
    return CountryLandGeometry(
        country_code=code,
        land_geometry_wkt=geometry.wkt,
        source_id=GEOBOUNDARIES_SOURCE_ID,
        source_version=version,
    )


__all__ = [
    "GEOBOUNDARIES_RELEASE_TAG",
    "GEOBOUNDARIES_RELEASE_COMMIT",
    "GEOBOUNDARIES_LICENSE",
    "GEOBOUNDARIES_LICENSE_BLOB_SHA",
    "GEOBOUNDARIES_SOURCE_ID",
    "ISO_MAPPING_PATH",
    "URL_TEMPLATE",
    "alpha3_for_country",
    "fetch_geoboundaries_country_geometry",
    "geoboundaries_url",
    "load_iso_alpha2_to_alpha3",
]
