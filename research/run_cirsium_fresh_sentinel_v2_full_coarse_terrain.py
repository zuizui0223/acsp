#!/usr/bin/env python3
"""Execute and assemble all 49 fresh-SENTINEL v2 coarse-terrain tiles.

The scientific frame is already frozen. This module only shards terrain
attachment for runtime reliability. Sharding cannot alter tile membership,
candidate identity/order, terrain mechanics, or missingness semantics.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from acsp.global_geometry import fetch_geoboundaries_country_geometry
from research.attach_cirsium_fresh_sentinel_v2_coarse_terrain import (
    COMPLETE,
    POINT_MISSING,
    PROVIDER_FAILURE,
    attach_coarse_terrain_primitives,
)
from research.build_cirsium_fresh_sentinel_public_broad_frame_v2 import (
    build_fresh_sentinel_v2_outer_frame,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_v2_full_terrain_execution_v1.json"
SHARD_COUNT = 7
EXPECTED_TILES = 49
EXPECTED_POINTS_PER_TILE = 800
EXPECTED_CANDIDATES = EXPECTED_TILES * EXPECTED_POINTS_PER_TILE
STATUS_VOCAB = {COMPLETE, POINT_MISSING, PROVIDER_FAILURE}


def _contract() -> dict[str, Any]:
    value = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if value.get("status") != "FROZEN_BEFORE_FULL_49_TILE_TERRAIN_EXECUTION":
        raise ValueError("full terrain execution contract is not frozen")
    if int(value.get("expected_intersecting_tile_count", -1)) != EXPECTED_TILES:
        raise ValueError("expected tile count drift")
    if int(value.get("expected_points_per_tile", -1)) != EXPECTED_POINTS_PER_TILE:
        raise ValueError("expected points-per-tile drift")
    if int(value.get("expected_candidate_count", -1)) != EXPECTED_CANDIDATES:
        raise ValueError("expected candidate count drift")
    if int(value.get("execution", {}).get("terrain_shard_count", -1)) != SHARD_COUNT:
        raise ValueError("terrain shard count drift")
    return value


def frozen_outer_frame() -> pd.DataFrame:
    _contract()
    geometry = fetch_geoboundaries_country_geometry("JP")
    frame, summary = build_fresh_sentinel_v2_outer_frame(geometry)
    if int(summary["intersecting_tile_count"]) != EXPECTED_TILES:
        raise ValueError("live frozen Japan geometry tile count drift")
    if len(frame) != EXPECTED_CANDIDATES:
        raise ValueError("live frozen Japan geometry candidate count drift")
    return frame.reset_index(drop=True)


def tile_partition(tile_ids: list[str], *, shard_count: int = SHARD_COUNT) -> dict[int, list[str]]:
    ids = sorted(str(value) for value in tile_ids)
    if len(ids) != len(set(ids)):
        raise ValueError("regional tile IDs must be unique before sharding")
    count = int(shard_count)
    if count < 1:
        raise ValueError("shard_count must be >=1")
    return {
        shard_id: [tile_id for ordinal, tile_id in enumerate(ids) if ordinal % count == shard_id]
        for shard_id in range(count)
    }


def run_shard(shard_id: int, output_dir: Path) -> dict[str, Any]:
    _contract()
    shard_id = int(shard_id)
    if not 0 <= shard_id < SHARD_COUNT:
        raise ValueError(f"shard_id must be in [0,{SHARD_COUNT - 1}]")
    output = Path(output_dir)
    if output.exists():
        raise ValueError("refusing to overwrite existing terrain shard output")
    output.mkdir(parents=True)

    frame = frozen_outer_frame()
    tile_ids = sorted(frame["regional_tile_id"].astype(str).unique())
    if len(tile_ids) != EXPECTED_TILES:
        raise ValueError("frozen outer frame no longer has 49 tiles")
    partitions = tile_partition(tile_ids)
    selected_tiles = partitions[shard_id]
    if len(selected_tiles) != 7:
        raise ValueError(f"terrain shard {shard_id} must contain exactly seven tiles")

    rows: list[pd.DataFrame] = []
    tile_audits: list[dict[str, Any]] = []
    for tile_id in selected_tiles:
        part = frame.loc[frame["regional_tile_id"].astype(str).eq(tile_id)].copy().reset_index(drop=True)
        if len(part) != EXPECTED_POINTS_PER_TILE:
            raise ValueError(f"{tile_id} does not contain exactly 800 frozen candidates")
        enriched, summary = attach_coarse_terrain_primitives(part)
        if len(enriched) != EXPECTED_POINTS_PER_TILE:
            raise AssertionError(f"{tile_id} terrain attachment changed row count")
        if enriched["candidate_cell_id"].astype(str).tolist() != part["candidate_cell_id"].astype(str).tolist():
            raise AssertionError(f"{tile_id} terrain attachment changed candidate identity/order")
        enriched["terrain_shard_id"] = shard_id
        rows.append(enriched)
        tile_audits.append({
            "regional_tile_id": tile_id,
            "candidate_count": int(len(enriched)),
            "complete_candidate_count": int(summary["complete_candidate_count"]),
            "incomplete_candidate_count": int(summary["incomplete_candidate_count"]),
            "status_counts": summary["status_counts"],
            "provider_error_class": summary["provider_error_class"],
            "candidate_rows_dropped": int(summary["candidate_rows_dropped"]),
        })

    combined = pd.concat(rows, ignore_index=True)
    expected_rows = len(selected_tiles) * EXPECTED_POINTS_PER_TILE
    if len(combined) != expected_rows:
        raise AssertionError("terrain shard row count drift")
    if combined["candidate_cell_id"].astype(str).duplicated().any():
        raise AssertionError("terrain shard contains duplicate candidate IDs")
    if not set(combined["coarse_terrain_status"].astype(str)).issubset(STATUS_VOCAB):
        raise ValueError("terrain shard contains an unknown status")

    data_path = output / f"terrain_shard_{shard_id:02d}.csv.gz"
    combined.to_csv(data_path, index=False, compression="gzip")
    manifest = {
        "schema_version": "cirsium-fresh-sentinel-v2-coarse-terrain-shard-v1",
        "status": "COARSE_TERRAIN_SHARD_COMPLETE_PRE_OUTCOME",
        "shard_id": shard_id,
        "shard_count": SHARD_COUNT,
        "total_frozen_tile_count": EXPECTED_TILES,
        "selected_tile_count": len(selected_tiles),
        "selected_tile_ids": selected_tiles,
        "candidate_count": int(len(combined)),
        "expected_candidate_count": expected_rows,
        "candidate_rows_dropped": 0,
        "candidate_identity_order_preserved_within_tile": True,
        "tile_audits": tile_audits,
        "candidate_selection_added": False,
        "candidate_ranking_added": False,
        "field_outcomes_used": False,
        "private_exact_site_geometry_used": False,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def _find_shard_files(input_root: Path) -> tuple[list[Path], list[Path]]:
    root = Path(input_root)
    manifests = sorted(root.glob("**/manifest.json"))
    data = sorted(root.glob("**/terrain_shard_*.csv.gz"))
    return manifests, data


def assemble_shards(
    input_root: Path,
    output_csv: Path,
    summary_json: Path,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> dict[str, Any]:
    _contract()
    manifests, data_files = _find_shard_files(Path(input_root))
    if len(manifests) != SHARD_COUNT or len(data_files) != SHARD_COUNT:
        raise ValueError(
            f"expected {SHARD_COUNT} terrain shards; manifests={len(manifests)} data={len(data_files)}"
        )
    meta = [json.loads(path.read_text(encoding="utf-8")) for path in manifests]
    if sorted(int(item["shard_id"]) for item in meta) != list(range(SHARD_COUNT)):
        raise ValueError("terrain shard IDs are incomplete or duplicated")
    if any(int(item["candidate_rows_dropped"]) != 0 for item in meta):
        raise ValueError("a terrain shard reports candidate row loss")

    declared_tiles = [
        tile_id
        for item in meta
        for tile_id in item["selected_tile_ids"]
    ]
    if len(declared_tiles) != EXPECTED_TILES or len(set(declared_tiles)) != EXPECTED_TILES:
        raise ValueError("terrain shard tile coverage is not exactly 49 unique tiles")

    raw = pd.concat([pd.read_csv(path) for path in data_files], ignore_index=True)
    if len(raw) != EXPECTED_CANDIDATES:
        raise ValueError(f"assembled terrain rows={len(raw)} expected={EXPECTED_CANDIDATES}")
    if raw["candidate_cell_id"].astype(str).duplicated().any():
        raise ValueError("assembled terrain surface contains duplicate candidate IDs")
    if not set(raw["coarse_terrain_status"].astype(str)).issubset(STATUS_VOCAB):
        raise ValueError("assembled terrain surface contains unknown statuses")

    reference = (
        frozen_outer_frame()
        if reference_frame is None
        else reference_frame.copy().reset_index(drop=True)
    )
    if len(reference) != EXPECTED_CANDIDATES:
        raise ValueError("reference outer frame candidate count drift")
    reference_ids = reference["candidate_cell_id"].astype(str).tolist()
    raw_by_id = raw.set_index(raw["candidate_cell_id"].astype(str), drop=False)
    if set(raw_by_id.index) != set(reference_ids):
        raise ValueError("assembled terrain candidate ID set differs from frozen outer frame")
    ordered = raw_by_id.loc[reference_ids].reset_index(drop=True)
    if ordered["candidate_cell_id"].astype(str).tolist() != reference_ids:
        raise AssertionError("assembled terrain candidate order does not match frozen outer frame")
    for column in ("latitude", "longitude", "regional_tile_id"):
        left = reference[column].astype(str if column == "regional_tile_id" else float).reset_index(drop=True)
        right = ordered[column].astype(str if column == "regional_tile_id" else float).reset_index(drop=True)
        if not left.equals(right):
            raise ValueError(f"assembled terrain {column} differs from frozen outer frame")

    counts = ordered["coarse_terrain_status"].astype(str).value_counts().to_dict()
    provider_failure_tiles = sorted(
        ordered.loc[
            ordered["coarse_terrain_status"].astype(str).eq(PROVIDER_FAILURE),
            "regional_tile_id",
        ].astype(str).unique()
    )
    complete_n = int(counts.get(COMPLETE, 0))
    missing_n = int(counts.get(POINT_MISSING, 0))
    provider_failure_n = int(counts.get(PROVIDER_FAILURE, 0))

    output_csv = Path(output_csv)
    summary_json = Path(summary_json)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    summary_json.parent.mkdir(parents=True, exist_ok=True)
    ordered.to_csv(output_csv, index=False, compression="gzip")

    summary = {
        "schema_version": "cirsium-fresh-sentinel-v2-full-coarse-terrain-result-v1",
        "status": "FULL_49_TILE_COARSE_TERRAIN_EXECUTION_COMPLETE",
        "outer_frame_identity": "JP_PUBLIC_COUNTRY_BROAD_FRAME_V1",
        "intersecting_tile_count": EXPECTED_TILES,
        "points_per_tile": EXPECTED_POINTS_PER_TILE,
        "input_candidate_count": EXPECTED_CANDIDATES,
        "output_candidate_count": int(len(ordered)),
        "candidate_rows_dropped": 0,
        "exact_candidate_id_set_match": True,
        "exact_candidate_id_order_match": True,
        "complete_candidate_count": complete_n,
        "terrain_missing_candidate_count": missing_n,
        "provider_failure_candidate_count": provider_failure_n,
        "provider_failure_tile_count": int(len(provider_failure_tiles)),
        "provider_failure_tile_ids": provider_failure_tiles,
        "complete_fraction": float(complete_n / EXPECTED_CANDIDATES),
        "status_counts": {str(key): int(value) for key, value in sorted(counts.items())},
        "provider_failure_is_biological_negative": False,
        "terrain_missing_is_biological_negative": False,
        "stage3_source_execution_ready": len(provider_failure_tiles) == 0,
        "candidate_selection_added": False,
        "candidate_ranking_added": False,
        "structural_support_threshold_added": False,
        "focal_occurrence_prototypes_used": False,
        "private_exact_site_geometry_used": False,
        "p02_result_used": False,
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used": False,
        "human_access_used": False,
    }
    summary_json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    shard = sub.add_parser("shard")
    shard.add_argument("--shard-id", type=int, required=True)
    shard.add_argument("--output-dir", type=Path, required=True)

    assemble = sub.add_parser("assemble")
    assemble.add_argument("--input-root", type=Path, required=True)
    assemble.add_argument("--output-csv", type=Path, required=True)
    assemble.add_argument("--summary-json", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "shard":
        result = run_shard(args.shard_id, args.output_dir)
    elif args.command == "assemble":
        result = assemble_shards(args.input_root, args.output_csv, args.summary_json)
    else:
        raise AssertionError(args.command)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
