"""Species-name adapters for the validated ACSP candidate-patch product.

The input-generation path mirrors the untouched cross-taxon confirmation:
GBIF occurrence retrieval inside a fixed region, deterministic spatial thinning
to at most 32 occurrence prototypes, one fixed 800-point land surface per
region, the confirmed terrain feature set, and the validated 2.5% robust-support
candidate-patch rule.

The simplest product path uses the same 12 Japanese region rectangles that
structured the untouched confirmation. It adds no route, budget, day,
movement-mode, top-k, or threshold optimization.
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

# Exact regional rectangles used by the cross-taxon Japan confirmation design.
# They intentionally remain separate evaluation units; overlapping units such as
# Kanto and Izu are not merged after candidate generation.
VALIDATED_JAPAN_REGIONS = (
    ("hokkaido-west", "Hokkaido west", "north", 140.0, 42.5, 142.0, 44.5),
    ("hokkaido-east", "Hokkaido east", "north", 143.0, 42.5, 145.5, 44.5),
    ("tohoku", "Tohoku", "north", 139.5, 38.0, 141.5, 40.5),
    ("kanto", "Kanto", "east", 138.5, 35.0, 140.5, 36.5),
    ("izu", "Izu", "east", 138.8, 34.0, 139.8, 35.0),
    ("chubu-mountains", "Chubu mountains", "east", 136.5, 35.0, 138.5, 37.0),
    ("kinki", "Kinki", "west", 134.5, 33.5, 136.5, 35.5),
    ("chugoku", "Chugoku", "west", 131.5, 34.0, 134.0, 35.5),
    ("shikoku", "Shikoku", "west", 132.5, 32.7, 134.5, 34.5),
    ("northern-kyushu", "Northern Kyushu", "south", 129.5, 32.5, 131.5, 34.0),
    ("southern-kyushu", "Southern Kyushu", "south", 130.0, 30.8, 131.8, 32.5),
    ("ryukyu", "Ryukyu", "south", 126.0, 24.0, 130.0, 28.5),
)


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
    """Resolve a species and return validated candidate patches for one region."""
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


def discover_validated_candidate_patches_japan(
    taxon_name: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Return candidate patches across the 12 fixed Japanese validation regions.

    Each region is evaluated independently with the same occurrence cap,
    prototype rule, 800-point surface, feature set, and frozen 2.5% support
    rule used in confirmation. Regions with insufficient data are retained in
    the audit as skipped and do not trigger threshold widening or replacement.
    """
    match = match_gbif_species(taxon_name)
    patch_frames: list[pd.DataFrame] = []
    region_status: list[dict[str, object]] = []
    evaluated_regions = 0

    for region_id, region_name, geographic_stratum, west, south, east, north in VALIDATED_JAPAN_REGIONS:
        bounds = (float(west), float(south), float(east), float(north))
        try:
            occurrences = fetch_region_occurrences(int(match["taxon_key"]), bounds)
            surface, prototypes, surface_seed = _terrain_inputs(
                occurrences,
                bounds,
                area_id=region_id,
            )
            patches, support_audit = validated_robust_candidate_patches(
                surface,
                prototypes,
                feature_columns=ROBUST_TERRAIN_FEATURES,
                area_col="survey_area_id",
            )
            evaluated_regions += 1
            patches = patches.copy()
            patches["validation_region_id"] = str(region_id)
            patches["validation_region_name"] = str(region_name)
            patches["validation_geographic_stratum"] = str(geographic_stratum)
            patch_frames.append(patches)
            region_status.append(
                {
                    "region_id": str(region_id),
                    "region_name": str(region_name),
                    "geographic_stratum": str(geographic_stratum),
                    "extent": list(bounds),
                    "status": "evaluated",
                    "occurrence_rows": int(len(occurrences)),
                    "surface_points": int(len(surface)),
                    "surface_seed": int(surface_seed),
                    "prototype_rows": int(len(prototypes)),
                    "candidate_patch_count": int(len(patches)),
                    "support_audit": support_audit.as_dict(),
                    "failure_reason": "",
                }
            )
        except Exception as exc:
            region_status.append(
                {
                    "region_id": str(region_id),
                    "region_name": str(region_name),
                    "geographic_stratum": str(geographic_stratum),
                    "extent": list(bounds),
                    "status": "skipped_insufficient_or_unavailable",
                    "occurrence_rows": 0,
                    "surface_points": 0,
                    "prototype_rows": 0,
                    "candidate_patch_count": 0,
                    "failure_reason": f"{type(exc).__name__}: {exc}",
                }
            )

    if evaluated_regions == 0:
        raise ValueError(
            "no fixed Japanese validation region had enough usable occurrence/environment data"
        )

    patches = pd.concat(patch_frames, ignore_index=True, sort=False) if patch_frames else pd.DataFrame()
    audit: dict[str, object] = {
        "input_mode": "taxon_japan_validated_regions",
        **match,
        "region_rule": "the 12 fixed Japanese rectangles used by the cross-taxon confirmation design",
        "declared_region_count": int(len(VALIDATED_JAPAN_REGIONS)),
        "evaluated_region_count": int(evaluated_regions),
        "skipped_region_count": int(len(VALIDATED_JAPAN_REGIONS) - evaluated_regions),
        "candidate_patch_count": int(len(patches)),
        "feature_columns": list(ROBUST_TERRAIN_FEATURES),
        "candidate_generation_only": True,
        "routing_or_budget_optimization": False,
        "region_status": region_status,
    }
    return patches.reset_index(drop=True), audit
