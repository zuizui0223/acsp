"""Historical inputs and geometry types ported from the frozen global adapter."""
from __future__ import annotations
from dataclasses import dataclass
import re
import pandas as pd
from shapely import wkt
from acsp.benchmarking import get_json as _get_json
from acsp.taxon_patches import GBIF_SEARCH, VALIDATED_OCCURRENCE_CAP, _coordinate_columns
HISTORICAL_YEARS = (1900, 2020)
_COUNTRY_CODE = re.compile(r"^[A-Z]{2}$")


def get_json(*args, **kwargs):
    """Reject malformed transport payloads before the unchanged research body."""
    payload = _get_json(*args, **kwargs)
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("malformed GBIF occurrence response: expected results list")
    if any(not isinstance(record, dict) for record in payload["results"]):
        raise ValueError("malformed GBIF occurrence response: expected record objects")
    return payload


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
