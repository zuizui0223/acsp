#!/usr/bin/env python3
"""Attach coarse public terrain primitives to the frozen fresh-SENTINEL v2 outer frame.

This stage reuses the same terrain extractor already used by ACSP's frozen global
adapter. It is deliberately attachment-only: every outer-frame row is retained,
no candidate/tile ranking or filtering is performed, and the resulting fields are
kept distinct from the later 100 m regular-grid structural graph primitives.

Coordinate-bearing enriched output must remain outside the public repository.
The public-safe summary contains only aggregate completeness/provenance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from acsp.taxon_patches import RAW_TERRAIN_FEATURES

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_v2_terrain_attachment_v1.json"
OUTER_FRAME_CONTRACT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_v2.json"
COARSE_PREFIX = "coarse_"
EXPECTED_OUTER_FRAME_IDENTITY = "JP_PUBLIC_COUNTRY_BROAD_FRAME_V1"
EXPECTED_TERRAIN_SOURCE_IDENTITY = "GLOBAL_ADAPTER_EXISTING_EXTRACT_ENVIRONMENT_V1"
RESOLUTION_ARGUMENT = "2.5m"


def _inside_repo(path: Path, repo_root: Path | None = None) -> bool:
    root = ROOT if repo_root is None else Path(repo_root)
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _validate_outer_frame(frame: pd.DataFrame) -> None:
    required = {
        "candidate_cell_id",
        "latitude",
        "longitude",
        "regional_tile_id",
        "outer_frame_identity",
        "field_outcomes_used",
        "private_exact_site_geometry_used",
        "occurrence_selected_tile",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"fresh-SENTINEL v2 outer frame missing columns: {missing}")
    if frame.empty:
        raise ValueError("fresh-SENTINEL v2 outer frame cannot be empty")
    if frame["candidate_cell_id"].isna().any() or frame["candidate_cell_id"].astype(str).duplicated().any():
        raise ValueError("candidate_cell_id must be complete and unique")
    if set(frame["outer_frame_identity"].astype(str)) != {EXPECTED_OUTER_FRAME_IDENTITY}:
        raise ValueError("outer frame identity drifted")
    for column in ("field_outcomes_used", "private_exact_site_geometry_used", "occurrence_selected_tile"):
        if frame[column].astype(str).str.lower().isin({"true", "1", "yes"}).any():
            raise ValueError(f"outer frame violates pre-outcome boundary: {column}")
    for column, lower, upper in (("latitude", -90.0, 90.0), ("longitude", -180.0, 180.0)):
        values = pd.to_numeric(frame[column], errors="coerce").to_numpy(float)
        if not np.isfinite(values).all() or ((values < lower) | (values > upper)).any():
            raise ValueError(f"outer-frame {column} must be finite and valid")


def attach_coarse_terrain(
    frame: pd.DataFrame,
    *,
    extractor: Callable[..., pd.DataFrame] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Attach coarse terrain without dropping, ranking or filtering rows."""
    _validate_outer_frame(frame)
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    outer = json.loads(OUTER_FRAME_CONTRACT.read_text(encoding="utf-8"))
    if contract.get("status") != "FROZEN_BEFORE_TERRAIN_ATTACHMENT_EXECUTION":
        raise ValueError("terrain attachment contract is not pre-execution frozen")
    if outer.get("status") != "FROZEN_BEFORE_PUBLIC_BROAD_FRAME_EXECUTION":
        raise ValueError("fresh-SENTINEL v2 outer-frame contract drifted")
    if tuple(contract.get("raw_terrain_features") or ()) != tuple(RAW_TERRAIN_FEATURES):
        raise ValueError("terrain attachment feature list drifted")

    if extractor is None:
        from gbif_fieldmap_builder_app import extract_environment
        extractor = extract_environment

    base = frame.copy().reset_index(drop=True)
    enriched = extractor(
        base.copy(),
        list(RAW_TERRAIN_FEATURES),
        "latitude",
        "longitude",
        RESOLUTION_ARGUMENT,
    )
    if len(enriched) != len(base):
        raise ValueError("terrain extractor changed outer-frame row count")
    if "candidate_cell_id" not in enriched.columns:
        enriched.insert(0, "candidate_cell_id", base["candidate_cell_id"].astype(str).to_numpy())
    if enriched["candidate_cell_id"].astype(str).tolist() != base["candidate_cell_id"].astype(str).tolist():
        raise ValueError("terrain extractor changed candidate order or identity")

    output = base.copy()
    completeness: dict[str, float] = {}
    complete_mask = np.ones(len(output), dtype=bool)
    for feature in RAW_TERRAIN_FEATURES:
        if feature not in enriched.columns:
            raise ValueError(f"terrain extractor omitted frozen feature: {feature}")
        values = pd.to_numeric(enriched[feature], errors="coerce").to_numpy(float)
        finite = np.isfinite(values)
        completeness[feature] = float(finite.mean())
        complete_mask &= finite
        output[f"{COARSE_PREFIX}{feature}"] = values

    tile_counts = (
        output.assign(_complete=complete_mask)
        .groupby("regional_tile_id", sort=True)
        .agg(candidate_count=("candidate_cell_id", "size"), complete_terrain_count=("_complete", "sum"))
        .reset_index()
    )
    tile_counts["complete_fraction"] = (
        tile_counts["complete_terrain_count"].astype(float) / tile_counts["candidate_count"].astype(float)
    )

    summary = {
        "schema_version": "cirsium-fresh-sentinel-v2-terrain-attachment-v1",
        "status": "COARSE_PUBLIC_TERRAIN_ATTACHED_PRE_OUTCOME",
        "outer_frame_identity": EXPECTED_OUTER_FRAME_IDENTITY,
        "terrain_source_identity": EXPECTED_TERRAIN_SOURCE_IDENTITY,
        "raw_terrain_features": list(RAW_TERRAIN_FEATURES),
        "output_columns": [f"{COARSE_PREFIX}{feature}" for feature in RAW_TERRAIN_FEATURES],
        "candidate_count_before": int(len(base)),
        "candidate_count_after": int(len(output)),
        "rows_dropped": 0,
        "candidate_order_changed": False,
        "tile_count": int(output["regional_tile_id"].astype(str).nunique()),
        "per_feature_finite_fraction": completeness,
        "all_feature_complete_count": int(complete_mask.sum()),
        "all_feature_complete_fraction": float(complete_mask.mean()),
        "tiles_with_any_complete_terrain": int((tile_counts["complete_terrain_count"] > 0).sum()),
        "tiles_with_all_candidates_complete": int(
            (tile_counts["complete_terrain_count"] == tile_counts["candidate_count"]).sum()
        ),
        "rank_candidates": False,
        "select_tiles": False,
        "select_candidates": False,
        "structural_graph_applied": False,
        "private_exact_site_geometry_used": False,
        "occurrence_selected_tiles": False,
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used": False,
        "human_access_used": False,
        "budget_used": False,
        "coarse_fields_are_100m_structural_fields": False,
        "next_gate": "Attach public WorldCover coarse primitives to the same unchanged outer-frame rows.",
    }
    return output, summary


def run(
    outer_frame_csv: Path,
    private_out_csv: Path,
    public_safe_summary_json: Path,
) -> dict[str, Any]:
    outer_frame_csv = Path(outer_frame_csv).resolve()
    private_out_csv = Path(private_out_csv).resolve()
    public_safe_summary_json = Path(public_safe_summary_json).resolve()
    if not outer_frame_csv.is_file():
        raise ValueError(f"missing frozen v2 outer-frame CSV: {outer_frame_csv}")
    if _inside_repo(private_out_csv):
        raise ValueError("coordinate-bearing terrain output must remain outside the public repository")
    if private_out_csv.exists() or public_safe_summary_json.exists():
        raise ValueError("refusing to overwrite existing terrain-attachment outputs")

    frame = pd.read_csv(outer_frame_csv)
    enriched, summary = attach_coarse_terrain(frame)
    private_out_csv.parent.mkdir(parents=True, exist_ok=True)
    public_safe_summary_json.parent.mkdir(parents=True, exist_ok=True)
    enriched.to_csv(private_out_csv, index=False)
    encoded = (json.dumps(summary, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    public_safe_summary_json.write_bytes(encoded)
    return {
        **summary,
        "private_enriched_frame_sha256": _sha256_bytes(private_out_csv.read_bytes()),
        "public_safe_summary_sha256": _sha256_bytes(encoded),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outer-frame-csv", type=Path, required=True)
    parser.add_argument("--private-out-csv", type=Path, required=True)
    parser.add_argument("--public-safe-summary-json", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.outer_frame_csv, args.private_out_csv, args.public_safe_summary_json)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
