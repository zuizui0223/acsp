"""Species matching and transport from the pinned global adapter."""
from __future__ import annotations
from typing import Any
import requests

GBIF_MATCH_URL = "https://api.gbif.org/v1/species/match"
GBIF_OCCURRENCE_URL = "https://api.gbif.org/v1/occurrence/search"


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
