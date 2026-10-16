"""Species-name entry to historical country planning, not patch generation."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from importlib.resources import files
import json
import re

import requests

from .country_frames import plan_automatic_global_country, plan_explicit_target_country
from .providers.gbif import GBIF_OCCURRENCE_URL, _get_json, match_species

HISTORICAL_YEARS = (1900, 2020)
COUNTRY_SELECTION_SEED = 2026090701
COVERAGE_FINGERPRINT = "377f6374e077cc38ea7fc026de6dc289abc2716aca8c83d66ddcd42826139520"
ISO_FINGERPRINT = "1c6bfa83da614b0637433f2020126c26b3c1178c4114e91c81d50c931d042bde"


class CountryPlanningProviderError(ValueError):
    """Provider response is unusable, not evidence of biological absence."""


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _provider_inventory() -> tuple[dict[str, str], set[str]]:
    root = files("acsp.discovery").joinpath("data")
    coverage = json.loads(root.joinpath("acsp_geoboundaries_v6_adm0_coverage_v1.json").read_text(encoding="utf-8"))
    stored = coverage.pop("coverage_contract_fingerprint", None)
    if stored != COVERAGE_FINGERPRINT or _digest(coverage) != COVERAGE_FINGERPRINT:
        raise ValueError("packaged coverage contract fingerprint mismatch")
    iso = json.loads(root.joinpath("iso3166_alpha2_to_alpha3_pycountry_24_6_1.json").read_text(encoding="utf-8"))
    if _digest(iso) != ISO_FINGERPRINT:
        raise ValueError("packaged ISO mapping fingerprint mismatch")
    mapping = iso["alpha2_to_alpha3"]
    supported = set(coverage["coverage"]["supported_alpha3"])
    return mapping, {code for code, alpha3 in mapping.items() if alpha3 in supported}


def _country_counts(payload: dict) -> dict[str, int]:
    # Unlike a verified empty country facet, a missing/malformed response must
    # not become NO_HISTORICAL_COUNTRY. Never infer absence from provider errors.
    facets = payload.get("facets")
    if not isinstance(facets, list):
        raise CountryPlanningProviderError("GBIF country facets missing")
    if not facets and type(payload.get("count")) is int and payload["count"] == 0:
        return {}
    matching = [f for f in facets if isinstance(f, dict) and str(f.get("field", "")).upper() in {"COUNTRY", "COUNTRYCODE"}]
    if len(matching) != 1 or not isinstance(matching[0].get("counts"), list):
        raise CountryPlanningProviderError("GBIF country facet is missing or ambiguous")
    counts: dict[str, int] = {}
    for item in matching[0]["counts"]:
        if not isinstance(item, dict):
            raise CountryPlanningProviderError("malformed GBIF country count")
        code = str(item.get("name") or "").strip().upper()
        # Match the research parser's exclusion of non-country facet names.
        if not re.fullmatch(r"[A-Z]{2}", code):
            continue
        count = item.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise CountryPlanningProviderError("invalid GBIF country count")
        if count:
            counts[code] = counts.get(code, 0) + count
    return dict(sorted(counts.items()))


def plan_country_for_species(scientific_name: str, *, country: str = "", session=None) -> dict:
    """Return a historical-only country plan using the frozen coverage and rule.

    No geometry, terrain, individual occurrence rows, patches or heldout data
    are fetched. READY means country planning succeeded, not habitat suitability.
    """
    mapping, supported = _provider_inventory()
    target = str(country or "").strip().upper()
    if target and target not in mapping:
        raise ValueError("country must be a frozen ISO alpha-2 code")
    client = session or requests.Session()
    try:
        match = match_species(scientific_name, session=client)
        params = {
            "taxonKey": int(match["usageKey"]), "year": "1900,2020",
            "hasCoordinate": "true", "hasGeospatialIssue": "false",
            "occurrenceStatus": "PRESENT", "limit": 0,
            "facet": "country", "facetLimit": 300, "facetOffset": 0,
        }
        counts = _country_counts(_get_json(client, GBIF_OCCURRENCE_URL, params, timeout=45))
    finally:
        if session is None:
            client.close()
    options = dict(provider_supported_country_codes=supported, historical_min_count=5, tie_break_seed=COUNTRY_SELECTION_SEED)
    plan = plan_explicit_target_country(target, counts, **options) if target else plan_automatic_global_country(counts, **options)
    return {
        "schema_version": "acsp-historical-country-plan-v1",
        "status": plan.state.value,
        "requested_name": str(scientific_name).strip(),
        "provider_id": "GBIF",
        "provider_url": GBIF_OCCURRENCE_URL,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "matched_scientific_name": str(match.get("scientificName") or match.get("canonicalName") or scientific_name),
        "matched_usage_key": int(match["usageKey"]),
        "match_confidence": match.get("confidence"),
        "requested_country": target or None,
        "historical_years": list(HISTORICAL_YEARS),
        "historical_country_counts": counts,
        "query_parameters": params,
        "coverage_contract_fingerprint": COVERAGE_FINGERPRINT,
        "country_selection_seed": COUNTRY_SELECTION_SEED,
        "country_plan": plan.as_dict(),
        "candidate_generation_run": False,
        "country_geometry_opened": False,
        "heldout_2021_2025_opened": False,
        "field_outcomes_used": False,
        "warning": "Country planning only: no candidate patches, occupancy or field-efficiency claim. An explicit-country application is not independently confirmed.",
    }
