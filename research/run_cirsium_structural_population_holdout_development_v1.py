#!/usr/bin/env python3
"""Run the frozen public Cirsium structural whole-population holdout v1.

Development only. Three source-compatible structural families are evaluated on
fixed Japanese validation regions. Every strict 2000-2025 population is hidden
once. Structural, nearest-known and deterministic spatial-balance orders use the
same fold-specific source-complete candidate frame and the same selected count.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

from acsp.discovery import (
    attach_nearest_anchor_distance,
    build_rectangular_candidate_frame,
    build_structural_support_order,
    haversine_km,
    rank_morton_dyadic_spatial_balance,
    rank_nearest_anchor,
)
from acsp.discovery.providers import retain_worldcover_land_points
from acsp.discovery.providers.worldcover_neighborhood_points import (
    attach_worldcover_neighbourhood_fractions,
)
from acsp.taxon_patches import VALIDATED_JAPAN_REGIONS
from benchmark_public_japan_cirsium_temporal_anchor_v1 import (
    deterministic_complete_link_greedy,
    fetch_gbif_species,
)
from build_cirsium_private_alpine_local_grid_v1 import _sample_terrain
from preflight_cirsium_structural_population_holdout_v1 import dedupe_exact_coordinates

CONTRACT_PATH = ROOT / "validation" / "cirsium_structural_population_holdout_development_v1.json"
PREFLIGHT_TERMINAL = ROOT / "validation" / "cirsium_structural_population_holdout_preflight_result_v1.json"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _region_registry() -> dict[str, dict[str, Any]]:
    return {
        str(region_id): {
            "region_id": str(region_id),
            "region_name": str(region_name),
            "geographic_stratum": str(stratum),
            "west": float(west),
            "south": float(south),
            "east": float(east),
            "north": float(north),
        }
        for region_id, region_name, stratum, west, south, east, north in VALIDATED_JAPAN_REGIONS
    }


def _inside_region(frame: pd.DataFrame, region: dict[str, Any]) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    return frame.loc[
        pd.to_numeric(frame["longitude"], errors="coerce").between(float(region["west"]), float(region["east"]), inclusive="both")
        & pd.to_numeric(frame["latitude"], errors="coerce").between(float(region["south"]), float(region["north"]), inclusive="both")
    ].copy().reset_index(drop=True)


def _cluster_medoid(cluster: Any, *, population_index: int) -> dict[str, Any]:
    members = list(cluster.members)
    if not members:
        raise ValueError("population cluster cannot be empty")
    candidates: list[tuple[float, float, float, str]] = []
    for lat, lon, key in members:
        total = 0.0
        for other_lat, other_lon, _ in members:
            total += float(haversine_km(float(lat), float(lon), float(other_lat), float(other_lon)))
        candidates.append((total, float(lat), float(lon), str(key)))
    _, lat, lon, key = min(candidates)
    return {
        "occurrence_id": f"population_{int(population_index):03d}_{key}",
        "latitude": lat,
        "longitude": lon,
        "cluster_size": int(len(members)),
    }


def _training_anchors(clusters: list[Any], hidden_index: int) -> pd.DataFrame:
    rows = [
        _cluster_medoid(cluster, population_index=index)
        for index, cluster in enumerate(clusters)
        if index != int(hidden_index)
    ]
    return pd.DataFrame(rows)


def population_recovered(selected: pd.DataFrame, hidden_cluster: Any, radius_km: float) -> bool:
    if selected is None or selected.empty:
        return False
    points = list(zip(selected["latitude"].astype(float), selected["longitude"].astype(float)))
    for lat, lon in points:
        for member_lat, member_lon, _ in hidden_cluster.members:
            if haversine_km(float(lat), float(lon), float(member_lat), float(member_lon)) <= float(radius_km) + 1e-12:
                return True
    return False


def _terrain_chunk_groups(frame: pd.DataFrame, chunk_cells: int) -> list[pd.DataFrame]:
    if frame.empty:
        return []
    work = frame.copy()
    work["_chunk_row"] = work["grid_row"].astype(int) // int(chunk_cells)
    work["_chunk_col"] = work["grid_col"].astype(int) // int(chunk_cells)
    return [
        group.drop(columns=["_chunk_row", "_chunk_col"]).copy().reset_index(drop=True)
        for _, group in work.groupby(["_chunk_row", "_chunk_col"], sort=True)
    ]


def attach_gsi_microterrain_chunks(
    frame: pd.DataFrame,
    *,
    work_dir: Path,
    chunk_cells: int,
    margin_degrees: float,
    max_tiles: int,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    if frame.empty:
        raise ValueError("terrain input frame cannot be empty")
    cache = work_dir / "gsi-cache"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("GBIF_FIELDMAP_CACHE", str(cache))
    from gbif_fieldmap_builder_app import build_gsi_dem_for_bounds

    pieces: list[pd.DataFrame] = []
    audits: list[dict[str, Any]] = []
    for index, component in enumerate(_terrain_chunk_groups(frame, chunk_cells)):
        west = float(component["longitude"].min()) - float(margin_degrees)
        east = float(component["longitude"].max()) + float(margin_degrees)
        south = float(component["latitude"].min()) - float(margin_degrees)
        north = float(component["latitude"].max()) + float(margin_degrees)
        references = tuple(
            (float(row.latitude), float(row.longitude))
            for row in component.iloc[:: max(1, len(component) // 8)].head(8).itertuples(index=False)
        )
        dem_path, attribution = build_gsi_dem_for_bounds(
            (west, south, east, north),
            references,
            max_tiles=int(max_tiles),
        )
        if not dem_path:
            raise RuntimeError(f"GSI_DEM_UNAVAILABLE_FOR_CHUNK:{index}")
        sampled = _sample_terrain(component, Path(dem_path))
        if sampled.empty:
            raise RuntimeError(f"GSI_TERRAIN_EMPTY_FOR_CHUNK:{index}")
        pieces.append(sampled)
        audits.append(
            {
                "chunk_index": int(index),
                "candidate_rows_input": int(len(component)),
                "candidate_rows_complete": int(len(sampled)),
                "gsi_attribution": str(attribution),
            }
        )
    merged = pd.concat(pieces, ignore_index=True)
    if merged["candidate_cell_id"].duplicated().any():
        raise RuntimeError("GSI_CHUNK_ASSEMBLY_DUPLICATED_CANDIDATE_IDS")
    return merged.sort_values("candidate_cell_id", kind="mergesort").reset_index(drop=True), audits


def build_region_source_surface(
    region: dict[str, Any],
    *,
    contract: dict[str, Any],
    work_dir: Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    cfg = contract["candidate_frame"]
    bounds = (float(region["west"]), float(region["south"]), float(region["east"]), float(region["north"]))
    raw_grid, grid_audit = build_rectangular_candidate_frame(
        bounds,
        grid_spacing_m=float(cfg["grid_spacing_m"]),
        candidate_id_prefix=f"structural_holdout_{region['region_id']}",
    )
    land, land_audit = retain_worldcover_land_points(raw_grid)
    neighbourhood, neighbourhood_audit = attach_worldcover_neighbourhood_fractions(
        land,
        radius_m=float(contract["public_structural_sources"]["landcover"]["neighbourhood_radius_m"]),
    )
    terrain_cfg = contract["public_structural_sources"]["terrain"]
    terrain, terrain_audit = attach_gsi_microterrain_chunks(
        neighbourhood,
        work_dir=work_dir,
        chunk_cells=int(terrain_cfg["candidate_chunk_grid_cells"]),
        margin_degrees=float(terrain_cfg["chunk_margin_degrees"]),
        max_tiles=int(terrain_cfg["max_gsi_tiles_per_chunk"]),
    )
    if terrain.empty:
        raise RuntimeError("SOURCE_COMPLETE_REGION_SURFACE_EMPTY")
    source = {
        "region_id": str(region["region_id"]),
        "grid_spacing_m": float(cfg["grid_spacing_m"]),
        "raw_grid_candidate_count": int(len(raw_grid)),
        "worldcover_land_candidate_count": int(len(land)),
        "source_complete_candidate_count": int(len(terrain)),
        "grid_audit": grid_audit.__dict__.copy() if hasattr(grid_audit, "__dict__") else str(grid_audit),
        "worldcover_land_audit": land_audit.as_dict(),
        "worldcover_neighbourhood_audit": neighbourhood_audit.as_dict(),
        "gsi_terrain_chunks": terrain_audit,
    }
    return terrain, source


def _pair_clusters(pair: dict[str, Any], region: dict[str, Any]) -> tuple[list[Any], dict[str, Any]]:
    records, fetch_audit = fetch_gbif_species(str(pair["species_binomial"]), maximum_records=10000)
    strict = dedupe_exact_coordinates(records)
    subset = _inside_region(strict, region)
    clusters = deterministic_complete_link_greedy(
        subset,
        radius_km=0.5,
    )
    return clusters, {
        "strict_unique_coordinates": int(len(subset)),
        "population_clusters": int(len(clusters)),
        "fetch_audit": fetch_audit,
    }


def _fold_orders(
    base_surface: pd.DataFrame,
    structural_full: pd.DataFrame,
    anchors: pd.DataFrame,
    *,
    known_exclusion_km: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    with_distance = attach_nearest_anchor_distance(base_surface, anchors)
    fold_frame = with_distance.loc[
        pd.to_numeric(with_distance["nearest_anchor_km"], errors="coerce").ge(float(known_exclusion_km) - 1e-12)
    ].copy().reset_index(drop=True)
    if fold_frame.empty:
        return fold_frame, fold_frame.copy(), fold_frame.copy(), fold_frame.copy()
    allowed = set(fold_frame["candidate_cell_id"].astype(str))
    structural = structural_full.loc[
        structural_full["candidate_cell_id"].astype(str).isin(allowed)
    ].copy()
    structural = structural.sort_values(
        ["structural_support", "candidate_cell_id"], ascending=[False, True], kind="mergesort"
    ).reset_index(drop=True)
    structural["decision_rank"] = range(1, len(structural) + 1)
    nearest = rank_nearest_anchor(fold_frame)
    spatial, _ = rank_morton_dyadic_spatial_balance(fold_frame)
    return fold_frame, structural, nearest, spatial


def _score_fold_rows(
    *,
    pair: dict[str, Any],
    fold_index: int,
    hidden_cluster: Any,
    fold_frame: pd.DataFrame,
    structural: pd.DataFrame,
    nearest: pd.DataFrame,
    spatial: pd.DataFrame,
    prefix_fractions: list[float],
    recovery_radii: list[float],
) -> list[dict[str, Any]]:
    n = int(len(fold_frame))
    rows: list[dict[str, Any]] = []
    for fraction in prefix_fractions:
        k = 0 if n == 0 else max(1, min(n, int(math.ceil(float(fraction) * n))))
        structural_selected = structural.head(k) if k else structural.iloc[:0]
        nearest_selected = nearest.head(k) if k else nearest.iloc[:0]
        spatial_selected = spatial.head(k) if k else spatial.iloc[:0]
        for radius in recovery_radii:
            rows.append(
                {
                    "pair_id": str(pair["pair_id"]),
                    "cohort_unit_id": str(pair["cohort_unit_id"]),
                    "species_binomial": str(pair["species_binomial"]),
                    "structural_feature_family": str(pair["structural_feature_family"]),
                    "region_id": str(pair["region_id"]),
                    "fold_id": f"{pair['pair_id']}__population_{int(fold_index):03d}",
                    "hidden_population_size": int(len(hidden_cluster.members)),
                    "candidate_count": n,
                    "prefix_fraction": float(fraction),
                    "selected_count": int(k),
                    "recovery_radius_km": float(radius),
                    "structural_recovered": bool(population_recovered(structural_selected, hidden_cluster, radius)),
                    "nearest_recovered": bool(population_recovered(nearest_selected, hidden_cluster, radius)),
                    "spatial_balance_recovered": bool(population_recovered(spatial_selected, hidden_cluster, radius)),
                    "full_frame_reachable": bool(population_recovered(fold_frame, hidden_cluster, radius)),
                }
            )
    return rows


def _wtl(left: pd.Series, right: pd.Series) -> dict[str, int]:
    a = left.astype(int).to_numpy()
    b = right.astype(int).to_numpy()
    return {
        "win": int(np.sum(a > b)),
        "tie": int(np.sum(a == b)),
        "loss": int(np.sum(a < b)),
    }


def summarize(
    curve: pd.DataFrame,
    pair_audits: list[dict[str, Any]],
    *,
    contract: dict[str, Any],
) -> dict[str, Any]:
    primary_radius = float(contract["outcome"]["primary_recovery_radius_km"])
    primary = curve.loc[np.isclose(pd.to_numeric(curve.get("recovery_radius_km", pd.Series(dtype=float)), errors="coerce"), primary_radius)].copy() if not curve.empty else pd.DataFrame()
    executed_pairs = [row for row in pair_audits if row["status"] == "EXECUTED"]
    source_failures = [row for row in pair_audits if row["status"] == "SOURCE_PROVIDER_FAILURE"]
    drift = [row for row in pair_audits if row["status"] == "POPULATION_COUNT_DRIFT"]

    if primary.empty:
        aggregate: dict[str, Any] = {
            "structural_mean_recovery": None,
            "nearest_mean_recovery": None,
            "spatial_balance_mean_recovery": None,
            "structural_minus_nearest": None,
            "structural_minus_spatial_balance": None,
            "structural_vs_nearest_win_tie_loss": None,
            "structural_vs_spatial_balance_win_tie_loss": None,
        }
        family_summary: dict[str, Any] = {}
    else:
        s = primary["structural_recovered"].astype(float)
        n = primary["nearest_recovered"].astype(float)
        b = primary["spatial_balance_recovered"].astype(float)
        aggregate = {
            "structural_mean_recovery": float(s.mean()),
            "nearest_mean_recovery": float(n.mean()),
            "spatial_balance_mean_recovery": float(b.mean()),
            "structural_minus_nearest": float((s - n).mean()),
            "structural_minus_spatial_balance": float((s - b).mean()),
            "structural_vs_nearest_win_tie_loss": _wtl(primary["structural_recovered"], primary["nearest_recovered"]),
            "structural_vs_spatial_balance_win_tie_loss": _wtl(primary["structural_recovered"], primary["spatial_balance_recovered"]),
        }
        family_summary = {}
        for family, frame in primary.groupby("structural_feature_family", sort=True):
            family_summary[str(family)] = {
                "rows": int(len(frame)),
                "folds": int(frame["fold_id"].nunique()),
                "structural_mean_recovery": float(frame["structural_recovered"].astype(float).mean()),
                "nearest_mean_recovery": float(frame["nearest_recovered"].astype(float).mean()),
                "spatial_balance_mean_recovery": float(frame["spatial_balance_recovered"].astype(float).mean()),
            }

    fold_ceiling = pd.DataFrame()
    if not primary.empty:
        fold_ceiling = primary.loc[primary["prefix_fraction"].eq(1.0)].drop_duplicates("fold_id")
    return {
        "schema_version": "cirsium-structural-population-holdout-development-result-v1",
        "status": "STRUCTURAL_POPULATION_HOLDOUT_DEVELOPMENT_COMPLETE",
        "source_contract": str(CONTRACT_PATH.relative_to(ROOT)),
        "validated_product_changed": False,
        "automatic_global_adapter_changed": False,
        "new_confirmation_claim": False,
        "field_outcomes_used": False,
        "expected_total_folds": int(contract["population_holdout"]["expected_total_folds"]),
        "executed_total_folds": int(primary["fold_id"].nunique()) if not primary.empty else 0,
        "executed_pairs": int(len(executed_pairs)),
        "source_provider_failure_pairs": int(len(source_failures)),
        "population_count_drift_pairs": int(len(drift)),
        "explicitly_deferred_eligible_pairs": contract["explicitly_deferred_eligible_pairs"],
        "pair_audits": pair_audits,
        "primary_5km_all_fold_all_prefix": aggregate,
        "primary_5km_full_frame_reachability": None if fold_ceiling.empty else float(fold_ceiling["full_frame_reachable"].astype(float).mean()),
        "family_primary_5km": family_summary,
        "promotion_allowed": False,
        "interpretation_boundary": "Opened public-data known-truth development only. One species per executed family; no selector promotion or field-efficiency claim is authorized. Source failures are unavailable evidence, not biological negatives."
    }


def run(work_dir: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    contract = _load_json(CONTRACT_PATH)
    if contract.get("status") != "FROZEN_BEFORE_STRUCTURAL_POPULATION_HOLDOUT_EXECUTION":
        raise ValueError("structural population-holdout contract is not frozen")
    if git_blob_sha1(PREFLIGHT_TERMINAL) != str(contract["preflight_terminal"]["git_blob_sha1"]):
        raise RuntimeError("PREFLIGHT_TERMINAL_GIT_BLOB_DRIFT")

    regions = _region_registry()
    execution_pairs = list(contract["execution_pairs"])
    source_surfaces: dict[str, tuple[pd.DataFrame, dict[str, Any]] | Exception] = {}
    for region_id in sorted({str(row["region_id"]) for row in execution_pairs}):
        region = regions[region_id]
        try:
            source_surfaces[region_id] = build_region_source_surface(
                region,
                contract=contract,
                work_dir=work_dir / region_id,
            )
        except Exception as exc:
            source_surfaces[region_id] = exc

    prefix_fractions = [float(value) for value in contract["prefix_curve"]["fractions"]]
    recovery_radii = [
        float(contract["outcome"]["primary_recovery_radius_km"]),
        float(contract["outcome"]["sensitivity_recovery_radius_km"]),
    ]
    known_exclusion = float(contract["candidate_frame"]["known_population_exclusion_km"])
    curve_rows: list[dict[str, Any]] = []
    pair_audits: list[dict[str, Any]] = []

    for pair in execution_pairs:
        pair_id = str(pair["pair_id"])
        region_id = str(pair["region_id"])
        source = source_surfaces[region_id]
        if isinstance(source, Exception):
            pair_audits.append(
                {
                    "pair_id": pair_id,
                    "status": "SOURCE_PROVIDER_FAILURE",
                    "failure": f"{type(source).__name__}:{source}",
                    "population_outcomes_scored": False,
                }
            )
            continue
        base_surface, source_audit = source

        try:
            clusters, population_audit = _pair_clusters(pair, regions[region_id])
        except Exception as exc:
            pair_audits.append(
                {
                    "pair_id": pair_id,
                    "status": "SOURCE_PROVIDER_FAILURE",
                    "failure": f"GBIF:{type(exc).__name__}:{exc}",
                    "population_outcomes_scored": False,
                }
            )
            continue
        expected_clusters = int(pair["expected_population_clusters"])
        if len(clusters) != expected_clusters:
            pair_audits.append(
                {
                    "pair_id": pair_id,
                    "status": "POPULATION_COUNT_DRIFT",
                    "expected_population_clusters": expected_clusters,
                    "observed_population_clusters": int(len(clusters)),
                    "population_outcomes_scored": False,
                }
            )
            continue

        try:
            structural_full, structural_audit = build_structural_support_order(
                base_surface,
                feature_family=str(pair["structural_feature_family"]),
                source_provenance=source_audit,
                graph_radius_cells=int(contract["structural_method"]["graph_radius_cells"]),
            )
        except Exception as exc:
            pair_audits.append(
                {
                    "pair_id": pair_id,
                    "status": "SOURCE_PROVIDER_FAILURE",
                    "failure": f"STRUCTURAL_SOURCE:{type(exc).__name__}:{exc}",
                    "population_outcomes_scored": False,
                }
            )
            continue

        for hidden_index, hidden_cluster in enumerate(clusters):
            anchors = _training_anchors(clusters, hidden_index)
            fold_frame, structural, nearest, spatial = _fold_orders(
                base_surface,
                structural_full,
                anchors,
                known_exclusion_km=known_exclusion,
            )
            curve_rows.extend(
                _score_fold_rows(
                    pair=pair,
                    fold_index=hidden_index,
                    hidden_cluster=hidden_cluster,
                    fold_frame=fold_frame,
                    structural=structural,
                    nearest=nearest,
                    spatial=spatial,
                    prefix_fractions=prefix_fractions,
                    recovery_radii=recovery_radii,
                )
            )

        pair_audits.append(
            {
                "pair_id": pair_id,
                "status": "EXECUTED",
                "population_outcomes_scored": True,
                "strict_unique_coordinates": int(population_audit["strict_unique_coordinates"]),
                "population_clusters": int(population_audit["population_clusters"]),
                "folds": int(len(clusters)),
                "source_complete_candidate_count": int(len(base_surface)),
                "structural_support_provenance_id": structural_audit.support_provenance_id,
                "source_audit": source_audit,
            }
        )

    curve = pd.DataFrame(curve_rows)
    summary = summarize(curve, pair_audits, contract=contract)
    return curve, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    curve, summary = run(args.out_dir / "source-cache")
    curve.to_csv(args.out_dir / "population_holdout_curve.csv", index=False)
    (args.out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
