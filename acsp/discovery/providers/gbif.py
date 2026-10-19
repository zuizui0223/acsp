"""GBIF occurrence adapter for experimental ACSP Discovery.

The adapter retrieves public occurrence evidence but does not decide whether a
record is an exact anchor. Coordinate uncertainty is preserved as reported and
is evaluated later by the discovery evidence policy.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import time
from typing import Any

import pandas as pd
import requests

GBIF_MATCH_URL = "https://api.gbif.org/v1/species/match"
GBIF_OCCURRENCE_URL = "https://api.gbif.org/v1/occurrence/search"


@dataclass(frozen=True)
class GBIFOccurrenceAudit:
    requested_name: str
    matched_scientific_name: str
    matched_usage_key: int
    match_confidence: int | None
    country: str
    year_from: int | None
    year_to: int | None
    raw_records_seen: int
    normalized_records: int
    pages: int
    provider_id: str = "GBIF"
    coordinate_precision_filter_applied: bool = False
    field_outcomes_used: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _get_json(session: requests.Session, url: str, params: dict[str, Any], *, timeout: int = 60) -> dict:
    response = session.get(url, params=params, timeout=timeout, headers={"User-Agent": "acsp-discovery/0.3 public-research"})
    response.raise_for_status()
    return response.json()


def match_species(scientific_name: str, *, session: requests.Session | None = None) -> dict[str, Any]:
    name = str(scientific_name).strip()
    if not name:
        raise ValueError("scientific_name is required")
    client = session or requests.Session()
    payload = _get_json(client, GBIF_MATCH_URL, {"name": name, "rank": "SPECIES"}, timeout=30)
    usage_key = payload.get("usageKey")
    rank = str(payload.get("rank") or "").upper()
    if usage_key is None or rank != "SPECIES":
        raise ValueError(f"GBIF did not resolve a species-rank usage key for {name!r}: rank={rank!r}")
    return payload


def fetch_gbif_occurrence_evidence(
    scientific_name: str,
    *,
    country: str = "",
    year_from: int | None = None,
    year_to: int | None = None,
    maximum_records: int = 10000,
    page_size: int = 300,
    pause_seconds: float = 0.02,
    session: requests.Session | None = None,
) -> tuple[pd.DataFrame, GBIFOccurrenceAudit]:
    """Fetch provider-neutral occurrence evidence for one matched GBIF species."""
    if int(maximum_records) < 1:
        raise ValueError("maximum_records must be positive")
    if int(page_size) < 1 or int(page_size) > 300:
        raise ValueError("page_size must be between 1 and 300")
    if year_from is not None and year_to is not None and int(year_from) > int(year_to):
        raise ValueError("year_from cannot exceed year_to")

    client = session or requests.Session()
    match = match_species(scientific_name, session=client)
    usage_key = int(match["usageKey"])
    matched_name = str(match.get("scientificName") or match.get("canonicalName") or scientific_name)
    params_base: dict[str, Any] = {
        "taxonKey": usage_key,
        "hasCoordinate": "true",
        "hasGeospatialIssue": "false",
        "occurrenceStatus": "PRESENT",
    }
    country_code = str(country or "").strip().upper()
    if country_code:
        if len(country_code) != 2:
            raise ValueError("country must be a two-letter GBIF/ISO country code such as JP")
        params_base["country"] = country_code
    if year_from is not None or year_to is not None:
        left = "" if year_from is None else str(int(year_from))
        right = "" if year_to is None else str(int(year_to))
        params_base["year"] = f"{left},{right}"

    rows: list[dict[str, Any]] = []
    offset = 0
    pages = 0
    raw_seen = 0
    while offset < int(maximum_records):
        limit = min(int(page_size), int(maximum_records) - offset)
        payload = _get_json(client, GBIF_OCCURRENCE_URL, {**params_base, "limit": limit, "offset": offset})
        batch = payload.get("results") or []
        pages += 1
        raw_seen += len(batch)
        for record in batch:
            # For infraspecific occurrences GBIF still reports the parent speciesKey.
            try:
                species_key = int(record.get("speciesKey"))
            except (TypeError, ValueError):
                species_key = -1
            if species_key != usage_key:
                continue
            try:
                latitude = float(record["decimalLatitude"])
                longitude = float(record["decimalLongitude"])
                year = int(record["year"])
            except (KeyError, TypeError, ValueError):
                continue
            uncertainty = record.get("coordinateUncertaintyInMeters")
            try:
                uncertainty_m = float(uncertainty) if uncertainty is not None else None
            except (TypeError, ValueError):
                uncertainty_m = None
            occurrence_id = str(record.get("key") or record.get("occurrenceID") or "").strip()
            if not occurrence_id:
                continue
            rows.append(
                {
                    "occurrence_id": occurrence_id,
                    "latitude": latitude,
                    "longitude": longitude,
                    "event_year": year,
                    "coordinate_uncertainty_m": uncertainty_m,
                    "provider_id": "GBIF",
                }
            )
        if payload.get("endOfRecords", False) or not batch or len(batch) < limit:
            break
        offset += len(batch)
        if pause_seconds:
            time.sleep(max(0.0, float(pause_seconds)))

    frame = pd.DataFrame(
        rows,
        columns=["occurrence_id", "latitude", "longitude", "event_year", "coordinate_uncertainty_m", "provider_id"],
    )
    if not frame.empty:
        frame = (
            frame.drop_duplicates(subset=["occurrence_id"], keep="first")
            .sort_values(["event_year", "latitude", "longitude", "occurrence_id"], kind="mergesort")
            .reset_index(drop=True)
        )
    audit = GBIFOccurrenceAudit(
        requested_name=str(scientific_name).strip(),
        matched_scientific_name=matched_name,
        matched_usage_key=usage_key,
        match_confidence=int(match["confidence"]) if match.get("confidence") is not None else None,
        country=country_code,
        year_from=None if year_from is None else int(year_from),
        year_to=None if year_to is None else int(year_to),
        raw_records_seen=int(raw_seen),
        normalized_records=int(len(frame)),
        pages=int(pages),
    )
    return frame, audit
