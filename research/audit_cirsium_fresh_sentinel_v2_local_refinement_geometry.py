#!/usr/bin/env python3
"""Audit fresh-SENTINEL v2 local-refinement geometry before fine ecology.

For each unit, select the already-frozen top 2.5% source-ready coarse candidates,
restore their exact coordinates from the frozen full-terrain artifact, and compute
only the union geometry of the pre-frozen 5-km / 100-m Japan-centered AEQD grid.

No fine ecological source, structural graph, access layer, field outcome or private
exact site is opened. The candidate-level fine grid is never written; only counts
and a SHA-256 over sorted packed global grid IDs are emitted.
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
CONTRACT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_v2_local_refinement_geometry_feasibility_v1.json"

UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
READY = "SOURCE_READY_FOR_FAMILY_COARSE_STAGE"
EXPECTED_CANDIDATES = 39_200
CENTER_FRACTION = 0.025
GRID_M = 100.0
RADIUS_M = 5000.0
PROJ_STRING = "+proj=aeqd +lat_0=36 +lon_0=138 +datum=WGS84 +units=m +no_defs"


def _contract() -> dict[str, Any]:
    value = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if value.get("status") != "FROZEN_BEFORE_LOCAL_REFINEMENT_GEOMETRY_EXECUTION":
        raise ValueError("local-refinement geometry contract is not frozen")
    centers = value.get("refinement_centers", {})
    geom = value.get("fine_geometry", {})
    if float(centers.get("fraction", -1)) != CENTER_FRACTION:
        raise ValueError("refinement-center fraction drifted")
    if float(geom.get("grid_spacing_m", -1)) != GRID_M:
        raise ValueError("fine-grid spacing drifted")
    if float(geom.get("window_radius_km", -1)) * 1000.0 != RADIUS_M:
        raise ValueError("fine-window radius drifted")
    if str(geom.get("proj_string")) != PROJ_STRING:
        raise ValueError("fine-grid projection drifted")
    return value


def _forward_transformer() -> Transformer:
    return Transformer.from_crs(
        "EPSG:4326",
        CRS.from_proj4(PROJ_STRING),
        always_xy=True,
    )


def _pack_grid_ids(rows: np.ndarray, cols: np.ndarray) -> np.ndarray:
    """Pack signed int32 row/col into deterministic uint64 IDs."""
    r = np.asarray(rows, dtype=np.int64)
    c = np.asarray(cols, dtype=np.int64)
    if ((r < np.iinfo(np.int32).min) | (r > np.iinfo(np.int32).max)).any():
        raise ValueError("grid row exceeds signed int32 range")
    if ((c < np.iinfo(np.int32).min) | (c > np.iinfo(np.int32).max)).any():
        raise ValueError("grid col exceeds signed int32 range")
    ru = r.astype(np.int32, copy=False).view(np.uint32).astype(np.uint64)
    cu = c.astype(np.int32, copy=False).view(np.uint32).astype(np.uint64)
    return (ru << np.uint64(32)) | cu


def _cells_for_projected_center(x_m: float, y_m: float) -> np.ndarray:
    min_col = math.floor((float(x_m) - RADIUS_M) / GRID_M)
    max_col = math.floor((float(x_m) + RADIUS_M) / GRID_M)
    min_row = math.floor((float(y_m) - RADIUS_M) / GRID_M)
    max_row = math.floor((float(y_m) + RADIUS_M) / GRID_M)

    rows = np.arange(min_row, max_row + 1, dtype=np.int64)
    cols = np.arange(min_col, max_col + 1, dtype=np.int64)
    yy = (rows.astype(float) + 0.5) * GRID_M
    xx = (cols.astype(float) + 0.5) * GRID_M
    dy2 = np.square(yy - float(y_m))
    dx2 = np.square(xx - float(x_m))
    mask = dy2[:, None] + dx2[None, :] <= (RADIUS_M * RADIUS_M + 1e-9)
    rr, cc = np.nonzero(mask)
    return _pack_grid_ids(rows[rr], cols[cc])


def _select_centers(
    order: pd.DataFrame,
    terrain: pd.DataFrame,
    unit: str,
    *,
    production: bool,
) -> pd.DataFrame:
    required_order = {"candidate_cell_id", "source_state", "coarse_evidence_rank"}
    required_terrain = {"candidate_cell_id", "latitude", "longitude", "regional_tile_id"}
    missing_o = sorted(required_order.difference(order.columns))
    missing_t = sorted(required_terrain.difference(terrain.columns))
    if missing_o:
        raise ValueError(f"{unit} coarse order missing columns: {missing_o}")
    if missing_t:
        raise ValueError(f"frozen terrain artifact missing columns: {missing_t}")
    if len(order) != len(terrain):
        raise ValueError(f"{unit} order/terrain row count mismatch")
    if production and len(order) != EXPECTED_CANDIDATES:
        raise ValueError(f"{unit} production denominator must contain 39,200 rows")

    o = order.reset_index(drop=True).copy()
    t = terrain.reset_index(drop=True).copy()
    if o["candidate_cell_id"].astype(str).tolist() != t["candidate_cell_id"].astype(str).tolist():
        raise ValueError(f"{unit} coarse order and frozen terrain candidate identity/order differ")

    ready = o["source_state"].astype(str).eq(READY)
    ready_frame = pd.DataFrame({
        "candidate_cell_id": o.loc[ready, "candidate_cell_id"].astype(str).to_numpy(),
        "coarse_evidence_rank": pd.to_numeric(
            o.loc[ready, "coarse_evidence_rank"], errors="raise"
        ).astype(int).to_numpy(),
        "latitude": pd.to_numeric(t.loc[ready, "latitude"], errors="raise").to_numpy(float),
        "longitude": pd.to_numeric(t.loc[ready, "longitude"], errors="raise").to_numpy(float),
        "regional_tile_id": t.loc[ready, "regional_tile_id"].astype(str).to_numpy(),
    })
    ready_frame = ready_frame.sort_values("coarse_evidence_rank", kind="mergesort").reset_index(drop=True)
    if ready_frame["coarse_evidence_rank"].tolist() != list(range(1, len(ready_frame) + 1)):
        raise ValueError(f"{unit} source-ready coarse order is not complete 1..N")
    if not np.isfinite(ready_frame[["latitude", "longitude"]].to_numpy(float)).all():
        raise ValueError(f"{unit} source-ready center coordinates must be finite")

    retain_n = int(math.ceil(CENTER_FRACTION * len(ready_frame)))
    if retain_n < 1:
        raise ValueError(f"{unit} source-ready tier is empty")
    return ready_frame.iloc[:retain_n].copy().reset_index(drop=True)


def audit_unit_geometry(
    order: pd.DataFrame,
    terrain: pd.DataFrame,
    unit: str,
    *,
    production: bool = False,
) -> dict[str, Any]:
    centers = _select_centers(order, terrain, unit, production=production)
    transformer = _forward_transformer()
    xs, ys = transformer.transform(
        centers["longitude"].to_numpy(float),
        centers["latitude"].to_numpy(float),
    )

    chunks: list[np.ndarray] = []
    raw_memberships = 0
    per_center_counts: list[int] = []
    for x_m, y_m in zip(xs, ys):
        ids = _cells_for_projected_center(float(x_m), float(y_m))
        raw_memberships += int(len(ids))
        per_center_counts.append(int(len(ids)))
        chunks.append(ids)

    all_ids = np.concatenate(chunks) if chunks else np.empty(0, dtype=np.uint64)
    unique_ids = np.unique(all_ids)
    if len(unique_ids) == 0:
        raise AssertionError(f"{unit} local-refinement union is unexpectedly empty")
    packed_le = unique_ids.astype("<u8", copy=False)
    grid_hash = hashlib.sha256(packed_le.tobytes()).hexdigest()

    center_ids = "\n".join(centers["candidate_cell_id"].astype(str).tolist()).encode("utf-8")
    return {
        "cohort_unit_id": unit,
        "source_ready_candidate_count": int(
            order["source_state"].astype(str).eq(READY).sum()
        ),
        "selected_coarse_center_count": int(len(centers)),
        "center_fraction": CENTER_FRACTION,
        "center_candidate_id_sha256": hashlib.sha256(center_ids).hexdigest(),
        "raw_seed_to_cell_membership_count": int(raw_memberships),
        "unique_unioned_fine_cell_count": int(len(unique_ids)),
        "overlap_memberships_removed": int(raw_memberships - len(unique_ids)),
        "overlap_fraction_of_raw_memberships": float(
            (raw_memberships - len(unique_ids)) / raw_memberships
        ) if raw_memberships else 0.0,
        "union_area_km2": float(len(unique_ids) * (GRID_M * GRID_M) / 1_000_000.0),
        "median_cells_per_center_before_union": float(np.median(per_center_counts)),
        "minimum_cells_per_center_before_union": int(min(per_center_counts)),
        "maximum_cells_per_center_before_union": int(max(per_center_counts)),
        "sorted_packed_global_grid_id_sha256": grid_hash,
        "grid_rows_written": False,
        "ecological_sources_attached": False,
        "structural_graph_computed": False,
        "field_outcomes_used": False,
    }


def run_all(
    orders: dict[str, pd.DataFrame],
    terrain: pd.DataFrame,
) -> dict[str, Any]:
    _contract()
    if set(orders) != set(UNITS):
        raise ValueError("unit set drifted")
    if len(terrain) != EXPECTED_CANDIDATES:
        raise ValueError("frozen terrain artifact must contain exactly 39,200 rows")
    unit_results = {
        unit: audit_unit_geometry(orders[unit], terrain, unit, production=True)
        for unit in UNITS
    }
    return {
        "schema_version": "cirsium-fresh-sentinel-v2-local-refinement-geometry-feasibility-result-v1",
        "status": "LOCAL_REFINEMENT_GEOMETRY_FEASIBILITY_COMPLETE",
        "projection_identity": "JAPAN_CENTERED_AEQD_V1",
        "grid_spacing_m": GRID_M,
        "window_radius_km": RADIUS_M / 1000.0,
        "center_fraction": CENTER_FRACTION,
        "unit_results": unit_results,
        "source_indeterminate_fine_expanded": False,
        "field_outcomes_opened": False,
        "recovery_used": False,
        "ecological_sources_attached": False,
        "structural_graph_computed": False,
        "promotion_gate": False,
        "next_gate": "Interpret geometry size only; do not tune 0.025, 5 km or 100 m from these counts.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terrain-csv-gz", type=Path, required=True)
    parser.add_argument("--order", action="append", required=True, help="UNIT=path.csv.gz")
    parser.add_argument("--out-json", type=Path, required=True)
    args = parser.parse_args()

    terrain = pd.read_csv(args.terrain_csv_gz, low_memory=False)
    orders: dict[str, pd.DataFrame] = {}
    for spec in args.order:
        unit, path = spec.split("=", 1)
        orders[unit] = pd.read_csv(path, low_memory=False)

    result = run_all(orders, terrain)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
