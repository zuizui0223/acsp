#!/usr/bin/env python3
"""Diagnose CIR08 LOCAL versus DETACHED candidate-universe reachability.

Development-only, post-opened diagnostic. The candidate lanes are constructed
from strict historical occurrence evidence, the pre-existing Okinawa-main outer
frame and ESA WorldCover land components before 2021-2025 novel populations are
scored. No ranking, fitted threshold, route/access layer or method nomination is
performed here.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

from acsp.discovery import (
    DiscoveryContext,
    assess_occurrence_evidence,
    attach_nearest_anchor_distance,
    build_rectangular_candidate_frame,
    cluster_min_distance_km,
    complete_link_clusters,
    partition_candidate_components,
)
from acsp.discovery.providers import (
    attach_worldcover_component_ids,
    build_worldcover_2021_map_crop,
)
from benchmark_public_japan_cirsium_temporal_anchor_v1 import fetch_gbif_species

CONTRACT = ROOT / "validation" / "public_cirsium_portable_detached_component_diagnostic_v1.json"
UNIT_ID = "CIR08"
SPECIES = "Cirsium brevicaule"


def _inside(frame: pd.DataFrame, bounds: tuple[float, float, float, float]) -> pd.DataFrame:
    west, south, east, north = bounds
    return frame.loc[
        frame["longitude"].between(west, east)
        & frame["latitude"].between(south, north)
    ].copy().reset_index(drop=True)


def _occurrence_schema(frame: pd.DataFrame) -> pd.DataFrame:
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
    historical_clusters = complete_link_clusters(historical, radius_km=0.5)
    recent_clusters = complete_link_clusters(recent, radius_km=0.5)
    novel = []
    for cluster in recent_clusters:
        if not historical_clusters or min(
            cluster_min_distance_km(cluster, prior) for prior in historical_clusters
        ) > 0.5 + 1e-12:
            novel.append(cluster)
    return novel


def _nearest_cluster_distances_km(
    candidate_frame: pd.DataFrame,
    clusters,
    *,
    metric_crs: str,
) -> list[float]:
    if not clusters:
        return []
    if candidate_frame.empty:
        return [float("inf")] * len(clusters)
    transformer = Transformer.from_crs("EPSG:4326", metric_crs, always_xy=True)
    cx, cy = transformer.transform(
        candidate_frame["longitude"].to_numpy(float),
        candidate_frame["latitude"].to_numpy(float),
    )
    tree = cKDTree(np.column_stack([cx, cy]))
    distances: list[float] = []
    for cluster in clusters:
        lon = np.asarray([member[1] for member in cluster.members], dtype=float)
        lat = np.asarray([member[0] for member in cluster.members], dtype=float)
        x, y = transformer.transform(lon, lat)
        value, _ = tree.query(np.column_stack([x, y]), k=1)
        distances.append(float(np.min(np.asarray(value, dtype=float))) / 1000.0)
    return distances


def _lane_rows(
    lane_id: str,
    frame: pd.DataFrame,
    clusters,
    *,
    metric_crs: str,
    radii_km: list[float],
) -> list[dict[str, object]]:
    nearest = _nearest_cluster_distances_km(frame, clusters, metric_crs=metric_crs)
    finite = np.asarray([value for value in nearest if math.isfinite(value)], dtype=float)
    median = None if finite.size == 0 else float(np.median(finite))
    maximum = None if finite.size == 0 else float(np.max(finite))
    rows = []
    for radius in radii_km:
        recovered = int(sum(value <= radius + 1e-12 for value in nearest))
        total = int(len(clusters))
        rows.append(
            {
                "cohort_unit_id": UNIT_ID,
                "species": SPECIES,
                "lane_id": lane_id,
                "candidate_count": int(len(frame)),
                "recovery_radius_km": float(radius),
                "novel_recent_clusters": total,
                "recovered_clusters": recovered,
                "recall": 0.0 if total == 0 else float(recovered / total),
                "median_nearest_candidate_km": median,
                "maximum_nearest_candidate_km": maximum,
            }
        )
    return rows


def _blocked(status: str, *, fetch_audit: dict[str, object], detail: str = ""):
    return pd.DataFrame(), {
        "schema_version": "public-cirsium-portable-detached-component-result-v1",
        "status": status,
        "cohort_unit_id": UNIT_ID,
        "species": SPECIES,
        "validated_product_changed": False,
        "new_confirmation_claim": False,
        "candidate_lanes_frozen_before_recent_scoring": False,
        "replacement_or_precision_relaxation_used": False,
        "fetch_audit": fetch_audit,
        "detail": detail,
    }


def run(out_dir: Path) -> tuple[pd.DataFrame, dict[str, object]]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if contract.get("status") != "DEVELOPMENT_ONLY_POST_OPENED_DIAGNOSTIC_FROZEN_BEFORE_COMPONENT_SCORING":
        raise ValueError("detached-component diagnostic contract is not frozen")
    if contract.get("cohort_unit_id") != UNIT_ID or contract.get("species") != SPECIES:
        raise ValueError("detached-component identity mismatch")

    declared = contract["declared_outer_frame"]
    bounds = tuple(float(declared[key]) for key in ("west", "south", "east", "north"))
    records, fetch_audit = fetch_gbif_species(SPECIES, maximum_records=10000, pause_seconds=0.02)
    records = _inside(records, bounds)
    historical_raw = records.loc[records["year"].between(2000, 2020)].copy().reset_index(drop=True)
    if historical_raw.empty:
        return _blocked("NO_STRICT_HISTORICAL_ANCHOR", fetch_audit=fetch_audit)
    historical = _occurrence_schema(historical_raw)
    assessment, anchors = assess_occurrence_evidence(
        historical,
        context=DiscoveryContext(),
    )
    if anchors.empty:
        return _blocked("NO_STRICT_HISTORICAL_ANCHOR", fetch_audit=fetch_audit)

    frame_cfg = contract["broad_candidate_frame"]
    broad, broad_audit = build_rectangular_candidate_frame(
        bounds,
        grid_spacing_m=float(frame_cfg["grid_spacing_m"]),
        candidate_id_prefix=f"{UNIT_ID}_broad",
    )
    broad = attach_nearest_anchor_distance(broad, anchors)
    broad = broad.loc[
        broad["nearest_anchor_km"].ge(float(frame_cfg["known_exclusion_km"]) - 1e-12)
    ].copy().reset_index(drop=True)

    out_dir.mkdir(parents=True, exist_ok=True)
    worldcover_path = out_dir / "private_worldcover_component_crop.tif"
    try:
        wc_audit = build_worldcover_2021_map_crop(
            bounds,
            worldcover_path,
            margin_m=float(contract["worldcover_component_map"]["crop_margin_m"]),
        )
        land, component_audit = attach_worldcover_component_ids(
            broad,
            anchors,
            worldcover_path,
        )
    except Exception as exc:
        return _blocked(
            "WORLDCOVER_COMPONENT_PROVIDER_FAILURE",
            fetch_audit=fetch_audit,
            detail=f"{type(exc).__name__}:{exc}",
        )

    anchored_component_frame, other_component_frame, partition_audit = partition_candidate_components(
        land,
        anchored_component_ids=component_audit.anchored_component_ids,
    )
    distance = pd.to_numeric(land["nearest_anchor_km"], errors="coerce")
    local_2 = land.loc[distance.le(2.0 + 1e-12)].copy().reset_index(drop=True)
    local_5 = land.loc[distance.le(5.0 + 1e-12)].copy().reset_index(drop=True)
    anchored_distance = pd.to_numeric(anchored_component_frame["nearest_anchor_km"], errors="coerce")
    other_distance = pd.to_numeric(other_component_frame["nearest_anchor_km"], errors="coerce")
    detached_same = anchored_component_frame.loc[anchored_distance.gt(5.0 + 1e-12)].copy().reset_index(drop=True)
    detached_other = other_component_frame.loc[other_distance.gt(5.0 + 1e-12)].copy().reset_index(drop=True)

    # Candidate lanes are now frozen. Only after this point are recent records
    # converted to outcome clusters for the already-opened retrospective diagnostic.
    recent_raw = records.loc[records["year"].between(2021, 2025)].copy().reset_index(drop=True)
    recent = _occurrence_schema(recent_raw)
    novel = _novel_recent_clusters(historical, recent) if not recent.empty else []
    radii = [float(value) for value in contract["outcome"]["recovery_radii_km"]]
    lanes = {
        "LOCAL_2KM": local_2,
        "LOCAL_5KM": local_5,
        "DETACHED_SAME_COMPONENT": detached_same,
        "DETACHED_OTHER_COMPONENT": detached_other,
        "ANCHORED_COMPONENT_FULL": anchored_component_frame,
        "OTHER_COMPONENTS_FULL": other_component_frame,
        "BROAD_LAND_UNION": land,
    }
    rows: list[dict[str, object]] = []
    for lane_id, frame in lanes.items():
        rows.extend(
            _lane_rows(
                lane_id,
                frame,
                novel,
                metric_crs=broad_audit.metric_crs,
                radii_km=radii,
            )
        )
    table = pd.DataFrame(rows)
    summary = {
        "schema_version": "public-cirsium-portable-detached-component-result-v1",
        "status": "DEVELOPMENT_ONLY_DETACHED_COMPONENT_REACHABILITY_COMPLETE",
        "cohort_unit_id": UNIT_ID,
        "species": SPECIES,
        "validated_product_changed": False,
        "new_confirmation_claim": False,
        "opened_outcome_diagnostic": True,
        "candidate_lanes_frozen_before_recent_scoring": True,
        "ranking_or_fitted_selector_used": False,
        "replacement_or_precision_relaxation_used": False,
        "fetch_audit": fetch_audit,
        "historical_records_in_declared_frame": int(len(historical)),
        "historical_population_anchors": int(len(anchors)),
        "recent_records_in_declared_frame": int(len(recent)),
        "novel_recent_clusters": int(len(novel)),
        "assessment_status": assessment.status,
        "broad_frame_audit": asdict(broad_audit),
        "worldcover_audit": asdict(wc_audit),
        "component_audit": asdict(component_audit),
        "component_partition_audit": asdict(partition_audit),
        "lane_candidate_counts": {key: int(len(value)) for key, value in lanes.items()},
        "reported_recovery_radii_km": radii,
        "interpretation_boundary": "Opened post-hoc reachability diagnostic only. Do not tune distance/component definitions or nominate a selector from this unit."
    }
    return table, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    table, summary = run(args.out_dir)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.out_dir / "detached_component_reachability.csv", index=False)
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    private_crop = args.out_dir / "private_worldcover_component_crop.tif"
    if private_crop.exists():
        private_crop.unlink()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
