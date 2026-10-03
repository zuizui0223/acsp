#!/usr/bin/env python3
"""Run the frozen public structural smoke for CIR04 / Cirsium otayae.

Development only. Historical occurrence rows are first collapsed into deterministic
0.5-km complete-link population clusters. The frozen Myoko slot then uses exactly
the four historical cluster medoids nearest the pre-execution JMA Myokosan reference.
Only later clusters assigned to those historical Myoko anchors enter the local-slot
outcome denominator. Public GSI DEM and the already frozen alpine structural family
are then evaluated for both the predeclared 2-km primary and 5-km sensitivity frames.
Every frozen prefix/radius combination is reported; no favorable cell is selected.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely.geometry import Point
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

from acsp.structural_selector import select_structural_support
from benchmark_public_japan_cirsium_temporal_anchor_v1 import (
    Cluster,
    cluster_min_distance_km,
    deterministic_complete_link_greedy,
    fetch_gbif_species,
    haversine_km,
)
from compare_public_japan_96pair_environment_vs_distance_v1 import select_spatial_balance
from gbif_fieldmap_builder_app import build_gsi_dem_for_bounds
from prepare_cirsium_private_candidate_frame_v1 import build_private_candidate_frame
from build_cirsium_private_alpine_local_grid_v1 import _sample_terrain, _utm_crs

CONTRACT = ROOT / "validation" / "public_cirsium_structural_three_family_smoke_v1.json"
AMENDMENT = ROOT / "validation" / "public_cirsium_structural_three_family_smoke_anchor_slot_amendment_v1.json"
UNIT_ID = "CIR04"
SPECIES = "Cirsium otayae"
FAMILY = "ALPINE_TOPOGRAPHIC_STRUCTURE"
INNER_M = 500.0
GRID_M = 100.0


def strict_period(records: pd.DataFrame, start: int, end: int) -> pd.DataFrame:
    out = records.loc[records["year"].between(start, end)].copy()
    if out.empty:
        return out
    return (
        out.sort_values(["latitude", "longitude", "year", "gbif_key"], kind="mergesort")
        .drop_duplicates(["latitude", "longitude", "year"], keep="first")
        .reset_index(drop=True)
    )


def cluster_medoid(cluster: Cluster) -> dict[str, object]:
    """Return the deterministic observed member minimizing within-cluster distance."""
    if not cluster.members:
        raise ValueError("cannot calculate a medoid for an empty cluster")
    candidates: list[tuple[float, float, float, str]] = []
    for lat, lon, gbif_key in cluster.members:
        total = sum(haversine_km(lat, lon, old_lat, old_lon) for old_lat, old_lon, _ in cluster.members)
        candidates.append((float(total), float(lat), float(lon), str(gbif_key)))
    total, lat, lon, gbif_key = min(candidates)
    return {
        "latitude": lat,
        "longitude": lon,
        "gbif_key": gbif_key,
        "cluster_size": int(len(cluster.members)),
        "medoid_total_distance_km": total,
    }


def historical_cluster_table(historical: pd.DataFrame) -> tuple[list[Cluster], pd.DataFrame]:
    clusters = deterministic_complete_link_greedy(historical, 0.5)
    rows: list[dict[str, object]] = []
    for index, cluster in enumerate(clusters):
        row = cluster_medoid(cluster)
        row["historical_cluster_id"] = f"H{index:04d}"
        row["historical_cluster_index"] = int(index)
        rows.append(row)
    table = pd.DataFrame(rows)
    if table.empty:
        raise ValueError("no historical complete-link clusters")
    return clusters, table


def select_myoko_slot_anchors(
    medoids: pd.DataFrame,
    *,
    reference_latitude: float,
    reference_longitude: float,
    count: int,
) -> pd.DataFrame:
    """Select the frozen number of historical cluster medoids nearest Myokosan."""
    if int(count) <= 0:
        raise ValueError("slot anchor count must be positive")
    if len(medoids) < int(count):
        raise ValueError(f"need {int(count)} historical population clusters, found {len(medoids)}")
    work = medoids.copy()
    work["distance_to_slot_reference_km"] = [
        haversine_km(reference_latitude, reference_longitude, float(lat), float(lon))
        for lat, lon in zip(work["latitude"], work["longitude"])
    ]
    return (
        work.sort_values(
            ["distance_to_slot_reference_km", "latitude", "longitude", "gbif_key"],
            kind="mergesort",
        )
        .head(int(count))
        .reset_index(drop=True)
    )


def slot_novel_recent_clusters(
    records: pd.DataFrame,
    *,
    historical_clusters: list[Cluster],
    medoids: pd.DataFrame,
    selected_anchors: pd.DataFrame,
) -> tuple[list[Cluster], dict[str, int]]:
    """Attribute later clusters to the historical Voronoi catchment of selected anchors."""
    recent = strict_period(records, 2021, 2025)
    recent_clusters = deterministic_complete_link_greedy(recent, 0.5)
    selected_indices = set(selected_anchors["historical_cluster_index"].astype(int))
    medoid_order = medoids.set_index("historical_cluster_index")
    novel: list[Cluster] = []
    reobserved = 0
    offslot_novel = 0
    for recent_cluster in recent_clusters:
        distances: list[tuple[float, float, float, str, int]] = []
        for index, historical_cluster in enumerate(historical_clusters):
            medoid = medoid_order.loc[int(index)]
            distances.append(
                (
                    float(cluster_min_distance_km(recent_cluster, historical_cluster)),
                    float(medoid.latitude),
                    float(medoid.longitude),
                    str(medoid.gbif_key),
                    int(index),
                )
            )
        nearest_distance, _, _, _, nearest_index = min(distances)
        if nearest_distance <= 0.5 + 1e-12:
            reobserved += 1
        elif nearest_index in selected_indices:
            novel.append(recent_cluster)
        else:
            offslot_novel += 1
    return novel, {
        "recent_clusters_total": int(len(recent_clusters)),
        "recent_reobserved_clusters": int(reobserved),
        "recent_novel_clusters_in_slot": int(len(novel)),
        "recent_novel_clusters_outside_slot": int(offslot_novel),
    }


def build_annular_grid(anchors: pd.DataFrame, *, outer_km: float) -> tuple[pd.DataFrame, str]:
    if anchors.empty:
        raise ValueError("historical anchor table is empty")
    center_lon = float(anchors["longitude"].mean())
    center_lat = float(anchors["latitude"].mean())
    metric = _utm_crs(center_lon, center_lat)
    to_metric = Transformer.from_crs("EPSG:4326", metric, always_xy=True)
    to_wgs = Transformer.from_crs(metric, "EPSG:4326", always_xy=True)
    ax, ay = to_metric.transform(anchors["longitude"].to_numpy(float), anchors["latitude"].to_numpy(float))
    anchor_xy = np.column_stack([ax, ay])
    outer = unary_union([Point(float(x), float(y)).buffer(float(outer_km) * 1000.0) for x, y in anchor_xy])
    inner = unary_union([Point(float(x), float(y)).buffer(INNER_M) for x, y in anchor_xy])
    annulus = outer.difference(inner)
    if annulus.is_empty:
        raise ValueError("annular public frame is empty")
    minx, miny, maxx, maxy = annulus.bounds
    x0 = math.floor(minx / GRID_M) * GRID_M
    y0 = math.floor(miny / GRID_M) * GRID_M
    x1 = math.ceil(maxx / GRID_M) * GRID_M
    y1 = math.ceil(maxy / GRID_M) * GRID_M
    ncol = int(round((x1 - x0) / GRID_M)) + 1
    nrow = int(round((y1 - y0) / GRID_M)) + 1
    rows: list[dict[str, object]] = []
    for grid_row in range(nrow):
        y = y0 + grid_row * GRID_M
        for grid_col in range(ncol):
            x = x0 + grid_col * GRID_M
            point = Point(float(x), float(y))
            if not annulus.covers(point):
                continue
            dist = np.sqrt((anchor_xy[:, 0] - x) ** 2 + (anchor_xy[:, 1] - y) ** 2)
            nearest = float(np.min(dist))
            lon, lat = to_wgs.transform(x, y)
            rows.append(
                {
                    "candidate_cell_id": f"{UNIT_ID}_{int(round(outer_km * 1000)):04d}_r{grid_row}_c{grid_col}",
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "grid_row": int(grid_row),
                    "grid_col": int(grid_col),
                    "nearest_anchor_km": nearest / 1000.0,
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError("no public annular candidate cells")
    return frame, metric.to_string()


def add_gsi_terrain(frame: pd.DataFrame, anchors: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    west = float(frame["longitude"].min()) - 0.01
    east = float(frame["longitude"].max()) + 0.01
    south = float(frame["latitude"].min()) - 0.01
    north = float(frame["latitude"].max()) + 0.01
    refs = tuple((float(r.latitude), float(r.longitude)) for r in anchors.itertuples(index=False))
    dem_path, attribution = build_gsi_dem_for_bounds((west, south, east, north), refs, max_tiles=400)
    if not dem_path:
        raise RuntimeError("public GSI DEM mosaic could not be constructed")
    out = _sample_terrain(frame, Path(dem_path))
    audit = {
        "source": "GSI public DEM tile mosaic",
        "attribution": str(attribution),
        "bounds": [west, south, east, north],
        "candidate_rows_before_complete_terrain": int(len(frame)),
        "candidate_rows_after_complete_terrain": int(len(out)),
    }
    return out, audit


def cluster_recovery(selected: pd.DataFrame, clusters: list[Cluster], radius_km: float) -> float:
    if selected.empty or not clusters:
        return 0.0
    recovered = 0
    points = list(zip(selected["latitude"].astype(float), selected["longitude"].astype(float)))
    for cluster in clusters:
        hit = any(
            haversine_km(lat, lon, member_lat, member_lon) <= radius_km + 1e-12
            for lat, lon in points
            for member_lat, member_lon, _ in cluster.members
        )
        recovered += int(hit)
    return float(recovered / len(clusters))


def nearest_prefix(frame: pd.DataFrame, k: int) -> pd.DataFrame:
    return (
        frame.sort_values(["nearest_anchor_km", "candidate_cell_id"], kind="mergesort")
        .head(int(k))
        .reset_index(drop=True)
    )


def run() -> tuple[pd.DataFrame, dict[str, object]]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    amendment = json.loads(AMENDMENT.read_text(encoding="utf-8"))
    if contract.get("status") != "DEVELOPMENT_ONLY_FROZEN_BEFORE_STRUCTURAL_LAYER_EXECUTION":
        raise ValueError("three-family smoke contract is not frozen")
    if amendment.get("status") != "PRE_EXECUTION_UNDERSPECIFICATION_FIXED_BEFORE_FIRST_STRUCTURAL_LAYER_RUN":
        raise ValueError("anchor/slot amendment is not frozen")
    if amendment.get("structural_layer_execution_before_amendment") is not False:
        raise ValueError("anchor/slot amendment is not pre-execution")
    unit = next(row for row in contract["units"] if row["cohort_unit_id"] == UNIT_ID)
    if unit["species"] != SPECIES or unit["family"] != FAMILY:
        raise ValueError("CIR04 identity/family mismatch")
    slot = amendment["cir04_myoko_slot"]
    if slot["cohort_unit_id"] != UNIT_ID or slot["species"] != SPECIES:
        raise ValueError("CIR04 Myoko amendment identity mismatch")

    records, fetch_audit = fetch_gbif_species(SPECIES, maximum_records=10000, pause_seconds=0.02)
    historical = strict_period(records, 2000, 2020)
    if historical.empty:
        raise RuntimeError("CIR04 has no strict public historical evidence")
    historical_clusters, medoids = historical_cluster_table(historical)
    reference = slot["public_reference"]
    anchors = select_myoko_slot_anchors(
        medoids,
        reference_latitude=float(reference["latitude"]),
        reference_longitude=float(reference["longitude"]),
        count=int(slot["frozen_primary_anchor_count"]),
    )
    novel, slot_audit = slot_novel_recent_clusters(
        records,
        historical_clusters=historical_clusters,
        medoids=medoids,
        selected_anchors=anchors,
    )

    prefix_fractions = [float(value) for value in contract["prefix_curve"]["fractions"]]
    recovery_radii = [float(value) for value in contract["outcome"]["recovery_radii_km"]]
    results: list[dict[str, object]] = []
    frame_audits: list[dict[str, object]] = []

    outer_frames = (
        float(contract["candidate_frames"]["primary_outer_radius_km"]),
        float(contract["candidate_frames"]["sensitivity_outer_radius_km"]),
    )
    for outer_km in outer_frames:
        raw, metric = build_annular_grid(anchors, outer_km=outer_km)
        raw, terrain_audit = add_gsi_terrain(raw, anchors)
        source_manifest = {
            "schema_version": "public-cirsium-alpine-smoke-source-v1",
            "cohort_unit_id": UNIT_ID,
            "source": "public GSI DEM + strict public GBIF historical complete-link medoids + frozen JMA Myoko slot reference",
            "anchor_representation": "0.5-km complete-link cluster medoid",
            "selected_anchor_count": int(len(anchors)),
            "field_outcomes_opened": False,
            "human_access_used": False,
        }
        built, frame_summary = build_private_candidate_frame(
            raw,
            feature_family=FAMILY,
            source_manifest=source_manifest,
            graph_radius_cells=1,
        )
        frame_audits.append(
            {
                "outer_km": outer_km,
                "metric_crs": metric,
                "candidate_rows": int(len(built)),
                "support_provenance_id": frame_summary["support_provenance_id"],
                **terrain_audit,
            }
        )
        for fraction in prefix_fractions:
            k = max(1, min(len(built), int(math.ceil(fraction * len(built)))))
            structural, _ = select_structural_support(
                built,
                count=k,
                feature_family=FAMILY,
                support_provenance_id=frame_summary["support_provenance_id"],
            )
            nearest = nearest_prefix(built, k)
            balanced = select_spatial_balance(built, pair_id=4, count=k)
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
                        "structural_recall": cluster_recovery(structural, novel, radius),
                        "nearest_recall": cluster_recovery(nearest, novel, radius),
                        "spatial_balance_recall": cluster_recovery(balanced, novel, radius),
                    }
                )

    table = pd.DataFrame(results)
    if table.empty:
        raise RuntimeError("CIR04 smoke produced no prefix-curve rows")
    summary = {
        "schema_version": "public-cirsium-alpine-structural-smoke-result-v1",
        "status": "DEVELOPMENT_ONLY_ALPINE_SMOKE_COMPLETE",
        "cohort_unit_id": UNIT_ID,
        "species": SPECIES,
        "family": FAMILY,
        "validated_product_changed": False,
        "new_confirmation_claim": False,
        "strict_public_records": int(len(records)),
        "strict_historical_rows": int(len(historical)),
        "historical_population_clusters": int(len(historical_clusters)),
        "selected_myoko_anchor_medoids": int(len(anchors)),
        "slot_reference_name": str(reference["name"]),
        "slot_reference_source": str(reference["source"]),
        "slot_attribution_audit": slot_audit,
        "novel_recent_clusters": int(len(novel)),
        "fetch_audit": fetch_audit,
        "frame_audits": frame_audits,
        "reported_outer_frames_km": sorted(table["outer_frame_km"].unique().tolist()),
        "reported_prefix_fractions": prefix_fractions,
        "reported_recovery_radii_km": recovery_radii,
        "structural_any_positive_recovery": bool((table["structural_recall"] > 0).any()),
        "structural_exceeds_nearest_any_cell": bool((table["structural_recall"] > table["nearest_recall"]).any()),
        "nearest_exceeds_structural_any_cell": bool((table["nearest_recall"] > table["structural_recall"]).any()),
        "interpretation_boundary": "One already-opened Cirsium alpine unit, development smoke only. Population anchors and Myoko slot attribution were frozen in a pre-execution amendment. All frozen frame/prefix/radius cells are reported; no favorable cell can be promoted as a method.",
    }
    return table, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    table, summary = run()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.out_dir / "alpine_prefix_curve.csv", index=False)
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
