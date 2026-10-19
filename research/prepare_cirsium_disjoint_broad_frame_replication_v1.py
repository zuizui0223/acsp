#!/usr/bin/env python3
"""Freeze historical-only frames for the disjoint Cirsium broad-frame replication.

This script MUST NOT fetch 2021-2025 outcomes. For each frozen taxon it uses only
strict 2000-2020 GBIF evidence to choose one externally allowed fixed Japanese
region, then freezes matched-resolution BROAD and LOCAL land candidate universes.
Only coordinate-free counts and SHA-256 fingerprints are written publicly.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acsp.discovery import (
    attach_nearest_anchor_distance,
    build_rectangular_candidate_frame,
    cluster_medoid_table,
    complete_link_clusters,
)
from acsp.discovery.providers import (
    fetch_gbif_occurrence_evidence,
    retain_worldcover_land_points,
)
from acsp.taxon_patches import VALIDATED_JAPAN_REGIONS

CONTRACT = ROOT / "validation" / "cirsium_disjoint_broad_frame_replication_v1.json"


def _region_registry() -> list[dict[str, object]]:
    return [
        {
            "region_id": region_id,
            "region_name": region_name,
            "geographic_stratum": stratum,
            "west": float(west),
            "south": float(south),
            "east": float(east),
            "north": float(north),
            "order": index,
        }
        for index, (region_id, region_name, stratum, west, south, east, north) in enumerate(VALIDATED_JAPAN_REGIONS)
    ]


def _inside_region(frame: pd.DataFrame, region: dict[str, object]) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    return frame.loc[
        frame["longitude"].between(float(region["west"]), float(region["east"]), inclusive="both")
        & frame["latitude"].between(float(region["south"]), float(region["north"]), inclusive="both")
    ].copy().reset_index(drop=True)


def _strict_exact(frame: pd.DataFrame, max_uncertainty_m: float) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    uncertainty = pd.to_numeric(frame["coordinate_uncertainty_m"], errors="coerce")
    return frame.loc[uncertainty.notna() & uncertainty.le(float(max_uncertainty_m))].copy().reset_index(drop=True)


def _hash_rows(frame: pd.DataFrame, columns: list[str]) -> str:
    digest = hashlib.sha256()
    if frame.empty:
        digest.update(b"EMPTY\n")
        return digest.hexdigest()
    work = frame[columns].copy()
    for column in columns:
        if column in {"latitude", "longitude", "coordinate_uncertainty_m"}:
            work[column] = pd.to_numeric(work[column], errors="coerce")
    sort_columns = [column for column in columns if column in work.columns]
    work = work.sort_values(sort_columns, kind="mergesort", na_position="last")
    for row in work.itertuples(index=False, name=None):
        values = []
        for value in row:
            if isinstance(value, float):
                values.append("NA" if pd.isna(value) else f"{value:.8f}")
            else:
                values.append(str(value))
        digest.update(("\t".join(values) + "\n").encode("utf-8"))
    return digest.hexdigest()


def _hash_candidate_ids(frame: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    for value in sorted(frame["candidate_cell_id"].astype(str).tolist()):
        digest.update((value + "\n").encode("utf-8"))
    return digest.hexdigest()


def _choose_training_region(
    strict_historical: pd.DataFrame,
    *,
    allowed_region_ids: list[str],
    cluster_radius_km: float,
) -> tuple[dict[str, object] | None, pd.DataFrame, list[dict[str, object]]]:
    registry = _region_registry()
    by_id = {str(row["region_id"]): row for row in registry}
    unknown = sorted(set(allowed_region_ids).difference(by_id))
    if unknown:
        raise ValueError(f"unknown fixed region IDs in contract: {unknown}")
    diagnostics: list[dict[str, object]] = []
    best_region = None
    best_frame = pd.DataFrame(columns=strict_historical.columns)
    best_count = -1
    for region in registry:
        region_id = str(region["region_id"])
        if region_id not in allowed_region_ids:
            continue
        subset = _inside_region(strict_historical, region)
        clusters = complete_link_clusters(subset, radius_km=float(cluster_radius_km))
        count = int(len(clusters))
        diagnostics.append(
            {
                "region_id": region_id,
                "strict_historical_records": int(len(subset)),
                "historical_population_clusters": count,
            }
        )
        # Strictly greater preserves VALIDATED_JAPAN_REGIONS order as tie-break.
        if count > best_count:
            best_count = count
            best_region = region
            best_frame = subset
    if best_region is None or best_count <= 0:
        return None, best_frame, diagnostics
    return best_region, best_frame, diagnostics


def _prepare_unit(unit: dict[str, object], contract: dict[str, object]) -> dict[str, object]:
    historical_cfg = contract["historical_evidence"]
    universe_cfg = contract["candidate_universes"]
    unit_id = str(unit["unit_id"])
    species = str(unit["species"])
    base: dict[str, object] = {
        "unit_id": unit_id,
        "species": species,
        "recent_outcomes_fetched": False,
        "region_selection_uses_recent_outcomes": False,
        "validated_product_changed": False,
    }
    try:
        historical, gbif_audit = fetch_gbif_occurrence_evidence(
            species,
            country=str(historical_cfg["country"]),
            year_from=int(historical_cfg["period"][0]),
            year_to=int(historical_cfg["period"][1]),
            maximum_records=10000,
        )
    except Exception as exc:
        return {
            **base,
            "status": "GBIF_HISTORICAL_PROVIDER_FAILURE",
            "failure": f"{type(exc).__name__}:{exc}",
        }

    strict = _strict_exact(historical, float(historical_cfg["coordinate_uncertainty_m_max"]))
    region, selected_historical, region_diagnostics = _choose_training_region(
        strict,
        allowed_region_ids=[str(value) for value in unit["allowed_fixed_regions"]],
        cluster_radius_km=0.5,
    )
    if region is None:
        return {
            **base,
            "status": "NO_HISTORICAL_ANCHOR",
            "gbif_historical_audit": gbif_audit.as_dict(),
            "strict_historical_records_countrywide": int(len(strict)),
            "allowed_region_training_diagnostics": region_diagnostics,
        }

    clusters = complete_link_clusters(selected_historical, radius_km=0.5)
    anchors = cluster_medoid_table(clusters, prefix=f"{unit_id}_H")
    bounds = (
        float(region["west"]),
        float(region["south"]),
        float(region["east"]),
        float(region["north"]),
    )
    broad_raw, broad_audit = build_rectangular_candidate_frame(
        bounds,
        grid_spacing_m=float(universe_cfg["grid_spacing_m"]),
        candidate_id_prefix=f"{unit_id}_{region['region_id']}_broad",
    )
    broad_raw = attach_nearest_anchor_distance(broad_raw, anchors)
    broad_raw = broad_raw.loc[
        pd.to_numeric(broad_raw["nearest_anchor_km"], errors="coerce").ge(float(universe_cfg["known_exclusion_km"]) - 1e-12)
    ].copy().reset_index(drop=True)

    try:
        broad_land, wc_audit = retain_worldcover_land_points(broad_raw)
    except Exception as exc:
        return {
            **base,
            "status": "WORLDCOVER_POINT_PROVIDER_FAILURE",
            "failure": f"{type(exc).__name__}:{exc}",
            "gbif_historical_audit": gbif_audit.as_dict(),
            "selected_region": {key: region[key] for key in ("region_id", "region_name", "west", "south", "east", "north")},
            "historical_population_count": int(len(anchors)),
            "broad_raw_candidate_count": int(len(broad_raw)),
        }

    nearest = pd.to_numeric(broad_land["nearest_anchor_km"], errors="coerce")
    lanes: dict[str, pd.DataFrame] = {"BROAD_LAND": broad_land}
    for radius in universe_cfg["local_outer_radii_km"]:
        label = f"LOCAL_{int(radius)}KM_LAND"
        lanes[label] = broad_land.loc[nearest.le(float(radius) + 1e-12)].copy().reset_index(drop=True)

    return {
        **base,
        "status": "PREOUTCOME_CANDIDATE_UNIVERSES_FROZEN",
        "gbif_historical_audit": gbif_audit.as_dict(),
        "strict_historical_records_countrywide": int(len(strict)),
        "allowed_region_training_diagnostics": region_diagnostics,
        "selected_region": {key: region[key] for key in ("region_id", "region_name", "geographic_stratum", "west", "south", "east", "north")},
        "selected_region_strict_historical_records": int(len(selected_historical)),
        "historical_population_count": int(len(anchors)),
        "historical_evidence_sha256": _hash_rows(
            selected_historical,
            ["occurrence_id", "latitude", "longitude", "event_year", "coordinate_uncertainty_m"],
        ),
        "population_anchor_sha256": _hash_rows(
            anchors,
            ["occurrence_id", "latitude", "longitude", "cluster_size"],
        ),
        "broad_frame_audit": asdict(broad_audit),
        "worldcover_point_audit": wc_audit.as_dict(),
        "candidate_universes": {
            name: {
                "candidate_count": int(len(frame)),
                "candidate_id_sha256": _hash_candidate_ids(frame),
            }
            for name, frame in lanes.items()
        },
    }


def run() -> dict[str, object]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if contract.get("status") != "FROZEN_BEFORE_2021_2025_OUTCOME_FETCH":
        raise ValueError("disjoint broad-frame replication contract is not in the pre-outcome frozen state")
    if not bool(contract.get("cohort_selection", {}).get("selected_before_recent_outcome_fetch")):
        raise ValueError("cohort is not declared pre-outcome")
    units = contract["cohort_selection"]["units"]
    results = [_prepare_unit(unit, contract) for unit in units]
    return {
        "schema_version": "cirsium-disjoint-broad-frame-replication-preflight-result-v1",
        "status": "HISTORICAL_ONLY_PREFLIGHT_COMPLETE",
        "source_contract": str(CONTRACT.relative_to(ROOT)),
        "recent_outcomes_fetched": False,
        "validated_product_changed": False,
        "unit_count": int(len(results)),
        "units_frozen": int(sum(row.get("status") == "PREOUTCOME_CANDIDATE_UNIVERSES_FROZEN" for row in results)),
        "units_no_historical_anchor": int(sum(row.get("status") == "NO_HISTORICAL_ANCHOR" for row in results)),
        "units_provider_failure": int(sum(str(row.get("status", "")).endswith("PROVIDER_FAILURE") for row in results)),
        "units": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = run()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
