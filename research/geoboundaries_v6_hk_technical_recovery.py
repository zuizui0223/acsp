#!/usr/bin/env python3
"""Technical geoBoundaries recovery for the issue #163 HK freeze abort.

The scientific selected country remains HK.  The direct HKG/ADM0 object is
absent from the frozen geoBoundaries v6.0.0 gbOpen release, so this adapter
extracts the single ``Hong Kong`` ADM1 feature carried inside CHN/ADM1 in the
same pinned release.  No alternate provider, country substitution, taxon
replacement, geometry repair, or held-out data access is permitted.
"""
from __future__ import annotations

from typing import Any

from acsp.benchmarking import get_json
from country_framed_robust_integration import CountryLandGeometry
import geoboundaries_v6_provider as base

HK_COUNTRY_CODE = "HK"
HK_ISO3 = "HKG"
HK_PARENT_ISO3 = "CHN"
HK_SHAPE_NAME = "Hong Kong"
HK_SHAPE_GROUP = "CHN"
HK_SHAPE_TYPE = "ADM1"
HK_RECOVERY_SOURCE_ID = "geoBoundaries-gbOpen-CHN-ADM1-Hong-Kong-extract"
HK_CHN_ADM1_URL = (
    "https://media.githubusercontent.com/media/wmgeolab/geoBoundaries/"
    f"{base.GEOBOUNDARIES_RELEASE_COMMIT}/releaseData/gbOpen/CHN/ADM1/"
    "geoBoundaries-CHN-ADM1_simplified.geojson"
)


def _hong_kong_feature(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("type") != "FeatureCollection":
        raise ValueError("pinned CHN/ADM1 payload is not a FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("pinned CHN/ADM1 payload contains no features")
    matches: list[dict[str, Any]] = []
    for feature in features:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            continue
        properties = feature.get("properties") or {}
        if str(properties.get("shapeName") or "").strip() == HK_SHAPE_NAME:
            matches.append(feature)
    if len(matches) != 1:
        raise ValueError(
            f"pinned CHN/ADM1 must contain exactly one {HK_SHAPE_NAME!r} feature; got {len(matches)}"
        )
    feature = matches[0]
    properties = feature.get("properties") or {}
    if str(properties.get("shapeGroup") or "").strip().upper() != HK_SHAPE_GROUP:
        raise ValueError("Hong Kong recovery feature shapeGroup drift")
    if str(properties.get("shapeType") or "").strip().upper() != HK_SHAPE_TYPE:
        raise ValueError("Hong Kong recovery feature shapeType drift")
    return feature


def fetch_hk_geometry_from_pinned_china_adm1() -> CountryLandGeometry:
    """Return the frozen Hong Kong geometry without changing country identity."""
    payload = get_json(HK_CHN_ADM1_URL, timeout=120, attempts=5)
    feature = _hong_kong_feature(payload)
    properties = feature.get("properties") or {}
    subset = {"type": "FeatureCollection", "features": [feature]}
    digest = base._canonical_payload_sha256(subset)
    geometry = base._polygonal_union(subset, HK_COUNTRY_CODE)
    shape_id = str(properties.get("shapeID") or "").strip()
    version = (
        f"{base.GEOBOUNDARIES_RELEASE_TAG}@{base.GEOBOUNDARIES_RELEASE_COMMIT};"
        f"iso3={HK_ISO3};container_iso3={HK_PARENT_ISO3};container_adm=ADM1;"
        f"shapeName={HK_SHAPE_NAME};shapeID={shape_id};"
        f"canonical_geojson_sha256={digest};license={base.GEOBOUNDARIES_LICENSE}"
    )
    return CountryLandGeometry(
        country_code=HK_COUNTRY_CODE,
        land_geometry_wkt=geometry.wkt,
        source_id=HK_RECOVERY_SOURCE_ID,
        source_version=version,
    )


def fetch_country_geometry_with_hk_recovery(country_code: str) -> CountryLandGeometry:
    """Use the frozen ADM0 provider except for the bound HK technical recovery."""
    code = str(country_code).strip().upper()
    if code == HK_COUNTRY_CODE:
        return fetch_hk_geometry_from_pinned_china_adm1()
    return base.fetch_geoboundaries_country_geometry(code)


__all__ = [
    "HK_CHN_ADM1_URL",
    "HK_COUNTRY_CODE",
    "HK_ISO3",
    "HK_PARENT_ISO3",
    "HK_RECOVERY_SOURCE_ID",
    "HK_SHAPE_GROUP",
    "HK_SHAPE_NAME",
    "HK_SHAPE_TYPE",
    "fetch_country_geometry_with_hk_recovery",
    "fetch_hk_geometry_from_pinned_china_adm1",
]
