#!/usr/bin/env python3
"""Diagnose why the retained 32-patch Campanula policy succeeds.

This is a development-only diagnostic, not a candidate policy.  All patch
features and the canonical fixed spatial-policy order are constructed from
pre-2026 occurrences and public NDVI before field outcomes are opened.  The 2026
detection clusters are then used only to identify the first canonical patch that
recovers each cluster at 1 km and to describe those witness patches.

The goal is to learn which *outcome-blind structural variables* distinguish the
late but necessary patches that simpler compression rules repeatedly omit.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

import campanula_patch_policy as base
import campanula_patch_policy_spatial as spatial
from campanula_worldcover_discovery import haversine_km

SUPPORT_FRACTION = 0.05
RECOVERY_RADIUS_KM = 1.0
SUPPORT_WEIGHT = 0.25
NEW_COMPONENT_WEIGHT = 0.10
AREA_COST_WEIGHT = 0.02
GEO_WEIGHT = 1.00
GAP_WEIGHT = 0.05

TRANSITION_COLUMNS = [
    "ndvi_sd100",
    "ndvi_sd250",
    "ndvi_grad100",
    "ndvi_grad250",
    "ndvi_amp_sd100",
    "ndvi_scale_contrast",
    "ndvi_hetero_contrast",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--microterrain-universe", type=Path, required=True)
    p.add_argument("--gbif-prototypes", type=Path, required=True)
    p.add_argument("--ndvi", type=Path, required=True)
    p.add_argument("--detections", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    return p.parse_args()


def _nearest_patch_distance(zones: pd.DataFrame) -> np.ndarray:
    components = zones["survey_area_id"].astype(str).to_numpy()
    lat = pd.to_numeric(zones["latitude"], errors="coerce").to_numpy(float)
    lon = pd.to_numeric(zones["longitude"], errors="coerce").to_numpy(float)
    out = np.zeros(len(zones), dtype=float)
    for component in sorted(set(components)):
        idx = np.flatnonzero(components == component)
        if len(idx) <= 1:
            out[idx] = 0.0
            continue
        for pos in idx:
            others = idx[idx != pos]
            out[pos] = float(np.min(haversine_km(lat[pos], lon[pos], lat[others], lon[others])))
    return out


def _zone_feature_table(
    universe: pd.DataFrame,
    zones: pd.DataFrame,
    support_rank: np.ndarray,
    support: np.ndarray,
    area_cost: np.ndarray,
    gap: np.ndarray,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    nearest_patch = _nearest_patch_distance(zones)
    for pos, (_, zone) in enumerate(zones.iterrows()):
        members = base.patch.member_indices(zone)
        member_rows = universe.iloc[members]
        row: dict[str, object] = {
            "zone_position": int(pos),
            "zone_id": str(zone["zone_id"]),
            "survey_area_id": str(zone["survey_area_id"]),
            "latitude": float(zone["latitude"]),
            "longitude": float(zone["longitude"]),
            "zone_member_count": int(zone.get("zone_member_count", len(members))),
            "support": float(support[pos]),
            "area_cost_norm": float(area_cost[pos]),
            "survey_gap_norm": float(gap[pos]),
            "nearest_patch_distance_km": float(nearest_patch[pos]),
            "support_rank_best": float(np.min(support_rank[members])),
            "support_rank_median": float(np.median(support_rank[members])),
        }
        for column in TRANSITION_COLUMNS:
            values = pd.to_numeric(member_rows[column], errors="coerce").to_numpy(float)
            finite = values[np.isfinite(values)]
            row[f"{column}_mean"] = float(np.mean(finite)) if len(finite) else None
            row[f"{column}_max"] = float(np.max(finite)) if len(finite) else None
        rows.append(row)
    return pd.DataFrame(rows)


def _detection_zone_distance(
    universe: pd.DataFrame,
    zones: pd.DataFrame,
    detections: pd.DataFrame,
) -> np.ndarray:
    matrix = np.full((len(detections), len(zones)), np.inf, dtype=float)
    for zpos, (_, zone) in enumerate(zones.iterrows()):
        members = base.patch.member_indices(zone)
        member_rows = universe.iloc[members]
        island = str(zone["survey_area_id"])
        local_det = np.flatnonzero(detections["island"].astype(str).to_numpy() == island)
        if not len(local_det):
            continue
        mlat = member_rows["lat"].to_numpy(float)
        mlon = member_rows["lon"].to_numpy(float)
        for dpos in local_det:
            det = detections.iloc[dpos]
            distances = haversine_km(
                float(det["latitude"]),
                float(det["longitude"]),
                mlat,
                mlon,
            )
            matrix[dpos, zpos] = float(np.min(np.asarray(distances, dtype=float)))
    return matrix


def main() -> None:
    args = parse_args()
    universe = pd.read_csv(args.microterrain_universe)
    prototypes = pd.read_csv(args.gbif_prototypes)
    universe, prototypes = base.attach_ndvi(universe, prototypes, args.ndvi)
    responsibility, support_rank, proto_rows, kernel_scale = base.environmental_geometry(universe, prototypes)
    _, zones = base.make_zones(universe, support_rank, SUPPORT_FRACTION)
    matrix, support, area_cost, islands = base.patch_responsibilities(zones, responsibility, support_rank)
    gap, spatial_scale, islands, lat, lon = spatial.patch_spatial_features(zones, proto_rows)
    order = spatial.greedy_spatial_order(
        matrix,
        support,
        area_cost,
        islands,
        lat,
        lon,
        gap,
        spatial_scale,
        SUPPORT_WEIGHT,
        NEW_COMPONENT_WEIGHT,
        AREA_COST_WEIGHT,
        GEO_WEIGHT,
        GAP_WEIGHT,
    )
    features = _zone_feature_table(universe, zones, support_rank, support, area_cost, gap)
    rank_by_pos = {int(pos): rank for rank, pos in enumerate(order, start=1)}
    features["canonical_rank"] = features["zone_position"].map(rank_by_pos).astype(int)
    features["canonical_top32"] = features["canonical_rank"] <= 32

    # Outcome-blind feature construction and canonical order end here.
    detections = pd.read_csv(args.detections)
    distances = _detection_zone_distance(universe, zones, detections)
    detection_rows: list[dict[str, object]] = []
    witness_positions: list[int] = []
    for dpos, (_, detection) in enumerate(detections.iterrows()):
        first_rank = None
        witness_pos = None
        witness_distance = None
        for rank, pos in enumerate(order, start=1):
            value = float(distances[dpos, pos])
            if value <= RECOVERY_RADIUS_KM:
                first_rank = int(rank)
                witness_pos = int(pos)
                witness_distance = value
                break
        if first_rank is None or witness_pos is None:
            raise RuntimeError(f"detection {detection['detection_cluster_id']} not recoverable by patch universe")
        witness_positions.append(witness_pos)
        feature = features.loc[features["zone_position"].eq(witness_pos)].iloc[0]
        row = {
            "detection_cluster_id": int(detection["detection_cluster_id"]),
            "island": str(detection["island"]),
            "first_recovery_rank": first_rank,
            "witness_zone_id": str(feature["zone_id"]),
            "witness_distance_km": float(witness_distance),
        }
        for column in features.columns:
            if column in {"zone_position", "zone_id", "survey_area_id", "latitude", "longitude", "canonical_top32"}:
                continue
            value = feature[column]
            row[f"witness_{column}"] = None if pd.isna(value) else value.item() if hasattr(value, "item") else value
        detection_rows.append(row)

    detections_out = pd.DataFrame(detection_rows).sort_values("first_recovery_rank")
    unique_witness = sorted(set(witness_positions), key=lambda p: rank_by_pos[p])
    witness_features = features[features["zone_position"].isin(unique_witness)].copy()
    witness_features["first_detection_rank_using_zone"] = witness_features["zone_position"].map(
        lambda p: min(
            row["first_recovery_rank"]
            for row in detection_rows
            if int(rank_by_pos[int(p)]) == int(row["first_recovery_rank"])
        ) if any(int(rank_by_pos[int(p)]) == int(row["first_recovery_rank"]) for row in detection_rows) else np.nan
    )

    late = detections_out[detections_out["first_recovery_rank"] > 20]
    early = detections_out[detections_out["first_recovery_rank"] <= 20]
    numeric_feature_cols = [c for c in detections_out.columns if c.startswith("witness_") and c not in {"witness_zone_id"}]
    contrasts = []
    for column in numeric_feature_cols:
        a = pd.to_numeric(early[column], errors="coerce").dropna()
        b = pd.to_numeric(late[column], errors="coerce").dropna()
        if len(a) and len(b):
            contrasts.append({
                "feature": column,
                "early_mean": float(a.mean()),
                "late_mean": float(b.mean()),
                "late_minus_early": float(b.mean() - a.mean()),
                "early_median": float(a.median()),
                "late_median": float(b.median()),
            })
    contrasts_df = pd.DataFrame(contrasts)
    if not contrasts_df.empty:
        contrasts_df["abs_mean_difference"] = contrasts_df["late_minus_early"].abs()
        contrasts_df = contrasts_df.sort_values("abs_mean_difference", ascending=False)

    report = {
        "status": "development_only_structure_diagnostic",
        "species": "Campanula microdonta",
        "field_coordinates_used_to_build_patch_features": False,
        "field_coordinates_used_to_build_canonical_order": False,
        "canonical_policy": {
            "support_fraction": SUPPORT_FRACTION,
            "support_weight": SUPPORT_WEIGHT,
            "new_component_weight": NEW_COMPONENT_WEIGHT,
            "area_cost_weight": AREA_COST_WEIGHT,
            "geo_weight": GEO_WEIGHT,
            "gap_weight": GAP_WEIGHT,
            "top32_fixed_reference": True,
        },
        "patch_universe": int(len(zones)),
        "detection_count": int(len(detections)),
        "latest_first_recovery_rank": int(detections_out["first_recovery_rank"].max()),
        "detections_recovered_by_rank20": int((detections_out["first_recovery_rank"] <= 20).sum()),
        "detections_recovered_rank21_to_32": int(((detections_out["first_recovery_rank"] > 20) & (detections_out["first_recovery_rank"] <= 32)).sum()),
        "late_detection_ids": detections_out.loc[detections_out["first_recovery_rank"] > 20, "detection_cluster_id"].astype(int).tolist(),
        "top_feature_contrasts": contrasts_df.head(12).to_dict(orient="records") if not contrasts_df.empty else [],
        "kernel_scale": float(kernel_scale),
        "interpretation": "Field outcomes only label which already-frozen canonical patches are early versus late recovery witnesses; this diagnostic does not define an inference-time policy.",
    }

    args.out.mkdir(parents=True, exist_ok=True)
    features.to_csv(args.out / "canonical_patch_features.csv", index=False)
    detections_out.to_csv(args.out / "detection_first_recovery_witnesses.csv", index=False)
    witness_features.to_csv(args.out / "witness_patch_features.csv", index=False)
    contrasts_df.to_csv(args.out / "late_vs_early_feature_contrasts.csv", index=False)
    (args.out / "structure_diagnostic_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
