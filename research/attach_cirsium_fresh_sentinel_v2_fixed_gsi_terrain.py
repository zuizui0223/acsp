#!/usr/bin/env python3
"""Attach GSI terrain to fresh-SENTINEL v2 primary fine grids under a fixed policy.

The 40-km chunk lattice, phase, margin, source priority and max-tile limit are
part of the frozen source semantics. Every input fine-grid row is retained with
an explicit GSI source state. Provider/source gaps are never recoded as
ecological zero or biological absence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from research.build_cirsium_private_alpine_local_grid_v1 import _sample_terrain

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_v2_fixed_gsi_terrain_policy_v1.json"
UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
TERRAIN_COLUMNS = ("elev", "slope100", "tpi300", "rough300")


def _inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT.resolve())
        return True
    except ValueError:
        return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _feature_digest(frame: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    columns = ["candidate_cell_id", "gsi_attribution", *TERRAIN_COLUMNS]
    ordered = frame[columns].sort_values("candidate_cell_id", kind="mergesort")
    for row in ordered.itertuples(index=False, name=None):
        values = []
        for value in row:
            if isinstance(value, (float, np.floating)):
                values.append(f"{float(value):.8f}")
            else:
                values.append(str(value))
        digest.update(("\t".join(values) + "\n").encode("utf-8"))
    return digest.hexdigest()


def _load_contract() -> dict[str, Any]:
    value = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if value.get("status") != "FROZEN_BEFORE_FINE_GSI_TERRAIN_ATTACHMENT":
        raise ValueError("fixed GSI terrain policy is not frozen")
    if tuple(value.get("cohort_unit_ids") or ()) != UNITS:
        raise ValueError("GSI terrain cohort drifted")
    chunk = value["chunk_policy"]
    if int(chunk["physical_chunk_width_m"]) != 40000:
        raise ValueError("GSI chunk width drifted")
    if int(chunk["fine_grid_spacing_m"]) != 100 or int(chunk["chunk_grid_cells"]) != 400:
        raise ValueError("GSI fine chunk geometry drifted")
    if list(chunk["shared_grid_phase_offset_cells"]) != [0, 0]:
        raise ValueError("GSI chunk phase drifted")
    if float(chunk["chunk_margin_degrees"]) != 0.02:
        raise ValueError("GSI chunk margin drifted")
    if int(chunk["max_gsi_tiles_per_chunk"]) != 900:
        raise ValueError("GSI max-tile cap drifted")
    if int(chunk["reference_points_per_chunk_max"]) != 8:
        raise ValueError("GSI reference-point rule drifted")
    return value


def _chunk_groups(frame: pd.DataFrame, chunk_cells: int) -> list[pd.DataFrame]:
    work = frame.copy()
    work["_input_order"] = np.arange(len(work), dtype=np.int64)
    work["_chunk_row"] = work["grid_row"].astype(np.int64) // int(chunk_cells)
    work["_chunk_col"] = work["grid_col"].astype(np.int64) // int(chunk_cells)
    return [
        group.drop(columns=["_chunk_row", "_chunk_col"]).copy().reset_index(drop=True)
        for _, group in work.groupby(["_chunk_row", "_chunk_col"], sort=True)
    ]


def _references(component: pd.DataFrame, maximum: int) -> tuple[tuple[float, float], ...]:
    ordered = component.sort_values(["grid_row", "grid_col"], kind="mergesort").reset_index(drop=True)
    step = max(1, len(ordered) // int(maximum))
    sampled = ordered.iloc[::step].head(int(maximum))
    return tuple(
        (float(row.latitude), float(row.longitude))
        for row in sampled.itertuples(index=False)
    )


def attach_fixed_gsi_terrain(
    fine_grid: pd.DataFrame,
    *,
    unit_id: str,
    cache_dir: Path,
    dem_builder: Callable[..., tuple[str | None, str]] | None = None,
    terrain_sampler: Callable[[pd.DataFrame, Path], pd.DataFrame] | None = None,
    numerical_probe: Callable[..., None] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    contract = _load_contract()
    if unit_id not in UNITS:
        raise ValueError(f"unknown fresh-SENTINEL v2 unit: {unit_id}")
    required = {
        "candidate_cell_id",
        "cohort_unit_id",
        "grid_row",
        "grid_col",
        "latitude",
        "longitude",
    }
    missing = sorted(required.difference(fine_grid.columns))
    if missing:
        raise ValueError(f"primary fine grid missing columns: {missing}")
    if fine_grid.empty:
        raise ValueError("primary fine grid cannot be empty")
    if set(fine_grid["cohort_unit_id"].astype(str)) != {unit_id}:
        raise ValueError("primary fine-grid unit identity drifted")
    if fine_grid["candidate_cell_id"].astype(str).duplicated().any():
        raise ValueError("primary fine-grid candidate IDs must be unique")

    cache_dir = Path(cache_dir).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["GBIF_FIELDMAP_CACHE"] = str(cache_dir)
    if dem_builder is None:
        from gbif_fieldmap_builder_app import build_gsi_dem_for_bounds
        dem_builder = build_gsi_dem_for_bounds
    sampler = terrain_sampler or _sample_terrain

    chunk = contract["chunk_policy"]
    pieces: list[pd.DataFrame] = []
    audits: list[dict[str, Any]] = []

    groups = _chunk_groups(fine_grid, int(chunk["chunk_grid_cells"]))
    for chunk_index, component in enumerate(groups):
        west = float(component["longitude"].min()) - float(chunk["chunk_margin_degrees"])
        east = float(component["longitude"].max()) + float(chunk["chunk_margin_degrees"])
        south = float(component["latitude"].min()) - float(chunk["chunk_margin_degrees"])
        north = float(component["latitude"].max()) + float(chunk["chunk_margin_degrees"])
        refs = _references(component, int(chunk["reference_points_per_chunk_max"]))

        dem_path, attribution = dem_builder(
            (west, south, east, north),
            refs,
            max_tiles=int(chunk["max_gsi_tiles_per_chunk"]),
        )

        out = component.copy()
        out["gsi_source_state"] = "INDETERMINATE_GSI_PROVIDER_UNAVAILABLE"
        out["gsi_attribution"] = str(attribution or "")
        for column in TERRAIN_COLUMNS:
            out[column] = np.nan

        if not dem_path:
            audits.append(
                {
                    "chunk_index": int(chunk_index),
                    "candidate_rows_input": int(len(component)),
                    "source_complete_rows": 0,
                    "provider_unavailable_rows": int(len(component)),
                    "terrain_vector_unavailable_rows": 0,
                    "gsi_attribution": "",
                    "status": "INDETERMINATE_GSI_PROVIDER_UNAVAILABLE",
                }
            )
            pieces.append(out)
            continue

        try:
            sampled = sampler(component.drop(columns=["_input_order"]), Path(dem_path))
        except ValueError as exc:
            if "no annular candidate cell has complete terrain support" not in str(exc):
                raise
            out["gsi_source_state"] = "INDETERMINATE_TERRAIN_VECTOR_UNAVAILABLE"
            audits.append(
                {
                    "chunk_index": int(chunk_index),
                    "candidate_rows_input": int(len(component)),
                    "source_complete_rows": 0,
                    "provider_unavailable_rows": 0,
                    "terrain_vector_unavailable_rows": int(len(component)),
                    "gsi_attribution": str(attribution or ""),
                    "status": "INDETERMINATE_TERRAIN_VECTOR_UNAVAILABLE",
                }
            )
            pieces.append(out)
            continue

        # An optional read-only diagnostic repeats selected original samples
        # against this *same* resolved mosaic; its output never changes the
        # primary sampled rows or their frozen source/selection semantics.
        if numerical_probe is not None:
            numerical_probe(
                chunk_index,
                len(groups),
                component.drop(columns=["_input_order"]).copy(),
                sampled.copy(),
                Path(dem_path),
                sampler,
            )
        sampled_by_id = sampled.set_index(sampled["candidate_cell_id"].astype(str))
        complete_ids = set(sampled_by_id.index)
        complete = out["candidate_cell_id"].astype(str).isin(complete_ids)
        out.loc[complete, "gsi_source_state"] = "SOURCE_COMPLETE"
        out.loc[~complete, "gsi_source_state"] = "INDETERMINATE_TERRAIN_VECTOR_UNAVAILABLE"
        ids = out.loc[complete, "candidate_cell_id"].astype(str)
        for column in TERRAIN_COLUMNS:
            if column not in sampled_by_id.columns:
                raise AssertionError(f"terrain sampler omitted frozen column: {column}")
            out.loc[complete, column] = sampled_by_id.loc[ids, column].to_numpy(float)

        complete_n = int(complete.sum())
        unavailable_n = int((~complete).sum())
        audits.append(
            {
                "chunk_index": int(chunk_index),
                "candidate_rows_input": int(len(component)),
                "source_complete_rows": complete_n,
                "provider_unavailable_rows": 0,
                "terrain_vector_unavailable_rows": unavailable_n,
                "gsi_attribution": str(attribution or ""),
                "status": "SOURCE_ACQUIRED",
            }
        )
        pieces.append(out)

    merged = pd.concat(pieces, ignore_index=True)
    merged = merged.sort_values("_input_order", kind="mergesort").drop(columns=["_input_order"]).reset_index(drop=True)
    if len(merged) != len(fine_grid):
        raise AssertionError("fixed GSI attachment changed candidate denominator")
    if merged["candidate_cell_id"].astype(str).tolist() != fine_grid["candidate_cell_id"].astype(str).tolist():
        raise AssertionError("fixed GSI attachment changed candidate identity/order")

    states = merged["gsi_source_state"].astype(str)
    source_complete = int(states.eq("SOURCE_COMPLETE").sum())
    provider_unavailable = int(states.eq("INDETERMINATE_GSI_PROVIDER_UNAVAILABLE").sum())
    vector_unavailable = int(states.eq("INDETERMINATE_TERRAIN_VECTOR_UNAVAILABLE").sum())
    if source_complete + provider_unavailable + vector_unavailable != len(merged):
        raise AssertionError("GSI source states do not preserve denominator")

    complete_frame = merged.loc[states.eq("SOURCE_COMPLETE")].copy()
    if source_complete and complete_frame[list(TERRAIN_COLUMNS)].isna().any().any():
        raise AssertionError("source-complete GSI rows have missing frozen terrain")
    if (~states.eq("SOURCE_COMPLETE")).any() and merged.loc[
        ~states.eq("SOURCE_COMPLETE"), list(TERRAIN_COLUMNS)
    ].notna().any().any():
        raise AssertionError("source-indeterminate GSI rows carry partial terrain features")

    feature_digest = (
        _feature_digest(complete_frame)
        if not complete_frame.empty
        else hashlib.sha256(b"").hexdigest()
    )
    summary = {
        "schema_version": "cirsium-fresh-sentinel-v2-fixed-gsi-terrain-result-v1",
        "status": "FIXED_GSI_TERRAIN_ATTACHED_PRE_OUTCOME",
        "cohort_unit_id": unit_id,
        "candidate_rows": int(len(merged)),
        "source_complete_rows": source_complete,
        "source_complete_fraction": float(source_complete / len(merged)),
        "provider_unavailable_rows": provider_unavailable,
        "terrain_vector_unavailable_rows": vector_unavailable,
        "candidate_denominator_preserved": True,
        "chunk_count": int(len(audits)),
        "physical_chunk_width_m": int(chunk["physical_chunk_width_m"]),
        "chunk_grid_cells": int(chunk["chunk_grid_cells"]),
        "chunk_phase_offset_cells": list(chunk["shared_grid_phase_offset_cells"]),
        "chunk_margin_degrees": float(chunk["chunk_margin_degrees"]),
        "max_gsi_tiles_per_chunk": int(chunk["max_gsi_tiles_per_chunk"]),
        "attributions": sorted(
            set(str(value) for value in merged["gsi_attribution"].astype(str) if str(value))
        ),
        "terrain_feature_digest_sha256": feature_digest,
        "source_indeterminate_recoded_as_absence": False,
        "source_indeterminate_recoded_as_zero_support": False,
        "field_outcomes_opened": False,
        "structural_graph_computed": False,
        "candidate_ranking_computed": False,
        "exact_coordinates_public": False,
        "chunk_audits": audits,
    }
    return merged, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-id", choices=UNITS, required=True)
    parser.add_argument("--fine-grid-csv-gz", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--private-out-csv-gz", type=Path, required=True)
    parser.add_argument("--public-safe-summary-json", type=Path, required=True)
    parser.add_argument(
        "--same-mosaic-numerical-diagnostic-json",
        type=Path,
        help="Optional read-only pre-outcome sampled DEM replay summary without candidate IDs",
    )
    args = parser.parse_args()

    if not args.fine_grid_csv_gz.is_file():
        raise SystemExit(f"missing primary fine grid: {args.fine_grid_csv_gz}")
    if _inside_repo(args.private_out_csv_gz):
        raise SystemExit("refusing to write coordinate-bearing GSI output inside repository")
    if args.private_out_csv_gz.exists() or args.public_safe_summary_json.exists():
        raise SystemExit("refusing to overwrite fixed GSI terrain outputs")
    if args.same_mosaic_numerical_diagnostic_json is not None and args.same_mosaic_numerical_diagnostic_json.exists():
        raise SystemExit("refusing to overwrite numerical diagnostic")

    fine_grid = pd.read_csv(args.fine_grid_csv_gz, low_memory=False)
    collector = None
    if args.same_mosaic_numerical_diagnostic_json is not None:
        from research.audit_cirsium_fresh_sentinel_v2_same_mosaic_numerical_replay import (
            SameMosaicReplayCollector,
        )
        collector = SameMosaicReplayCollector()
    audited, summary = attach_fixed_gsi_terrain(
        fine_grid,
        unit_id=args.unit_id,
        cache_dir=args.cache_dir,
        numerical_probe=collector,
    )
    args.private_out_csv_gz.parent.mkdir(parents=True, exist_ok=True)
    args.public_safe_summary_json.parent.mkdir(parents=True, exist_ok=True)
    audited.to_csv(
        args.private_out_csv_gz,
        index=False,
        compression={"method": "gzip", "mtime": 0},
    )
    summary["private_gsi_frame_sha256"] = _sha256(args.private_out_csv_gz)
    args.public_safe_summary_json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
