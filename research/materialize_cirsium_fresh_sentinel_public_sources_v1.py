#!/usr/bin/env python3
"""Materialize frozen public-source inputs for fresh Cirsium SENTINEL units.

This execution adapter deliberately requires an already-frozen private range-sector
geometry. Given that geometry, it reconstructs only pre-field public inputs already
declared by the ACSP contracts: GSI DEM, ESA WorldCover 2021, and (for the two
UNCERTAINTY_FOOTPRINT units) coordinate-bearing GBIF records with declared
uncertainty strictly above the frozen 1-km local-anchor ceiling.

Coordinate-bearing outputs are private by construction and cannot be written inside
the git repository. No field outcome, access, permission, route, day, or budget
column is read.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
from pathlib import Path
from typing import Any

import pandas as pd

from research.audit_cirsium_aza3_gbif_occurrences_v1 import (
    MAX_PRIMARY_UNCERTAINTY_M,
    fetch_occurrences,
    gbif_taxon_match,
    parse_year,
    temporal_class,
    uncertainty_m,
)
from research.audit_cirsium_aza3_gbif_occurrences_v2 import (
    _generalized,
    _has_coordinates,
    _serious_issue,
)

ROOT = Path(__file__).resolve().parents[1]
COHORT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_cohort_v1.csv"
REQUIREMENTS = ROOT / "validation" / "cirsium_private_frame_source_requirements_v1.csv"
EXPECTED_UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
UNCERTAINTY_UNITS = ("CIR02", "CIR12")


def _inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT.resolve())
        return True
    except ValueError:
        return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _truth(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _unit_row(unit_id: str) -> tuple[dict[str, str], dict[str, str]]:
    cohort = {row["cohort_unit_id"]: row for row in csv.DictReader(COHORT.open(encoding="utf-8", newline=""))}
    requirements = {
        row["cohort_unit_id"]: row
        for row in csv.DictReader(REQUIREMENTS.open(encoding="utf-8", newline=""))
    }
    if unit_id not in EXPECTED_UNITS or unit_id not in cohort or unit_id not in requirements:
        raise ValueError(f"unit is not in the frozen fresh SENTINEL cohort: {unit_id}")
    row = cohort[unit_id]
    if row["outcome_opened"].strip().lower() != "false":
        raise ValueError(f"field outcome is already opened for {unit_id}")
    return row, requirements[unit_id]


def qualified_uncertainty_evidence(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Apply exactly the frozen v2 broad-uncertainty eligibility rule."""
    rows: list[dict[str, object]] = []
    for record in records:
        year = parse_year(record)
        if temporal_class(year) != "RECENT":
            continue
        if not _has_coordinates(record) or _serious_issue(record) or _generalized(record):
            continue
        unc = uncertainty_m(record)
        if unc is None or unc <= MAX_PRIMARY_UNCERTAINTY_M:
            continue
        try:
            latitude = float(record["decimalLatitude"])
            longitude = float(record["decimalLongitude"])
        except (TypeError, ValueError, KeyError):
            continue
        if not (math.isfinite(latitude) and math.isfinite(longitude)):
            continue
        rows.append(
            {
                "gbif_key": str(record.get("key") or ""),
                "latitude": latitude,
                "longitude": longitude,
                "coordinate_uncertainty_m": float(unc),
                "year": int(year),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["gbif_key", "latitude", "longitude", "coordinate_uncertainty_m", "year"])
    out = pd.DataFrame(rows)
    return out.sort_values(
        ["latitude", "longitude", "coordinate_uncertainty_m", "year", "gbif_key"],
        kind="mergesort",
    ).reset_index(drop=True)


def _geometry_bounds_and_references(path: Path) -> tuple[tuple[float, float, float, float], tuple[tuple[float, float], ...]]:
    from research.build_cirsium_private_alpine_local_grid_v1 import _load_geojson_geometry

    geometry = _load_geojson_geometry(path)
    west, south, east, north = map(float, geometry.bounds)
    representative = geometry.representative_point()
    references = (
        (float(representative.y), float(representative.x)),
        ((south + north) / 2.0, (west + east) / 2.0),
        (south, west),
        (south, east),
        (north, west),
        (north, east),
    )
    return (west, south, east, north), references


def materialize_public_sources(unit_id: str, range_sector_geojson: Path, private_dir: Path) -> dict[str, object]:
    unit, requirement = _unit_row(unit_id)
    private_dir = private_dir.resolve()
    if _inside_repo(private_dir):
        raise ValueError("private source materialization directory must be outside the git repository")
    if not range_sector_geojson.is_file():
        raise ValueError(f"missing frozen range-sector GeoJSON: {range_sector_geojson}")
    private_dir.mkdir(parents=True, exist_ok=True)

    bounds, references = _geometry_bounds_and_references(range_sector_geojson)
    outputs: dict[str, object] = {}

    if _truth(requirement.get("requires_gsi_dem", False)):
        from gbif_fieldmap_builder_app import build_gsi_dem_for_bounds

        source_dem, attribution = build_gsi_dem_for_bounds(bounds, references, max_tiles=400)
        if not source_dem:
            raise RuntimeError("frozen GSI DEM provider did not materialize a raster for the declared sector")
        dem_out = private_dir / f"{unit_id}_gsi_dem.tif"
        if Path(source_dem).resolve() != dem_out.resolve():
            shutil.copy2(source_dem, dem_out)
        outputs["gsi_dem"] = {
            "path": str(dem_out),
            "sha256": _sha256(dem_out),
            "attribution": str(attribution),
        }

    if _truth(requirement.get("requires_esa_worldcover_2021", False)):
        from acsp.discovery.providers import build_worldcover_2021_map_crop

        wc_out = private_dir / f"{unit_id}_esa_worldcover_2021_v200.tif"
        audit = build_worldcover_2021_map_crop(bounds, wc_out, margin_m=500.0)
        outputs["worldcover"] = {
            "path": str(wc_out),
            "sha256": _sha256(wc_out),
            "source_tile_ids": list(audit.source_tile_ids),
            "provider_output_sha256": audit.output_sha256,
        }

    if unit_id in UNCERTAINTY_UNITS:
        match = gbif_taxon_match(unit["species_binomial"])
        if match["classification"] != "AUTO_EXACT_ACCEPTED":
            raise RuntimeError(f"frozen species identity is no longer exact/accepted in GBIF: {match}")
        evidence = qualified_uncertainty_evidence(fetch_occurrences(str(match["usage_key"])))
        if evidence.empty:
            raise RuntimeError("no GBIF records satisfy the frozen >1-km uncertainty-footprint rule")
        evidence_out = private_dir / f"{unit_id}_gbif_uncertainty_evidence_private.csv"
        evidence.to_csv(evidence_out, index=False)
        outputs["sentinel_evidence"] = {
            "path": str(evidence_out),
            "sha256": _sha256(evidence_out),
            "row_count": int(len(evidence)),
            "taxon_match": match,
            "rule": "RECENT_2000_2025_AND_DECLARED_UNCERTAINTY_GT_1000M_AND_NOT_OBSCURED_AND_NO_SERIOUS_GEOSPATIAL_ISSUE",
        }

    summary = {
        "schema_version": "cirsium-fresh-sentinel-public-source-materialization-v1",
        "status": "PUBLIC_SOURCES_MATERIALIZED_PRE_FIELD",
        "cohort_unit_id": unit_id,
        "species_binomial": unit["species_binomial"],
        "range_sector_geometry_sha256": _sha256(range_sector_geojson),
        "range_sector_bounds_wgs84": list(bounds),
        "outputs": outputs,
        "field_outcomes_used": False,
        "human_access_used": False,
        "method_or_family_tuned": False,
        "exact_coordinates_public": False,
    }
    summary_path = private_dir / f"{unit_id}_public_source_materialization_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-id", choices=EXPECTED_UNITS, required=True)
    parser.add_argument("--range-sector-geojson", type=Path, required=True)
    parser.add_argument("--private-dir", type=Path, required=True)
    args = parser.parse_args()
    summary = materialize_public_sources(args.unit_id, args.range_sector_geojson, args.private_dir)
    print(json.dumps({
        "status": summary["status"],
        "cohort_unit_id": summary["cohort_unit_id"],
        "materialized": sorted(summary["outputs"]),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
