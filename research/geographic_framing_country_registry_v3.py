"""Development-only historical-country geographic framing v3.

V1 and v2 failed because both derived the outer search universe from local
occurrence components.  V3 deliberately tests a broader object: countries in
which the *focal species itself* had coordinate-bearing GBIF records during the
historical window 1900--2020.  Records from 2021--2025 are temporal held-out
outcomes and never enter the registry.

This module only evaluates geographic framing.  It does not generate candidate
surfaces, run robust ecological support, expand to neighbouring countries, or
fall back to higher taxa / continents / realms.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

import pandas as pd

from acsp.benchmarking import get_json

GBIF_OCCURRENCE_SEARCH = "https://api.gbif.org/v1/occurrence/search"
HISTORICAL_YEARS = (1900, 2020)
RECENT_YEARS = (2021, 2025)
COUNTRY_FACET_LIMIT = 300
REFERENCE_COUNTRY_CODE_COUNT = 249
_VALID_COUNTRY = re.compile(r"^[A-Z]{2}$")


@dataclass(frozen=True)
class CountryRegistryDiagnostic:
    pair_id: int
    scientific_name: str
    species_key: int
    taxon_group: str
    status: str
    historical_record_count: int
    recent_record_count: int
    recent_records_inside_registry: int
    recent_record_containment: float
    historical_country_count: int
    recent_country_count: int
    recent_countries_inside_registry: int
    recent_country_containment: float
    new_recent_country_count: int
    historical_country_fraction_of_249: float
    historical_countries: str
    recent_countries: str
    new_recent_countries: str
    historical_country_counts_json: str
    recent_country_counts_json: str
    failure_reason: str = ""

    def as_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


def _country_counts_from_payload(payload: dict[str, Any]) -> dict[str, int]:
    """Return positive two-letter country facet counts from a GBIF search response."""
    counts: dict[str, int] = {}
    for facet in payload.get("facets") or []:
        field = str(facet.get("field") or "").upper()
        if field not in {"COUNTRY", "COUNTRYCODE"}:
            continue
        for item in facet.get("counts") or []:
            code = str(item.get("name") or "").strip().upper()
            if not _VALID_COUNTRY.fullmatch(code):
                continue
            try:
                count = int(item.get("count") or 0)
            except (TypeError, ValueError):
                continue
            if count > 0:
                counts[code] = counts.get(code, 0) + count
    return dict(sorted(counts.items()))


def fetch_country_facet_counts(
    species_key: int,
    years: tuple[int, int],
) -> dict[str, int]:
    """Fetch all country facet counts for one focal species and fixed year range."""
    start, end = (int(years[0]), int(years[1]))
    if start > end:
        raise ValueError("year range must be ascending")
    payload = get_json(
        GBIF_OCCURRENCE_SEARCH,
        {
            "taxonKey": int(species_key),
            "year": f"{start},{end}",
            "hasCoordinate": "true",
            "hasGeospatialIssue": "false",
            "occurrenceStatus": "PRESENT",
            "limit": 0,
            "facet": "country",
            "facetLimit": COUNTRY_FACET_LIMIT,
            "facetOffset": 0,
        },
        timeout=45,
    )
    return _country_counts_from_payload(payload)


def evaluate_country_registry_taxon(row: pd.Series) -> CountryRegistryDiagnostic:
    """Evaluate one taxon's historical-country registry against recent GBIF records."""
    pair_id = int(row.pair_id)
    scientific_name = str(row.scientific_name)
    species_key = int(row.speciesKey)
    taxon_group = str(row.taxon_group)

    def zero(status: str, reason: str, *, historical: dict[str, int] | None = None, recent: dict[str, int] | None = None) -> CountryRegistryDiagnostic:
        h = dict(sorted((historical or {}).items()))
        r = dict(sorted((recent or {}).items()))
        return CountryRegistryDiagnostic(
            pair_id=pair_id,
            scientific_name=scientific_name,
            species_key=species_key,
            taxon_group=taxon_group,
            status=status,
            historical_record_count=int(sum(h.values())),
            recent_record_count=int(sum(r.values())),
            recent_records_inside_registry=0,
            recent_record_containment=0.0,
            historical_country_count=int(len(h)),
            recent_country_count=int(len(r)),
            recent_countries_inside_registry=0,
            recent_country_containment=0.0,
            new_recent_country_count=int(len(r)),
            historical_country_fraction_of_249=float(len(h) / REFERENCE_COUNTRY_CODE_COUNT),
            historical_countries=";".join(h),
            recent_countries=";".join(r),
            new_recent_countries=";".join(r),
            historical_country_counts_json=json.dumps(h, sort_keys=True, separators=(",", ":")),
            recent_country_counts_json=json.dumps(r, sort_keys=True, separators=(",", ":")),
            failure_reason=reason,
        )

    try:
        historical = fetch_country_facet_counts(species_key, HISTORICAL_YEARS)
    except Exception as exc:
        return zero("historical_provider_failed", f"{type(exc).__name__}: {exc}")
    if not historical:
        return zero("zero_historical_registry", "no valid historical country facet counts", historical=historical)

    try:
        recent = fetch_country_facet_counts(species_key, RECENT_YEARS)
    except Exception as exc:
        return zero("recent_provider_failed", f"{type(exc).__name__}: {exc}", historical=historical)
    if not recent:
        return zero("zero_recent_country_records", "no valid recent country facet counts", historical=historical, recent=recent)

    historical_set = set(historical)
    recent_set = set(recent)
    inside_countries = recent_set & historical_set
    new_countries = recent_set - historical_set
    total_recent = int(sum(recent.values()))
    inside_records = int(sum(recent[code] for code in inside_countries))
    return CountryRegistryDiagnostic(
        pair_id=pair_id,
        scientific_name=scientific_name,
        species_key=species_key,
        taxon_group=taxon_group,
        status="evaluated",
        historical_record_count=int(sum(historical.values())),
        recent_record_count=total_recent,
        recent_records_inside_registry=inside_records,
        recent_record_containment=float(inside_records / total_recent),
        historical_country_count=int(len(historical_set)),
        recent_country_count=int(len(recent_set)),
        recent_countries_inside_registry=int(len(inside_countries)),
        recent_country_containment=float(len(inside_countries) / len(recent_set)),
        new_recent_country_count=int(len(new_countries)),
        historical_country_fraction_of_249=float(len(historical_set) / REFERENCE_COUNTRY_CODE_COUNT),
        historical_countries=";".join(sorted(historical_set)),
        recent_countries=";".join(sorted(recent_set)),
        new_recent_countries=";".join(sorted(new_countries)),
        historical_country_counts_json=json.dumps(historical, sort_keys=True, separators=(",", ":")),
        recent_country_counts_json=json.dumps(recent, sort_keys=True, separators=(",", ":")),
        failure_reason="",
    )
