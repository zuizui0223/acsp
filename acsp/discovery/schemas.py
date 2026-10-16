"""Provider-neutral input contracts for experimental N4 discovery."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

import numpy as np
import pandas as pd

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class OccurrenceEvidenceAudit:
    row_count: int
    provider_count: int
    min_year: int
    max_year: int
    rows_with_declared_uncertainty: int
    coordinate_rows_complete: int


@dataclass(frozen=True)
class CandidateFrameSchemaAudit:
    row_count: int
    unique_candidate_ids: int
    grid_cells_unique: bool
    nearest_anchor_distance_available: bool


@dataclass(frozen=True)
class SourceManifestAudit:
    source_count: int
    provider_count: int
    roles: tuple[str, ...]
    all_sha256_pinned: bool


def normalize_occurrence_evidence(frame: pd.DataFrame) -> tuple[pd.DataFrame, OccurrenceEvidenceAudit]:
    """Validate one provider-neutral occurrence-evidence table.

    Required columns intentionally retain uncertainty/provenance rather than
    deciding whether a row is an exact anchor. A separately frozen experiment
    supplies precision and time-window gates.
    """
    required = {
        "occurrence_id",
        "latitude",
        "longitude",
        "event_year",
        "coordinate_uncertainty_m",
        "provider_id",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"occurrence evidence missing columns: {missing}")
    out = frame.copy().reset_index(drop=True)
    if out.empty:
        raise ValueError("occurrence evidence cannot be empty")
    out["occurrence_id"] = out["occurrence_id"].astype(str).str.strip()
    out["provider_id"] = out["provider_id"].astype(str).str.strip()
    if (out["occurrence_id"] == "").any() or out["occurrence_id"].duplicated().any():
        raise ValueError("occurrence_id must be complete and unique")
    if (out["provider_id"] == "").any():
        raise ValueError("provider_id must be complete")
    for column in ("latitude", "longitude", "event_year", "coordinate_uncertainty_m"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    if out[["latitude", "longitude", "event_year"]].isna().any().any():
        raise ValueError("occurrence coordinates and event_year must be complete")
    if not out["latitude"].between(-90, 90).all() or not out["longitude"].between(-180, 180).all():
        raise ValueError("occurrence coordinates are outside valid longitude/latitude ranges")
    if not np.isfinite(out["event_year"].to_numpy(float)).all():
        raise ValueError("event_year must be finite")
    rounded_year = np.rint(out["event_year"].to_numpy(float))
    if not np.allclose(out["event_year"].to_numpy(float), rounded_year):
        raise ValueError("event_year must be integer-valued")
    out["event_year"] = rounded_year.astype(int)
    if (out["event_year"] < 1600).any() or (out["event_year"] > 2200).any():
        raise ValueError("event_year is outside the supported provenance range")
    uncertainty = out["coordinate_uncertainty_m"].to_numpy(float)
    finite_uncertainty = np.isfinite(uncertainty)
    if np.any(finite_uncertainty & (uncertainty < 0)):
        raise ValueError("coordinate_uncertainty_m cannot be negative")
    out.loc[~finite_uncertainty, "coordinate_uncertainty_m"] = np.nan
    audit = OccurrenceEvidenceAudit(
        row_count=int(len(out)),
        provider_count=int(out["provider_id"].nunique()),
        min_year=int(out["event_year"].min()),
        max_year=int(out["event_year"].max()),
        rows_with_declared_uncertainty=int(out["coordinate_uncertainty_m"].notna().sum()),
        coordinate_rows_complete=int(out[["latitude", "longitude"]].notna().all(axis=1).sum()),
    )
    return out, audit


def validate_candidate_frame_schema(frame: pd.DataFrame) -> CandidateFrameSchemaAudit:
    """Validate the candidate-frame object consumed by discovery selectors."""
    required = {"candidate_cell_id", "latitude", "longitude", "grid_row", "grid_col"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"candidate frame missing columns: {missing}")
    if frame.empty:
        raise ValueError("candidate frame cannot be empty")
    ids = frame["candidate_cell_id"].astype(str).str.strip()
    if (ids == "").any() or ids.duplicated().any():
        raise ValueError("candidate_cell_id must be complete and unique")
    lat = pd.to_numeric(frame["latitude"], errors="coerce")
    lon = pd.to_numeric(frame["longitude"], errors="coerce")
    rows = pd.to_numeric(frame["grid_row"], errors="coerce")
    cols = pd.to_numeric(frame["grid_col"], errors="coerce")
    if pd.concat([lat, lon, rows, cols], axis=1).isna().any().any():
        raise ValueError("candidate coordinates and grid indices must be complete")
    if not lat.between(-90, 90).all() or not lon.between(-180, 180).all():
        raise ValueError("candidate coordinates are outside valid longitude/latitude ranges")
    grid_pairs = list(zip(rows.astype(int), cols.astype(int)))
    if len(set(grid_pairs)) != len(grid_pairs):
        raise ValueError("grid_row/grid_col pairs must be unique")
    if "nearest_anchor_km" in frame.columns:
        distance = pd.to_numeric(frame["nearest_anchor_km"], errors="coerce")
        if distance.isna().any() or (distance < 0).any():
            raise ValueError("nearest_anchor_km must be complete and non-negative when supplied")
    return CandidateFrameSchemaAudit(
        row_count=int(len(frame)),
        unique_candidate_ids=int(ids.nunique()),
        grid_cells_unique=True,
        nearest_anchor_distance_available=bool("nearest_anchor_km" in frame.columns),
    )


def validate_source_manifest(manifest: dict[str, Any]) -> SourceManifestAudit:
    """Validate provider/source provenance before candidate support is generated."""
    if not isinstance(manifest, dict):
        raise ValueError("source manifest must be a mapping")
    if not str(manifest.get("schema_version", "")).strip():
        raise ValueError("source manifest requires schema_version")
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("source manifest requires a non-empty sources list")
    roles: list[str] = []
    providers: set[str] = set()
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            raise ValueError(f"source {index} must be a mapping")
        for key in ("provider_id", "layer_role", "release_id", "retrieved_at", "source_uri", "sha256"):
            if not str(source.get(key, "")).strip():
                raise ValueError(f"source {index} missing {key}")
        digest = str(source["sha256"]).lower().removeprefix("sha256:")
        if not _SHA256_RE.fullmatch(digest):
            raise ValueError(f"source {index} sha256 must contain exactly 64 hexadecimal characters")
        roles.append(str(source["layer_role"]).strip())
        providers.add(str(source["provider_id"]).strip())
    if len(set(roles)) != len(roles):
        raise ValueError("each layer_role must occur once in a normalized source manifest")
    return SourceManifestAudit(
        source_count=int(len(sources)),
        provider_count=int(len(providers)),
        roles=tuple(sorted(roles)),
        all_sha256_pinned=True,
    )
