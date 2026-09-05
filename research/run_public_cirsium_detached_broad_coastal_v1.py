#!/usr/bin/env python3
"""Run frozen DETACHED_BROAD coastal development on opened CIR08 public data.

This is retrospective development only. Candidate frames and all selector orders
are constructed from 2000-2020 evidence plus public WorldCover before 2021-2025
novel populations are scored.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
import sys
from pathlib import Path

import pandas as pd
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

from acsp.discovery import (
    AnnularFrameSpec,
    DiscoveryContext,
    assess_occurrence_evidence,
    attach_nearest_anchor_distance,
    build_annular_candidate_frame,
    build_rectangular_candidate_frame,
    build_structural_support_order,
    cluster_min_distance_km,
    complete_link_clusters,
    haversine_km,
    partition_local_and_detached,
    rank_morton_dyadic_spatial_balance,
    rank_nearest_anchor,
)
from acsp.discovery.providers.coastal_worldcover import attach_worldcover_coastal_features
from acsp.discovery.providers.worldcover import build_worldcover_2021_map_crop
from acsp.discovery.providers.worldcover_land import retain_worldcover_land_candidates
from benchmark_public_japan_cirsium_temporal_anchor_v1 import fetch_gbif_species

CONTRACT = ROOT / "validation" / "public_cirsium_detached_broad_coastal_development_v1.json"
PRIOR_LOCAL_RESULT = ROOT / "validation" / "public_cirsium_portable_coastal_smoke_result_v1.json"
UNIT_ID = "CIR08"
SPECIES = "Cirsium brevicaule"
FAMILY = "COASTAL_ISLAND_STRUCTURE"


def _inside(frame: pd.DataFrame, bounds: tuple[float, float, float, float]) -> pd.DataFrame:
    west, south, east, north = bounds
    return frame.loc[
        frame["longitude"].between(west, east)
        & frame["latitude"].between(south, north)
    ].copy().reset_index(drop=True)


def _occurrence_schema(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["occurrence_id", "latitude", "longitude", "event_year", "coordinate_uncertainty_m", "provider_id"])
    return pd.DataFrame(
        {
            "occurrence_id": frame["gbif_key"].astype(str),
            "latitude": frame["latitude"].astype(float),
            "longitude": frame["longitude"].astype(float),
            "event_year": frame["year"].astype(int),
            "coordinate_uncertainty_m": frame["coordinate_uncertainty_m"].astype(float),
            "provider_id": "GBIF",
        }
    )


def _novel_recent_clusters(historical: pd.DataFrame, recent: pd.DataFrame):
    old = complete_link_clusters(historical, radius_km=0.5)
    new = complete_link_clusters(recent, radius_km=0.5)
    novel = []
    for cluster in new:
        if not old or min(cluster_min_distance_km(cluster, prior) for prior in old) > 0.5 + 1e-12:
            novel.append(cluster)
    return novel


def _cluster_hit(selected: pd.DataFrame, cluster, radius_km: float) -> bool:
    if selected.empty:
        return False
    points = list(zip(selected["latitude"].astype(float), selected["longitude"].astype(float)))
    return any(
        haversine_km(lat, lon, member_lat, member_lon) <= float(radius_km) + 1e-12
        for lat, lon in points
        for member_lat, member_lon, _ in cluster.members
    )


def _recall(selected: pd.DataFrame, clusters, radius_km: float) -> float:
    if not clusters:
        return 0.0
    return float(sum(_cluster_hit(selected, cluster, radius_km) for cluster in clusters) / len(clusters))


def _subset_structural_order(structural_full: pd.DataFrame, detached: pd.DataFrame) -> pd.DataFrame:
    ids = set(detached["candidate_cell_id"].astype(str))
    out = structural_full.loc[structural_full["candidate_cell_id"].astype(str).isin(ids)].copy()
    out = out.sort_values(["structural_support", "candidate_cell_id"], ascending=[False, True], kind="mergesort").reset_index(drop=True)
    out["decision_method"] = "STRUCTURAL_SUPPORT"
    out["decision_rank"] = range(1, len(out) + 1)
    if len(out) != len(detached):
        raise AssertionError("detached structural order does not cover exact detached candidate frame")
    return out


def run(out_dir: Path) -> tuple[pd.DataFrame, dict]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    prior = json.loads(PRIOR_LOCAL_RESULT.read_text(encoding="utf-8"))
    if contract.get("status") != "DEVELOPMENT_ONLY_FROZEN_BEFORE_DETACHED_BROAD_EXECUTION":
        raise ValueError("DETACHED_BROAD contract is not frozen")
    if contract.get("species") != SPECIES or contract.get("feature_family") != FAMILY:
        raise ValueError("DETACHED_BROAD identity/family mismatch")
    if prior.get("novel_recent_population_clusters") != 15:
        raise ValueError("prior CIR08 local result no longer matches frozen 15-population denominator")
    if prior.get("full_frame_ceiling", {}).get("5_km", {}).get("recovered_novel_clusters_at_1km") != 1:
        raise ValueError("prior 5-km LOCAL ceiling no longer matches frozen result")

    declared = contract["declared_broad_frame"]
    bounds = tuple(float(declared[key]) for key in ("west", "south", "east", "north"))
    clip = box(*bounds)
    records, fetch_audit = fetch_gbif_species(SPECIES, maximum_records=10000, pause_seconds=0.02)
    records = _inside(records, bounds)
    historical_raw = records.loc[records["year"].between(2000, 2020)].copy().reset_index(drop=True)
    recent_raw = records.loc[records["year"].between(2021, 2025)].copy().reset_index(drop=True)
    historical = _occurrence_schema(historical_raw)
    recent = _occurrence_schema(recent_raw)
    if historical.empty:
        raise RuntimeError("NO_STRICT_HISTORICAL_ANCHOR")

    detached_assessment, anchors = assess_occurrence_evidence(
        historical,
        context=DiscoveryContext(detached_component_available=True),
    )
    if detached_assessment.population_anchor_count < 1:
        raise RuntimeError("NO_STRICT_HISTORICAL_ANCHOR")

    frame_cfg = contract["candidate_frame"]
    broad_raw, broad_audit = build_rectangular_candidate_frame(
        bounds,
        grid_spacing_m=float(frame_cfg["grid_spacing_m"]),
        candidate_id_prefix=f"{UNIT_ID}_broad",
    )
    broad_raw = attach_nearest_anchor_distance(broad_raw, anchors)

    out_dir.mkdir(parents=True, exist_ok=True)
    wc_path = out_dir / "private_worldcover_crop.tif"
    wc_cfg = contract["worldcover"]
    wc_audit = build_worldcover_2021_map_crop(bounds, wc_path, margin_m=float(wc_cfg["crop_margin_m"]))
    broad_land, coastal_audit = attach_worldcover_coastal_features(
        broad_raw,
        anchors,
        wc_path,
        neighbourhood_half_width_m=float(wc_cfg["neighbourhood_half_width_m"]),
    )
    partitioned, partition_audit = partition_local_and_detached(
        broad_land,
        local_boundary_km=float(frame_cfg["local_boundary_km"]),
        target_component_id=coastal_audit.target_component_id,
    )
    detached = partitioned.loc[partitioned["discovery_lane"].astype(str).str.startswith("DETACHED")].copy().reset_index(drop=True)
    if detached.empty:
        raise RuntimeError("DETACHED_BROAD frame is empty")

    provenance = {
        "contract": contract["schema_version"],
        "provider": wc_audit.provider_id,
        "release": wc_audit.release_id,
        "worldcover_crop_sha256": wc_audit.output_sha256,
        "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "broad_frame": declared,
    }
    structural_full, structural_audit = build_structural_support_order(
        partitioned,
        feature_family=FAMILY,
        source_provenance=provenance,
        target_component_id=coastal_audit.target_component_id,
        graph_radius_cells=1,
    )
    structural_detached = _subset_structural_order(structural_full, detached)
    nearest_detached = rank_nearest_anchor(detached)
    spatial_detached, spatial_audit = rank_morton_dyadic_spatial_balance(detached)
    methods = {
        "STRUCTURAL_SUPPORT": structural_detached,
        "ANNULAR_NEAREST_KNOWN": nearest_detached,
        "DETERMINISTIC_SPATIAL_BALANCE": spatial_detached,
    }
    if len({len(frame) for frame in methods.values()}) != 1:
        raise AssertionError("detached methods do not rank identical candidate counts")

    # Reconstruct the previously frozen 5-km LOCAL frame before outcomes are opened.
    local_raw, local_build_audit = build_annular_candidate_frame(
        anchors,
        spec=AnnularFrameSpec(grid_spacing_m=100.0, known_exclusion_km=0.5, outer_radius_km=5.0),
        candidate_id_prefix=f"{UNIT_ID}_local5000",
        clip_geometry_wgs84=clip,
    )
    local_land, local_land_audit = retain_worldcover_land_candidates(local_raw, wc_path)

    # Outcome scoring begins here, after every candidate frame and selector order is frozen.
    novel = _novel_recent_clusters(historical, recent) if not recent.empty else []
    if len(novel) != int(prior["novel_recent_population_clusters"]):
        raise RuntimeError(f"novel population denominator drifted: current={len(novel)} prior={prior['novel_recent_population_clusters']}")

    radii = [float(value) for value in contract["outcome"]["recovery_radii_km"]]
    fractions = [float(value) for value in contract["ranking"]["prefix_fractions"]]
    reachability = {}
    local_unreached_by_radius = {}
    for radius in radii:
        local_hits = [_cluster_hit(local_land, cluster, radius) for cluster in novel]
        broad_hits = [_cluster_hit(broad_land, cluster, radius) for cluster in novel]
        detached_hits = [_cluster_hit(detached, cluster, radius) for cluster in novel]
        local_unreached_by_radius[radius] = [cluster for cluster, hit in zip(novel, local_hits) if not hit]
        reachability[str(radius)] = {
            "novel_population_count": int(len(novel)),
            "local_5km_100m_recovered": int(sum(local_hits)),
            "broad_land_250m_recovered": int(sum(broad_hits)),
            "detached_broad_250m_recovered": int(sum(detached_hits)),
            "local_unreached_count": int(len(novel) - sum(local_hits)),
        }

    rows: list[dict] = []
    count = len(detached)
    for fraction in fractions:
        k = max(1, min(count, int(math.ceil(float(fraction) * count))))
        selected = {method: frame.head(k) for method, frame in methods.items()}
        for radius in radii:
            unreached = local_unreached_by_radius[radius]
            rows.append(
                {
                    "cohort_unit_id": UNIT_ID,
                    "species": SPECIES,
                    "family": FAMILY,
                    "prefix_fraction": float(fraction),
                    "selected_count": int(k),
                    "recovery_radius_km": float(radius),
                    "novel_population_count": int(len(novel)),
                    "local_unreached_population_count": int(len(unreached)),
                    "structural_recall_all": _recall(selected["STRUCTURAL_SUPPORT"], novel, radius),
                    "nearest_recall_all": _recall(selected["ANNULAR_NEAREST_KNOWN"], novel, radius),
                    "spatial_recall_all": _recall(selected["DETERMINISTIC_SPATIAL_BALANCE"], novel, radius),
                    "structural_recall_local_unreached": _recall(selected["STRUCTURAL_SUPPORT"], unreached, radius),
                    "nearest_recall_local_unreached": _recall(selected["ANNULAR_NEAREST_KNOWN"], unreached, radius),
                    "spatial_recall_local_unreached": _recall(selected["DETERMINISTIC_SPATIAL_BALANCE"], unreached, radius),
                }
            )
    table = pd.DataFrame(rows)
    summary = {
        "schema_version": "public-cirsium-detached-broad-coastal-result-v1",
        "status": "DEVELOPMENT_ONLY_DETACHED_BROAD_COMPLETE",
        "source_contract": str(CONTRACT.relative_to(ROOT)),
        "cohort_unit_id": UNIT_ID,
        "species": SPECIES,
        "family": FAMILY,
        "validated_product_changed": False,
        "new_confirmation_claim": False,
        "retuning_used": False,
        "fetch_audit": fetch_audit,
        "historical_records_in_declared_frame": int(len(historical)),
        "historical_population_anchors": int(detached_assessment.population_anchor_count),
        "recent_records_in_declared_frame": int(len(recent)),
        "novel_recent_population_clusters": int(len(novel)),
        "broad_frame_audit": asdict(broad_audit),
        "worldcover_audit": asdict(wc_audit),
        "coastal_feature_audit": asdict(coastal_audit),
        "detached_partition_audit": asdict(partition_audit),
        "detached_candidate_count": int(len(detached)),
        "detached_same_component_count": int((detached["discovery_lane"] == "DETACHED_SAME_COMPONENT").sum()),
        "detached_other_component_count": int((detached["discovery_lane"] == "DETACHED_OTHER_COMPONENT").sum()),
        "local_reconstruction": {
            "frame_build_audit": asdict(local_build_audit),
            "land_mask_audit": asdict(local_land_audit),
            "prior_frozen_1km_recovered": int(prior["full_frame_ceiling"]["5_km"]["recovered_novel_clusters_at_1km"]),
        },
        "reachability": reachability,
        "structural_audit": asdict(structural_audit),
        "spatial_audit": asdict(spatial_audit),
        "prefix_fractions": fractions,
        "recovery_radii_km": radii,
        "interpretation_boundary": "Opened CIR08 development only. Broad-frame reachability is the primary diagnostic. Selector cells are secondary and cannot be promoted or retuned on this unit."
    }
    return table, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    table, summary = run(args.out_dir)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.out_dir / "detached_broad_prefix_curve.csv", index=False)
    (args.out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    private_crop = args.out_dir / "private_worldcover_crop.tif"
    if private_crop.exists():
        private_crop.unlink()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
