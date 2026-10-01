#!/usr/bin/env python3
"""Materialize fresh-SENTINEL v2 unioned 100-m fine frames around frozen seeds.

All seeds are projected into one shared Japan-centered AEQD coordinate system.
The fine frame is the union of cells on one global 100-m integer lattice whose
centers lie within 5 km of at least one seed. Units and source-state lanes remain
separate. No ecological source, graph score, access layer, budget, or field
outcome is used here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pyproj import CRS, Transformer

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_v2_fine_frame_geometry_v1.json"
UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
LANES = ("SOURCE_READY_COARSE_ORDER_COVER", "SOURCE_INDETERMINATE_GEOMETRY_ONLY_COVER")
GRID_M = 100.0
RADIUS_M = 5000.0
PROJ_STRING = "+proj=aeqd +lat_0=36 +lon_0=138 +datum=WGS84 +units=m +no_defs"


def _contract() -> dict[str, Any]:
    value = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if value.get("status") != "FROZEN_BEFORE_FINE_FRAME_MATERIALIZATION":
        raise ValueError("fine-frame geometry contract is not frozen")
    if float(value["grid"]["spacing_m"]) != GRID_M:
        raise ValueError("fine-frame grid spacing drifted")
    if float(value["seed_footprint"]["radius_km"]) * 1000.0 != RADIUS_M:
        raise ValueError("fine-frame radius drifted")
    if value["projection"]["proj_string"] != PROJ_STRING:
        raise ValueError("fine-frame projection drifted")
    return value


def _transformers() -> tuple[Transformer, Transformer]:
    crs = CRS.from_proj4(PROJ_STRING)
    return (
        Transformer.from_crs("EPSG:4326", crs, always_xy=True),
        Transformer.from_crs(crs, "EPSG:4326", always_xy=True),
    )


def _validate_seeds(seeds: pd.DataFrame, unit: str) -> None:
    required = {
        "cohort_unit_id", "seed_lane", "seed_order", "candidate_cell_id",
        "latitude", "longitude", "fine_expansion_radius_km",
    }
    missing = sorted(required.difference(seeds.columns))
    if missing:
        raise ValueError(f"{unit} seed table missing columns: {missing}")
    if seeds.empty:
        raise ValueError(f"{unit} seed table cannot be empty")
    if set(seeds["cohort_unit_id"].astype(str)) != {unit}:
        raise ValueError(f"{unit} seed table unit identity drifted")
    if not set(seeds["seed_lane"].astype(str)).issubset(set(LANES)):
        raise ValueError(f"{unit} seed table contains unknown lane")
    if not np.allclose(
        pd.to_numeric(seeds["fine_expansion_radius_km"], errors="raise").to_numpy(float),
        5.0, rtol=0.0, atol=0.0,
    ):
        raise ValueError(f"{unit} seed radius drifted")
    lat = pd.to_numeric(seeds["latitude"], errors="raise").to_numpy(float)
    lon = pd.to_numeric(seeds["longitude"], errors="raise").to_numpy(float)
    if not np.isfinite(lat).all() or not np.isfinite(lon).all():
        raise ValueError(f"{unit} seed coordinates must be finite")


def _cells_for_seed(x: float, y: float) -> set[tuple[int, int]]:
    min_col = math.floor((x - RADIUS_M) / GRID_M)
    max_col = math.floor((x + RADIUS_M) / GRID_M)
    min_row = math.floor((y - RADIUS_M) / GRID_M)
    max_row = math.floor((y + RADIUS_M) / GRID_M)
    cells: set[tuple[int, int]] = set()
    r2 = RADIUS_M * RADIUS_M
    for row in range(min_row, max_row + 1):
        cy = (row + 0.5) * GRID_M
        dy2 = (cy - y) ** 2
        if dy2 > r2:
            continue
        for col in range(min_col, max_col + 1):
            cx = (col + 0.5) * GRID_M
            if (cx - x) ** 2 + dy2 <= r2 + 1e-9:
                cells.add((row, col))
    return cells


def materialize_unit_fine_frame(
    seeds: pd.DataFrame,
    unit: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    _contract()
    _validate_seeds(seeds, unit)
    forward, inverse = _transformers()
    outputs: list[pd.DataFrame] = []
    lane_summary: dict[str, Any] = {}

    for lane in LANES:
        subset = seeds.loc[seeds["seed_lane"].astype(str).eq(lane)].copy()
        if subset.empty:
            raise ValueError(f"{unit} lane has no seeds: {lane}")
        xs, ys = forward.transform(
            pd.to_numeric(subset["longitude"], errors="raise").to_numpy(float),
            pd.to_numeric(subset["latitude"], errors="raise").to_numpy(float),
        )
        union: set[tuple[int, int]] = set()
        raw_memberships = 0
        for x, y in zip(xs, ys):
            cells = _cells_for_seed(float(x), float(y))
            raw_memberships += len(cells)
            union.update(cells)

        ordered = sorted(union)
        rows = np.asarray([r for r, _ in ordered], dtype=np.int64)
        cols = np.asarray([c for _, c in ordered], dtype=np.int64)
        center_x = (cols.astype(float) + 0.5) * GRID_M
        center_y = (rows.astype(float) + 0.5) * GRID_M
        lon, lat = inverse.transform(center_x, center_y)
        lane_frame = pd.DataFrame({
            "cohort_unit_id": unit,
            "fine_frame_lane": lane,
            "grid_row": rows,
            "grid_col": cols,
            "projected_x_m": center_x,
            "projected_y_m": center_y,
            "longitude": np.asarray(lon, dtype=float),
            "latitude": np.asarray(lat, dtype=float),
        })
        lane_frame["fine_cell_id"] = [
            f"{unit}:{lane}:r{int(row)}:c{int(col)}"
            for row, col in zip(rows, cols)
        ]
        if lane_frame[["grid_row", "grid_col"]].duplicated().any():
            raise AssertionError(f"{unit} {lane} union contains duplicate grid cells")
        outputs.append(lane_frame)
        lane_summary[lane] = {
            "seed_count": int(len(subset)),
            "raw_seed_cell_memberships": int(raw_memberships),
            "unioned_fine_cell_count": int(len(lane_frame)),
            "overlap_memberships_removed": int(raw_memberships - len(lane_frame)),
            "grid_pair_unique": True,
        }

    combined = pd.concat(outputs, ignore_index=True)
    if combined["fine_cell_id"].duplicated().any():
        raise AssertionError(f"{unit} fine_cell_id must be unique across separated lanes")
    return combined, {
        "cohort_unit_id": unit,
        "projection_identity": "JAPAN_CENTERED_AEQD_V1",
        "grid_spacing_m": GRID_M,
        "seed_radius_m": RADIUS_M,
        "lanes_kept_separate": True,
        "lane_results": lane_summary,
        "total_fine_cell_count": int(len(combined)),
        "ecological_sources_attached": False,
        "structural_graph_computed": False,
        "candidate_ranking_added": False,
        "access_or_roads_used": False,
        "budget_used": False,
        "field_outcomes_used": False,
    }


def build_all_fine_frames(
    seed_tables: dict[str, pd.DataFrame],
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    if set(seed_tables) != set(UNITS):
        raise ValueError("fine-frame seed unit set drifted")
    frames: dict[str, pd.DataFrame] = {}
    summaries: dict[str, Any] = {}
    for unit in UNITS:
        frame, summary = materialize_unit_fine_frame(seed_tables[unit], unit)
        frames[unit] = frame
        summaries[unit] = summary
    return frames, {
        "schema_version": "cirsium-fresh-sentinel-v2-fine-frame-materialization-result-v1",
        "status": "UNIONED_100M_FINE_FRAMES_MATERIALIZED_PRE_OUTCOME",
        "projection_identity": "JAPAN_CENTERED_AEQD_V1",
        "grid_spacing_m": GRID_M,
        "seed_radius_m": RADIUS_M,
        "unit_results": summaries,
        "units_merged": False,
        "lanes_merged": False,
        "ecological_sources_attached": False,
        "structural_graph_computed": False,
        "candidate_ranking_added": False,
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used": False,
        "private_exact_site_geometry_used": False,
        "p02_result_used": False,
        "human_access_used": False,
        "budget_used": False,
        "next_gate": "Freeze fine-frame counts/hashes, then attach fine public ecological sources before constructing the frozen 100-m structural graph.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", action="append", required=True, help="UNIT=path.csv.gz")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    seed_tables: dict[str, pd.DataFrame] = {}
    for spec in args.seeds:
        unit, path = spec.split("=", 1)
        seed_tables[unit] = pd.read_csv(path, low_memory=False)
    frames, summary = build_all_fine_frames(seed_tables)
    out = args.out_dir
    if out.exists():
        raise ValueError("refusing to overwrite fine-frame output directory")
    out.mkdir(parents=True)
    hashes = {}
    for unit, frame in frames.items():
        path = out / f"{unit}_fine_frame_100m.csv.gz"
        frame.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0})
        hashes[unit] = hashlib.sha256(path.read_bytes()).hexdigest()
    summary["private_fine_frame_sha256_by_unit"] = hashes
    path = out / "summary.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
