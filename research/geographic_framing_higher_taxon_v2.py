"""Development-only higher-taxon geographic prior for ACSP framing v2.

This module changes only the *source of geographic prior information* relative
 to rejected framing v1.  Frame geometry remains the v1 0.1-degree occupied
block / 8-neighbour component / frozen 10 km padding rule.

The prior is deliberately independent of focal-species training and held-out
coordinates.  GBIF occurrences of the focal genus are queried inside the fixed
development rectangle and every focal-species record is removed.  Family is a
fallback only when genus yields zero usable non-focal coordinates.  Provider
failure is explicit and does not trigger a broader fallback.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from acsp.benchmarking import get_json
from geographic_framing import (
    DEFAULT_BLOCK_DEGREES,
    DEFAULT_PADDING_KM,
    infer_training_block_frames,
)

GBIF_OCCURRENCE_SEARCH = "https://api.gbif.org/v1/occurrence/search"
GBIF_SPECIES = "https://api.gbif.org/v1/species"
FRAMING_METHOD_V2 = "higher_taxon_nonfocal_block_component_10km_padding_v2"
DEFAULT_PRIOR_RECORD_CAP = 300


@dataclass(frozen=True)
class HigherTaxonPriorAudit:
    focal_species_key: int
    focal_scientific_name: str
    genus_key: int | None
    family_key: int | None
    prior_rank_used: str | None
    prior_taxon_key_used: int | None
    raw_record_count: int
    usable_nonfocal_record_count: int
    focal_records_removed: int
    duplicate_coordinate_rows_removed: int
    status: str
    failure_reason: str = ""
    focal_training_coordinates_used: bool = False
    focal_heldout_coordinates_used: bool = False
    family_fallback_requires_zero_usable_genus: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "focal_species_key": self.focal_species_key,
            "focal_scientific_name": self.focal_scientific_name,
            "genus_key": self.genus_key,
            "family_key": self.family_key,
            "prior_rank_used": self.prior_rank_used,
            "prior_taxon_key_used": self.prior_taxon_key_used,
            "raw_record_count": self.raw_record_count,
            "usable_nonfocal_record_count": self.usable_nonfocal_record_count,
            "focal_records_removed": self.focal_records_removed,
            "duplicate_coordinate_rows_removed": self.duplicate_coordinate_rows_removed,
            "status": self.status,
            "failure_reason": self.failure_reason,
            "focal_training_coordinates_used": self.focal_training_coordinates_used,
            "focal_heldout_coordinates_used": self.focal_heldout_coordinates_used,
            "family_fallback_requires_zero_usable_genus": self.family_fallback_requires_zero_usable_genus,
        }


def rectangle_wkt(bounds: tuple[float, float, float, float]) -> str:
    west, south, east, north = (float(value) for value in bounds)
    if not (-180.0 <= west < east <= 180.0 and -90.0 <= south < north <= 90.0):
        raise ValueError("invalid development rectangle")
    return f"POLYGON(({west} {south},{east} {south},{east} {north},{west} {north},{west} {south}))"


def _optional_int(value: object) -> int | None:
    try:
        if value is None or pd.isna(value):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def focal_species_metadata(species_key: int) -> dict[str, object]:
    payload = get_json(f"{GBIF_SPECIES}/{int(species_key)}", timeout=30)
    return {
        "species_key": int(species_key),
        "scientific_name": str(payload.get("scientificName") or ""),
        "canonical_name": str(payload.get("canonicalName") or ""),
        "genus_key": _optional_int(payload.get("genusKey")),
        "family_key": _optional_int(payload.get("familyKey")),
    }


def _normalized_name(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _record_is_focal(record: dict[str, Any], focal_species_key: int, focal_names: set[str]) -> bool:
    for key_name in ("speciesKey", "acceptedTaxonKey", "taxonKey"):
        key = _optional_int(record.get(key_name))
        if key is not None and key == int(focal_species_key):
            return True
    for name_field in ("scientificName", "acceptedScientificName", "species"):
        normalized = _normalized_name(record.get(name_field))
        if normalized and normalized in focal_names:
            return True
    return False


def _query_prior_records(
    taxon_key: int,
    bounds: tuple[float, float, float, float],
    *,
    record_cap: int,
) -> list[dict[str, Any]]:
    payload = get_json(
        GBIF_OCCURRENCE_SEARCH,
        {
            "taxonKey": int(taxon_key),
            "geometry": rectangle_wkt(bounds),
            "hasCoordinate": "true",
            "hasGeospatialIssue": "false",
            "occurrenceStatus": "PRESENT",
            "limit": min(300, int(record_cap)),
            "offset": 0,
        },
        timeout=45,
    )
    return list(payload.get("results") or [])


def _usable_nonfocal_coordinates(
    records: list[dict[str, Any]],
    *,
    focal_species_key: int,
    focal_names: set[str],
) -> tuple[pd.DataFrame, int, int]:
    rows: list[tuple[float, float]] = []
    focal_removed = 0
    for record in records:
        if _record_is_focal(record, focal_species_key, focal_names):
            focal_removed += 1
            continue
        try:
            latitude = float(record.get("decimalLatitude"))
            longitude = float(record.get("decimalLongitude"))
        except (TypeError, ValueError):
            continue
        if not np.isfinite(latitude) or not np.isfinite(longitude):
            continue
        if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
            continue
        rows.append((latitude, longitude))
    frame = pd.DataFrame(rows, columns=["_latitude", "_longitude"])
    before = len(frame)
    frame = frame.drop_duplicates(["_latitude", "_longitude"]).reset_index(drop=True)
    return frame, int(focal_removed), int(before - len(frame))


def fetch_nonfocal_higher_taxon_prior(
    focal_species_key: int,
    bounds: tuple[float, float, float, float],
    *,
    focal_scientific_name: str = "",
    record_cap: int = DEFAULT_PRIOR_RECORD_CAP,
) -> tuple[pd.DataFrame, HigherTaxonPriorAudit]:
    """Fetch a non-focal genus prior, with family fallback only for zero genus rows."""
    if int(record_cap) <= 0:
        raise ValueError("record_cap must be positive")
    metadata = focal_species_metadata(int(focal_species_key))
    focal_names = {
        normalized
        for normalized in (
            _normalized_name(focal_scientific_name),
            _normalized_name(metadata["scientific_name"]),
            _normalized_name(metadata["canonical_name"]),
        )
        if normalized
    }
    genus_key = _optional_int(metadata["genus_key"])
    family_key = _optional_int(metadata["family_key"])
    last_raw_count = 0
    total_focal_removed = 0
    total_duplicates_removed = 0

    candidates: list[tuple[str, int]] = []
    if genus_key is not None:
        candidates.append(("GENUS", genus_key))
    if family_key is not None and family_key != genus_key:
        candidates.append(("FAMILY", family_key))

    if not candidates:
        return pd.DataFrame(columns=["_latitude", "_longitude"]), HigherTaxonPriorAudit(
            int(focal_species_key), str(focal_scientific_name), genus_key, family_key,
            None, None, 0, 0, 0, 0, "missing_higher_taxon_key",
            "GBIF species metadata contains neither usable genusKey nor familyKey",
        )

    for rank, taxon_key in candidates:
        try:
            records = _query_prior_records(taxon_key, bounds, record_cap=int(record_cap))
        except Exception as exc:
            return pd.DataFrame(columns=["_latitude", "_longitude"]), HigherTaxonPriorAudit(
                int(focal_species_key), str(focal_scientific_name), genus_key, family_key,
                rank, int(taxon_key), 0, 0, total_focal_removed, total_duplicates_removed,
                "provider_failed", f"{type(exc).__name__}: {exc}",
            )
        last_raw_count = int(len(records))
        prior, focal_removed, duplicates_removed = _usable_nonfocal_coordinates(
            records,
            focal_species_key=int(focal_species_key),
            focal_names=focal_names,
        )
        total_focal_removed += int(focal_removed)
        total_duplicates_removed += int(duplicates_removed)
        if not prior.empty:
            return prior, HigherTaxonPriorAudit(
                int(focal_species_key), str(focal_scientific_name), genus_key, family_key,
                rank, int(taxon_key), last_raw_count, int(len(prior)),
                total_focal_removed, total_duplicates_removed, "ready", "",
            )
        # Family fallback is allowed only after a successful genus query that
        # yielded zero usable non-focal coordinates (or when genusKey is absent).

    return pd.DataFrame(columns=["_latitude", "_longitude"]), HigherTaxonPriorAudit(
        int(focal_species_key), str(focal_scientific_name), genus_key, family_key,
        candidates[-1][0], candidates[-1][1], last_raw_count, 0,
        total_focal_removed, total_duplicates_removed, "no_usable_nonfocal_prior",
        "genus/family queries yielded zero usable non-focal coordinates",
    )


def infer_higher_taxon_prior_frames(
    prior_occurrences: pd.DataFrame,
    *,
    prior_audit: HigherTaxonPriorAudit,
    block_degrees: float = DEFAULT_BLOCK_DEGREES,
    padding_km: float = DEFAULT_PADDING_KM,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Apply unchanged v1 frame geometry to a non-focal higher-taxon prior."""
    if prior_audit.status != "ready":
        raise ValueError(f"higher-taxon prior is not ready: {prior_audit.status}")
    frames, occurrence_audit, summary = infer_training_block_frames(
        prior_occurrences,
        latitude_col="_latitude",
        longitude_col="_longitude",
        block_degrees=float(block_degrees),
        padding_km=float(padding_km),
    )
    if not frames.empty:
        frames = frames.copy()
        frames["framing_method"] = FRAMING_METHOD_V2
        frames["training_only"] = False
        frames["higher_taxon_prior_only"] = True
        frames["prior_rank_used"] = prior_audit.prior_rank_used
        frames["prior_taxon_key_used"] = prior_audit.prior_taxon_key_used
    occurrence_audit = occurrence_audit.copy()
    if not occurrence_audit.empty:
        occurrence_audit["scope_class"] = "retained_nonfocal_higher_taxon_prior"
        occurrence_audit["focal_training_coordinate"] = False
        occurrence_audit["focal_heldout_coordinate"] = False
    summary = {
        **summary,
        "framing_method": FRAMING_METHOD_V2,
        "prior_rank_used": prior_audit.prior_rank_used,
        "prior_taxon_key_used": prior_audit.prior_taxon_key_used,
        "prior_record_count": int(len(prior_occurrences)),
        "focal_training_coordinates_used": False,
        "focal_heldout_coordinates_used": False,
        "frame_geometry_reused_from_v1": True,
    }
    return frames, occurrence_audit, summary
