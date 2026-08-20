"""Thin species-name adapter for the validated ACSP candidate-patch product.

This module reproduces the input-generation conventions used by the untouched
cross-taxon confirmation: GBIF occurrence retrieval inside a declared rectangle,
deterministic spatial thinning to at most 32 occurrence prototypes, one fixed
800-point land surface for the rectangle, the confirmed terrain feature set,
and the validated 2.5% robust-support candidate-patch rule.

It adds no route, budget, day, movement-mode, top-k, or threshold optimization.
"""
from __future__ import annotations

import hashlib
from typing import Any

import numpy as np
import pandas as pd

from .benchmarking import get_json
from .validated_robust import validated_robust_candidate_patches

GBIF_MATCH = "https://api.gbif.org/v1/species/match"
GBIF_SEARCH = "https://api.gbif.org/v1/occurrence/search"
RAW_TERRAIN_FEATURES = ("elevation", "slope", "aspect", "roughness", "tpi")
ROBUST_TERRAIN_FEATURES = (
    "elevation",
    "slope",
    "aspect_sin",
    "aspect_cos",
    "roughness",
    "tpi",
)
VALIDATED_SURFACE_POINTS = 800
VALIDATED_OCCURRENCE_CAP = 150
VALIDATED_MAX_PROTOTYPES = 32
VALIDATED_SURFACE_SEED_BASE = 20260823


def _validate_bounds(bounds: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    west, south, east, north = (float(value) for value in bounds)
    if not (-180.0 <= west < east <= 180.0):
        raise ValueError("extent must satisfy -180 <= west < east <= 180")
    if not (-90.0 <= south < north <= 90.0):
        raise ValueError("extent must satisfy -90 <= south < north <= 90")
    return west, south, east, north


def _rectangle_wkt(bounds: tuple[float, float, float, float]) -> str:
    west, south, east, north = _validate_bounds(bounds)
    return f"POLYGON(({west} {south},{east} {south},{east} {north},{west} {north},{west} {south}))"


def _stable_surface_seed(bounds: tuple[float, float, float, float]) -> int:
    token = ",".join(f"{value:.6f}" for value in _validate_bounds(bounds))
    offset = int(hashlib.sha1(token.encode("utf-8")).hexdigest()[:8], 16)
    return int((VALIDATED_SURFACE_SEED_BASE + offset) % (2**31 - 1))


def _coordinate_columns(frame: pd.DataFrame) -> tuple[str, str]:
    for latitude, longitude in (
        ("latitude", "longitude"),
        ("_latitude", "_longitude"),
        ("decimalLatitude", "decimalLongitude"),
        ("lat", "lon"),
    ):
        if latitude in frame.columns and longitude in frame.columns:
            return latitude, longitude
    raise ValueError("occurrence rows do not contain recognizable coordinates")


def _with_robust_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for column in RAW_TERRAIN_FEATURES:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    radians = np.radians(out["aspect"].to_numpy(float))
    out["aspect_sin"] = np.sin(radians)
    out["aspect_cos"] = np.cos(radians)
    return out


def match_gbif_species(taxon_name: str) -> dict[str, Any]:
    """Resolve one scientific species name through the GBIF backbone."""
    name = str(taxon_name).strip()
    if not name:
        raise ValueError("taxon name must not be empty")
    payload = get_json(GBIF_MATCH, {"name": name, "verbose": "true"}, timeout=30)
    match_type = str(payload.get("matchType") or "").upper()
    rank = str(payload.get("rank") or "").upper()
    key = payload.get("acceptedUsageKey") or payload.get("usageKey") or payload.get("speciesKey")
    if match_type == "NONE" or key is None:
        raise ValueError(f"GBIF could not match species name: {name}")
    if rank != "SPECIES":
        raise ValueError(f"GBIF match is rank {rank or 'unknown'}, not SPECIES: {name}")
    return {
        "taxon_key": int(key),
        "requested_name": name,
        "matched_name": str(payload.get("scientificName") or payload.get("canonicalName") or name),
        "match_type": match_type,
        "confidence": payload.get("confidence"),
        "status": payload.get("status"),
    }


def fetch_region_occurrences(
    taxon_key: int,
    bounds: tuple[float, float, float, float],
    *,
    cap: int = VALIDATED_OCCURRENCE_CAP,
) -> pd.DataFrame:
    """Fetch and clean the same GBIF occurrence object used by confirmation."""
    from gbif_fieldmap_builder_app import clean_occurrences, detect_occurrence_columns, gbif_record_to_species_row

    payload = get_json(
        GBIF_SEARCH,
        {
            "taxonKey": int(taxon_key),
            "geometry": _rectangle_wkt(bounds),
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
        raise ValueError("GBIF returned no usable occurrence rows in the declared extent")
    cleaned = clean_occurrences(raw, detect_occurrence_columns(raw)).copy().reset_index(drop=True)
    latitude_col, longitude_col = _coordinate_columns(cleaned)
    cleaned["latitude"] = pd.to_numeric(cleaned[latitude_col], errors="coerce")
    cleaned["longitude"] = pd.to_numeric(cleaned[longitude_col], errors="coerce")
    cleaned = cleaned.dropna(subset=["latitude", "longitude"]).drop_duplicates(
        ["latitude", "longitude"]
    ).reset_index(drop=True)
    if len(cleaned) < 5:
        raise ValueError(f"fewer than five usable occurrence rows in the declared extent: {len(cleaned)}")
    return cleaned


def _prototype_coordinates(occurrences: pd.DataFrame) -> pd.DataFrame:
    from gbif_fieldmap_builder_app import spatial_thin

    work = occurrences[["latitude", "longitude"]].copy()
    work["_latitude"] = pd.to_numeric(work["latitude"], errors="coerce")
    work["_longitude"] = pd.to_numeric(work["longitude"], errors="coerce")
    work = work.dropna(subset=["_latitude", "_longitude"]).reset_index(drop=True)
    if len(work) < 5:
        raise ValueError("fewer than five occurrence coordinates")
    chosen = work
    for thinning_m in (5_000.0, 10_000.0, 20_000.0, 40_000.0, 80_000.0):
        candidate = spatial_thin(work, thinning_m)
        if len(candidate) >= 5:
            chosen = candidate
        if 5 <= len(candidate) <= VALIDATED_MAX_PROTOTYPES:
            chosen = candidate
            break
    if len(chosen) > VALIDATED_MAX_PROTOTYPES:
        chosen = chosen.iloc[:VALIDATED_MAX_PROTOTYPES].copy()
    return chosen[["_latitude", "_longitude"]].rename(
        columns={"_latitude": "latitude", "_longitude": "longitude"}
    ).reset_index(drop=True)


def _terrain_inputs(
    occurrences: pd.DataFrame,
    bounds: tuple[float, float, float, float],
    *,
    area_id: str,
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    from gbif_fieldmap_builder_app import extract_environment, generate_land_points

    west, south, east, north = _validate_bounds(bounds)
    seed = _stable_surface_seed(bounds)
    corners = pd.DataFrame(
        {
            "_latitude": [south, south, north, north],
            "_longitude": [west, east, west, east],
        }
    )
    surface = generate_land_points(
        corners,
        VALIDATED_SURFACE_POINTS,
        "bounding box",
        0.0,
        0.0,
        random_state=seed,
    )
    if len(surface) < max(20, int(VALIDATED_SURFACE_POINTS * 0.5)):
        raise ValueError(f"validated land surface produced only {len(surface)} usable points")
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
    surface["survey_area_id"] = str(area_id)
    if surface.empty:
        raise ValueError("no candidate-surface points have complete terrain features")

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
        raise ValueError("fewer than five unique complete training environment prototypes")
    return surface, prototypes, seed


def discover_validated_candidate_patches(
    taxon_name: str,
    bounds: tuple[float, float, float, float],
    *,
    area_id: str = "survey",
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Resolve a species and return only the validated candidate patches."""
    bounds = _validate_bounds(bounds)
    match = match_gbif_species(taxon_name)
    occurrences = fetch_region_occurrences(int(match["taxon_key"]), bounds)
    surface, prototypes, surface_seed = _terrain_inputs(
        occurrences,
        bounds,
        area_id=area_id,
    )
    patches, support_audit = validated_robust_candidate_patches(
        surface,
        prototypes,
        feature_columns=ROBUST_TERRAIN_FEATURES,
        area_col="survey_area_id",
    )
    audit: dict[str, object] = {
        "input_mode": "taxon_extent",
        **match,
        "extent": list(bounds),
        "survey_area_id": str(area_id),
        "occurrence_rows": int(len(occurrences)),
        "surface_points": int(len(surface)),
        "surface_seed": int(surface_seed),
        "prototype_rows": int(len(prototypes)),
        "feature_columns": list(ROBUST_TERRAIN_FEATURES),
        "support_audit": support_audit.as_dict(),
        "candidate_patch_count": int(len(patches)),
        "candidate_generation_only": True,
        "routing_or_budget_optimization": False,
    }
    return patches, audit
