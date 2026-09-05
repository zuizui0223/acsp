#!/usr/bin/env python3
"""Run the frozen public CIR01 / Cirsium sieboldii wetland structural smoke.

Development only. The Shikoku geographic frame is reused from the pre-existing
validated Japan regional rectangles. Historical 2000-2020 strict public records
are clustered before candidate generation; 2021-2025 records are used only for
later novel-cluster scoring after structural/nearest/spatial full orders exist.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

from acsp.discovery import (
    AnnularFrameSpec,
    build_annular_candidate_frame,
    build_structural_support_order,
    cluster_medoid_table,
    cluster_min_distance_km,
    complete_link_clusters,
    rank_morton_dyadic_spatial_balance,
    rank_nearest_anchor,
)
from acsp.discovery.providers import build_worldcover_2021_map_crop
from benchmark_public_japan_cirsium_temporal_anchor_v1 import fetch_gbif_species
from build_cirsium_private_alpine_local_grid_v1 import _sample_terrain
from campanula_worldcover_discovery import neighborhood_features
from gbif_fieldmap_builder_app import build_gsi_dem_for_bounds

CONTRACT = ROOT / "validation" / "public_cirsium_structural_three_family_smoke_v1.json"
AMENDMENT = ROOT / "validation" / "public_cirsium_wetland_shikoku_structural_smoke_amendment_v1.json"
SPATIAL_AMENDMENT = ROOT / "validation" / "public_cirsium_structural_three_family_spatial_comparator_amendment_v1.json"
UNIT_ID = "CIR01"
SPECIES = "Cirsium sieboldii"
FAMILY = "WETLAND_MOISTURE_STRUCTURE"


def strict_period(records: pd.DataFrame, start: int, end: int) -> pd.DataFrame:
    out = records.loc[records["year"].between(int(start), int(end))].copy()
    if out.empty:
        return out
    return (
        out.sort_values(["latitude", "longitude", "year", "gbif_key"], kind="mergesort")
        .drop_duplicates(["latitude", "longitude", "year"], keep="first")
        .reset_index(drop=True)
    )


def clip_records(records: pd.DataFrame, bounds: tuple[float, float, float, float]) -> pd.DataFrame:
    west, south, east, north = map(float, bounds)
    return records.loc[
        records["longitude"].between(west, east)
        & records["latitude"].between(south, north)
    ].copy().reset_index(drop=True)


def occurrence_clusters(records: pd.DataFrame):
    if records.empty:
        return []
    evidence = records[["gbif_key", "latitude", "longitude"]].rename(columns={"gbif_key": "occurrence_id"})
    return complete_link_clusters(evidence, radius_km=0.5)


def novel_recent_clusters(historical_clusters, recent_clusters):
    if not historical_clusters:
        return []
    result = []
    for recent in recent_clusters:
        nearest = min(cluster_min_distance_km(recent, historical) for historical in historical_clusters)
        if nearest > 0.5 + 1e-12:
            result.append(recent)
    return result


def grid_components(frame: pd.DataFrame) -> list[pd.DataFrame]:
    """Split a regular candidate grid into Moore-connected provider chunks."""
    if frame.empty:
        return []
    lookup = {
        (int(row.grid_row), int(row.grid_col)): int(index)
        for index, row in frame.reset_index(drop=True).iterrows()
    }
    visited: set[int] = set()
    groups: list[list[int]] = []
    for start in range(len(frame)):
        if start in visited:
            continue
        queue = [start]
        visited.add(start)
        group: list[int] = []
        while queue:
            index = queue.pop()
            group.append(index)
            row = frame.iloc[index]
            rr, cc = int(row.grid_row), int(row.grid_col)
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    neighbor = lookup.get((rr + dr, cc + dc))
                    if neighbor is not None and neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
        groups.append(group)
    return [frame.iloc[group].copy().reset_index(drop=True) for group in groups]


def attach_public_layers(
    frame: pd.DataFrame,
    *,
    outer_km: float,
    work_dir: Path,
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    pieces: list[pd.DataFrame] = []
    audits: list[dict[str, object]] = []
    components = grid_components(frame)
    for component_index, component in enumerate(components):
        bounds = (
            float(component["longitude"].min()),
            float(component["latitude"].min()),
            float(component["longitude"].max()),
            float(component["latitude"].max()),
        )
        references = tuple(
            (float(row.latitude), float(row.longitude))
            for row in component.iloc[:: max(1, len(component) // 8)].head(8).itertuples(index=False)
        )
        dem_path, attribution = build_gsi_dem_for_bounds(bounds, references, max_tiles=400)
        if not dem_path:
            raise RuntimeError(f"GSI DEM unavailable for component {component_index}")
        terrain = _sample_terrain(component, Path(dem_path))
        if terrain.empty:
            raise RuntimeError(f"GSI terrain empty for component {component_index}")

        wc_path = work_dir / f"worldcover_{int(round(outer_km * 1000)):04d}_{component_index:03d}.tif"
        wc_audit = build_worldcover_2021_map_crop(bounds, wc_path, margin_m=500.0)
        with rasterio.open(wc_path) as src:
            cover = neighborhood_features(
                src,
                terrain["longitude"].to_numpy(float),
                terrain["latitude"].to_numpy(float),
                radii_m=(250,),
            )
        needed = [
            "wc_water_frac_250m",
            "wc_wetland_frac_250m",
        ]
        if cover[needed].isna().any().any():
            raise RuntimeError(f"WorldCover neighborhoods incomplete for component {component_index}")
        combined = pd.concat([terrain.reset_index(drop=True), cover.reset_index(drop=True)], axis=1)
        combined["provider_component_id"] = int(component_index)
        pieces.append(combined)
        audits.append(
            {
                "component_id": int(component_index),
                "candidate_rows_requested": int(len(component)),
                "candidate_rows_complete": int(len(combined)),
                "gsi_attribution": str(attribution),
                "worldcover_tile_ids": list(wc_audit.source_tile_ids),
                "worldcover_crop_sha256": wc_audit.output_sha256,
                "worldcover_crop_bytes": wc_audit.output_bytes,
            }
        )
    merged = pd.concat(pieces, ignore_index=True)
    if merged["candidate_cell_id"].duplicated().any():
        raise RuntimeError("provider chunk assembly duplicated candidate cells")
    return merged, audits


def recovery_fraction(selected: pd.DataFrame, clusters, radius_km: float) -> float:
    if selected.empty or not clusters:
        return 0.0
    from acsp.discovery import haversine_km

    points = list(zip(selected["latitude"].astype(float), selected["longitude"].astype(float)))
    recovered = 0
    for cluster in clusters:
        recovered += int(
            any(
                haversine_km(lat, lon, member_lat, member_lon) <= float(radius_km) + 1e-12
                for lat, lon in points
                for member_lat, member_lon, _ in cluster.members
            )
        )
    return float(recovered / len(clusters))


def run(work_dir: Path) -> tuple[pd.DataFrame, dict[str, object]]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    amendment = json.loads(AMENDMENT.read_text(encoding="utf-8"))
    spatial = json.loads(SPATIAL_AMENDMENT.read_text(encoding="utf-8"))
    if contract["status"] != "DEVELOPMENT_ONLY_FROZEN_BEFORE_STRUCTURAL_LAYER_EXECUTION":
        raise ValueError("three-family smoke contract is not frozen")
    if amendment["status"] != "PRE_STRUCTURAL_OUTCOME_PUBLIC_SLOT_GEOMETRY_FROZEN":
        raise ValueError("CIR01 Shikoku amendment is not frozen")
    if spatial["status"] != "PRE_STRUCTURAL_OUTCOME_COMPARATOR_IDENTITY_FROZEN":
        raise ValueError("spatial comparator amendment is not frozen")
    unit = next(row for row in contract["units"] if row["cohort_unit_id"] == UNIT_ID)
    if unit["species"] != SPECIES or unit["family"] != FAMILY:
        raise ValueError("CIR01 identity/family mismatch")

    slot = amendment["slot_geometry"]
    bounds = tuple(float(slot[key]) for key in ("west", "south", "east", "north"))
    region_shape = box(*bounds)
    records, fetch_audit = fetch_gbif_species(SPECIES, maximum_records=10000, pause_seconds=0.02)
    records = clip_records(records, bounds)
    historical = strict_period(records, 2000, 2020)
    recent = strict_period(records, 2021, 2025)
    historical_clusters = occurrence_clusters(historical)
    recent_clusters = occurrence_clusters(recent)
    novel = novel_recent_clusters(historical_clusters, recent_clusters)
    if not historical_clusters:
        return pd.DataFrame(), {
            "schema_version": "public-cirsium-wetland-structural-smoke-result-v1",
            "status": "BLOCKED_NO_STRICT_HISTORICAL_ANCHOR",
            "cohort_unit_id": UNIT_ID,
            "species": SPECIES,
            "family": FAMILY,
            "validated_product_changed": False,
            "new_confirmation_claim": False,
            "structural_layer_run": False,
            "replacement_or_precision_relaxation_used": False,
            "fetch_audit": fetch_audit,
        }
    anchors = cluster_medoid_table(historical_clusters).rename(columns={"occurrence_id": "gbif_key"})

    prefix_fractions = [float(value) for value in contract["prefix_curve"]["fractions"]]
    recovery_radii = [float(value) for value in contract["outcome"]["recovery_radii_km"]]
    outer_frames = [
        float(contract["candidate_frames"]["primary_outer_radius_km"]),
        float(contract["candidate_frames"]["sensitivity_outer_radius_km"]),
    ]
    results: list[dict[str, object]] = []
    frame_audits: list[dict[str, object]] = []
    work_dir.mkdir(parents=True, exist_ok=True)

    for outer_km in outer_frames:
        frame, frame_audit = build_annular_candidate_frame(
            anchors,
            spec=AnnularFrameSpec(
                grid_spacing_m=float(contract["candidate_frames"]["grid_spacing_m"]),
                known_exclusion_km=float(contract["historical_evidence"]["known_point_exclusion_km"]),
                outer_radius_km=outer_km,
            ),
            candidate_id_prefix=f"{UNIT_ID}_{int(round(outer_km * 1000)):04d}",
            clip_geometry_wgs84=region_shape,
        )
        raw, provider_audits = attach_public_layers(frame, outer_km=outer_km, work_dir=work_dir)
        structural, structural_audit = build_structural_support_order(
            raw,
            feature_family=FAMILY,
            source_provenance={
                "slot": "validated-japan-shikoku",
                "gsi": "public GSI DEM",
                "worldcover": "ESA WorldCover 2021 v200 Map",
                "provider_components": provider_audits,
            },
        )
        nearest = rank_nearest_anchor(raw)
        balanced, balanced_audit = rank_morton_dyadic_spatial_balance(raw)
        frame_audits.append(
            {
                "outer_km": outer_km,
                "frame_candidate_rows": int(frame_audit.candidate_count),
                "provider_complete_rows": int(len(raw)),
                "provider_component_count": int(len(provider_audits)),
                "structural_support_provenance_id": structural_audit.support_provenance_id,
                "spatial_comparator": balanced_audit.method,
                "provider_components": provider_audits,
            }
        )
        for fraction in prefix_fractions:
            k = max(1, min(len(raw), int(math.ceil(float(fraction) * len(raw)))))
            for radius in recovery_radii:
                results.append(
                    {
                        "cohort_unit_id": UNIT_ID,
                        "species": SPECIES,
                        "family": FAMILY,
                        "outer_frame_km": outer_km,
                        "prefix_fraction": fraction,
                        "selected_count": k,
                        "recovery_radius_km": radius,
                        "novel_recent_clusters": int(len(novel)),
                        "structural_recall": recovery_fraction(structural.head(k), novel, radius),
                        "nearest_recall": recovery_fraction(nearest.head(k), novel, radius),
                        "spatial_balance_recall": recovery_fraction(balanced.head(k), novel, radius),
                    }
                )

    table = pd.DataFrame(results)
    summary = {
        "schema_version": "public-cirsium-wetland-structural-smoke-result-v1",
        "status": "DEVELOPMENT_ONLY_WETLAND_SMOKE_COMPLETE",
        "cohort_unit_id": UNIT_ID,
        "species": SPECIES,
        "family": FAMILY,
        "validated_product_changed": False,
        "new_confirmation_claim": False,
        "strict_records_in_shikoku": int(len(records)),
        "strict_historical_rows": int(len(historical)),
        "strict_recent_rows": int(len(recent)),
        "historical_population_clusters": int(len(historical_clusters)),
        "recent_population_clusters": int(len(recent_clusters)),
        "novel_recent_clusters": int(len(novel)),
        "fetch_audit": fetch_audit,
        "frame_audits": frame_audits,
        "reported_outer_frames_km": outer_frames,
        "reported_prefix_fractions": prefix_fractions,
        "reported_recovery_radii_km": recovery_radii,
        "structural_exceeds_nearest_any_cell": bool((table["structural_recall"] > table["nearest_recall"]).any()),
        "nearest_exceeds_structural_any_cell": bool((table["nearest_recall"] > table["structural_recall"]).any()),
        "structural_exceeds_spatial_any_cell": bool((table["structural_recall"] > table["spatial_balance_recall"]).any()),
        "interpretation_boundary": "Opened public Cirsium development smoke only. All frozen 2/5-km frames, seven prefixes and three recovery radii are reported jointly; no favorable cell is a promoted method.",
    }
    return table, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    work_dir = args.out_dir / "provider-cache"
    table, summary = run(work_dir)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    if table.empty:
        pd.DataFrame(columns=[
            "cohort_unit_id", "species", "family", "outer_frame_km", "prefix_fraction",
            "selected_count", "recovery_radius_km", "novel_recent_clusters",
            "structural_recall", "nearest_recall", "spatial_balance_recall",
        ]).to_csv(args.out_dir / "wetland_prefix_curve.csv", index=False)
    else:
        table.to_csv(args.out_dir / "wetland_prefix_curve.csv", index=False)
    (args.out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
