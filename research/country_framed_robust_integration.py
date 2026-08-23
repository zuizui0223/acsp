#!/usr/bin/env python3
"""Development-only integration of confirmed country framing and robust patches.

This module deliberately lives under ``research/``.  It connects two already
frozen components without changing either in place:

1. the independently confirmed focal-species historical-country outer frame;
2. the existing 2.5% / float32 / 1 km robust candidate-patch core.

Country membership is the *only* outer-frame selector.  Within-country search
geometry must come from an injected external land-geometry provider, never from
focal-species occurrence envelopes.  No ranking, SDM/SSDM, movement, route,
day, budget, or access quantity can enter candidate membership here.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Callable

import numpy as np
import pandas as pd
from shapely.geometry import Point
from shapely import wkt

from acsp.benchmarking import get_json
from acsp.taxon_patches import (
    GBIF_SEARCH,
    RAW_TERRAIN_FEATURES,
    ROBUST_TERRAIN_FEATURES,
    VALIDATED_MAX_PROTOTYPES,
    VALIDATED_OCCURRENCE_CAP,
    VALIDATED_SURFACE_POINTS,
    VALIDATED_SURFACE_SEED_BASE,
    _coordinate_columns,
    _prototype_coordinates,
    _with_robust_features,
    match_gbif_species,
)
from acsp.validated_robust import validated_robust_candidate_patches
from geographic_framing_country_registry_v3 import (
    HISTORICAL_YEARS,
    fetch_country_facet_counts,
)

REPRESENTATION_FREEZE_ID = "acsp_geographic_framing_country_registry_freeze_v1"
INTEGRATION_STATUS = "development_only_country_framed_robust_integration"
_COUNTRY_CODE = re.compile(r"^[A-Z]{2}$")
_COUNTRY_SURFACE_MAX_DRAW_FACTOR = 500


@dataclass(frozen=True)
class CountryLandGeometry:
    """Auditable external land geometry for one ISO-like country code.

    ``land_geometry_wkt`` must be supplied independently of focal-species
    occurrence geometry.  The integration adapter does not geocode countries,
    expand borders, or infer a polygon from the focal species.
    """

    country_code: str
    land_geometry_wkt: str
    source_id: str
    source_version: str

    def normalized_code(self) -> str:
        code = str(self.country_code).strip().upper()
        if not _COUNTRY_CODE.fullmatch(code):
            raise ValueError(f"invalid two-letter country code: {self.country_code!r}")
        return code


CountryGeometryProvider = Callable[[str], CountryLandGeometry]


def historical_country_codes_for_taxon(taxon_key: int) -> tuple[str, ...]:
    """Return the frozen historical focal-species country registry."""
    counts = fetch_country_facet_counts(int(taxon_key), HISTORICAL_YEARS)
    return tuple(sorted(str(code).upper() for code in counts))


def _stable_country_surface_seed(country_code: str) -> int:
    code = str(country_code).strip().upper()
    if not _COUNTRY_CODE.fullmatch(code):
        raise ValueError(f"invalid two-letter country code: {country_code!r}")
    offset = int(hashlib.sha1(code.encode("ascii")).hexdigest()[:8], 16)
    return int((VALIDATED_SURFACE_SEED_BASE + offset) % (2**31 - 1))


def _parse_land_geometry(spec: CountryLandGeometry):
    code = spec.normalized_code()
    if not str(spec.source_id).strip() or not str(spec.source_version).strip():
        raise ValueError(f"country geometry provenance is incomplete for {code}")
    geometry = wkt.loads(str(spec.land_geometry_wkt))
    if geometry.is_empty or not geometry.is_valid:
        raise ValueError(f"country land geometry is empty or invalid for {code}")
    if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError(f"country land geometry must be Polygon/MultiPolygon for {code}")
    return code, geometry


def sample_country_land_surface(
    spec: CountryLandGeometry,
    *,
    n_points: int = VALIDATED_SURFACE_POINTS,
) -> tuple[pd.DataFrame, int]:
    """Sample a deterministic outcome-blind point surface inside country land.

    The point universe comes from the external country polygon, not a focal
    occurrence envelope.  Rejection sampling is intentionally simple here;
    provider choice and surface mechanics remain part of the new integration
    method that still requires its own development/validation cycle.
    """
    code, geometry = _parse_land_geometry(spec)
    n_points = int(n_points)
    if n_points <= 0:
        raise ValueError("n_points must be positive")
    west, south, east, north = map(float, geometry.bounds)
    if not (-180.0 <= west < east <= 180.0 and -90.0 <= south < north <= 90.0):
        raise ValueError(f"country geometry has invalid WGS84-like bounds for {code}")

    seed = _stable_country_surface_seed(code)
    rng = np.random.default_rng(seed)
    rows: list[tuple[float, float]] = []
    max_draws = max(n_points * _COUNTRY_SURFACE_MAX_DRAW_FACTOR, 10_000)
    draws = 0
    while len(rows) < n_points and draws < max_draws:
        batch = min(max(256, (n_points - len(rows)) * 4), max_draws - draws)
        xs = rng.uniform(west, east, size=batch)
        ys = rng.uniform(south, north, size=batch)
        draws += batch
        for longitude, latitude in zip(xs, ys):
            if geometry.covers(Point(float(longitude), float(latitude))):
                rows.append((float(latitude), float(longitude)))
                if len(rows) == n_points:
                    break
    if len(rows) != n_points:
        raise ValueError(
            f"country geometry sampling produced {len(rows)}/{n_points} points for {code}; "
            "do not widen the frame or fall back to occurrence envelopes"
        )
    surface = pd.DataFrame(rows, columns=["latitude", "longitude"])
    surface["survey_area_id"] = f"country-{code}"
    return surface, seed


def fetch_country_occurrences(
    taxon_key: int,
    country_code: str,
    *,
    years: tuple[int, int] = HISTORICAL_YEARS,
    cap: int = VALIDATED_OCCURRENCE_CAP,
) -> pd.DataFrame:
    """Fetch historical training occurrences using the country code itself."""
    from gbif_fieldmap_builder_app import (
        clean_occurrences,
        detect_occurrence_columns,
        gbif_record_to_species_row,
    )

    code = str(country_code).strip().upper()
    if not _COUNTRY_CODE.fullmatch(code):
        raise ValueError(f"invalid two-letter country code: {country_code!r}")
    start, end = map(int, years)
    if start > end:
        raise ValueError("year range must be ascending")
    payload = get_json(
        GBIF_SEARCH,
        {
            "taxonKey": int(taxon_key),
            "country": code,
            "year": f"{start},{end}",
            "hasCoordinate": "true",
            "hasGeospatialIssue": "false",
            "occurrenceStatus": "PRESENT",
            "limit": min(300, int(cap)),
            "offset": 0,
        },
    )
    records = payload.get("results", [])
    raw = pd.DataFrame([gbif_record_to_species_row(record) for record in records])
    if raw.empty:
        raise ValueError(f"GBIF returned no usable historical occurrence rows in {code}")
    cleaned = clean_occurrences(raw, detect_occurrence_columns(raw)).copy().reset_index(drop=True)
    latitude_col, longitude_col = _coordinate_columns(cleaned)
    cleaned["latitude"] = pd.to_numeric(cleaned[latitude_col], errors="coerce")
    cleaned["longitude"] = pd.to_numeric(cleaned[longitude_col], errors="coerce")
    cleaned = cleaned.dropna(subset=["latitude", "longitude"]).drop_duplicates(
        ["latitude", "longitude"]
    ).reset_index(drop=True)
    if len(cleaned) < 5:
        raise ValueError(f"fewer than five usable historical occurrence rows in {code}: {len(cleaned)}")
    return cleaned


def country_terrain_inputs(
    occurrences: pd.DataFrame,
    geometry: CountryLandGeometry,
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Attach the frozen terrain feature representation to country inputs."""
    from gbif_fieldmap_builder_app import extract_environment

    code = geometry.normalized_code()
    surface, seed = sample_country_land_surface(geometry)
    surface = extract_environment(
        surface,
        list(RAW_TERRAIN_FEATURES),
        "latitude",
        "longitude",
        "2.5m",
    )
    surface = _with_robust_features(surface)
    surface = surface.loc[
        surface[list(ROBUST_TERRAIN_FEATURES)].notna().all(axis=1)
    ].copy().reset_index(drop=True)
    surface["survey_area_id"] = f"country-{code}"
    if surface.empty:
        raise ValueError(f"no complete terrain surface points for {code}")

    prototype_points = _prototype_coordinates(occurrences)
    prototypes = extract_environment(
        prototype_points,
        list(RAW_TERRAIN_FEATURES),
        "latitude",
        "longitude",
        "2.5m",
    )
    prototypes = _with_robust_features(prototypes)
    prototypes = prototypes.loc[
        prototypes[list(ROBUST_TERRAIN_FEATURES)].notna().all(axis=1)
    ].copy().drop_duplicates(list(ROBUST_TERRAIN_FEATURES)).reset_index(drop=True)
    if len(prototypes) < 5:
        raise ValueError(f"fewer than five unique complete training environment prototypes in {code}")
    return surface, prototypes, seed


def integrate_country_framed_robust_patches(
    taxon_name: str,
    geometry_provider: CountryGeometryProvider,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Run the frozen robust core inside the confirmed historical country set.

    This is a development-only integration object.  It is intentionally not
    exported from the production ``acsp`` package and must not be described as
    an independently validated global candidate-generation product.
    """
    match = match_gbif_species(taxon_name)
    taxon_key = int(match["taxon_key"])
    country_codes = historical_country_codes_for_taxon(taxon_key)
    if not country_codes:
        raise ValueError("frozen historical country registry is empty; no fallback is allowed")

    patch_frames: list[pd.DataFrame] = []
    country_status: list[dict[str, object]] = []
    for code in country_codes:
        area_id = f"country-{code}"
        try:
            spec = geometry_provider(code)
            if spec.normalized_code() != code:
                raise ValueError(
                    f"geometry provider returned {spec.normalized_code()} for requested country {code}"
                )
        except Exception as exc:
            country_status.append(
                {
                    "country_code": code,
                    "status": "skipped_geometry_provider_failure",
                    "candidate_patch_count": 0,
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            )
            continue

        try:
            occurrences = fetch_country_occurrences(taxon_key, code)
            surface, prototypes, surface_seed = country_terrain_inputs(occurrences, spec)
            patches, support_audit = validated_robust_candidate_patches(
                surface,
                prototypes,
                feature_columns=ROBUST_TERRAIN_FEATURES,
                area_col="survey_area_id",
            )
        except Exception as exc:
            country_status.append(
                {
                    "country_code": code,
                    "status": "skipped_insufficient_or_unavailable",
                    "candidate_patch_count": 0,
                    "geometry_source_id": str(spec.source_id),
                    "geometry_source_version": str(spec.source_version),
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            )
            continue

        patches = patches.copy()
        patches["framing_country_code"] = code
        patches["country_geometry_source_id"] = str(spec.source_id)
        patches["country_geometry_source_version"] = str(spec.source_version)
        patches["integration_status"] = INTEGRATION_STATUS
        patch_frames.append(patches)
        country_status.append(
            {
                "country_code": code,
                "status": "evaluated",
                "occurrence_rows": int(len(occurrences)),
                "surface_points": int(len(surface)),
                "surface_seed": int(surface_seed),
                "prototype_rows": int(len(prototypes)),
                "candidate_patch_count": int(len(patches)),
                "geometry_source_id": str(spec.source_id),
                "geometry_source_version": str(spec.source_version),
                "support_audit": support_audit.as_dict(),
            }
        )

    patches = pd.concat(patch_frames, ignore_index=True) if patch_frames else pd.DataFrame()
    audit: dict[str, object] = {
        "input_mode": INTEGRATION_STATUS,
        **match,
        "representation_freeze_id": REPRESENTATION_FREEZE_ID,
        "historical_year_range": list(HISTORICAL_YEARS),
        "declared_country_codes": list(country_codes),
        "declared_country_count": int(len(country_codes)),
        "evaluated_country_count": int(sum(row["status"] == "evaluated" for row in country_status)),
        "skipped_country_count": int(sum(row["status"] != "evaluated" for row in country_status)),
        "country_status": country_status,
        "feature_columns": list(ROBUST_TERRAIN_FEATURES),
        "surface_points_per_country": int(VALIDATED_SURFACE_POINTS),
        "candidate_patch_count": int(len(patches)),
        "country_membership_is_sole_outer_selector": True,
        "country_geometry_is_external_and_occurrence_independent": True,
        "local_occurrence_envelope_fallback": False,
        "country_expansion_or_higher_taxon_fallback": False,
        "ranking_or_topk_in_candidate_membership": False,
        "sdm_ssdm_in_candidate_membership": False,
        "movement_route_day_budget_in_candidate_membership": False,
        "validated_japan_adapter_changed": False,
        "independently_validated_integration": False,
        "development_only": True,
    }
    return patches, audit
