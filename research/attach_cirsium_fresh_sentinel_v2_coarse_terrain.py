#!/usr/bin/env python3
"""Attach coarse public terrain primitives to a frozen fresh-SENTINEL v2 frame.

This stage preserves every candidate row and its order. Missing terrain and
provider failures are represented explicitly as indeterminate states; they never
remove candidates and never become biological negatives.

No occurrence prototypes, private exact sites, roads/access, budget, ranking,
selection, or field outcomes are read here.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from acsp.taxon_patches import (
    RAW_TERRAIN_FEATURES,
    ROBUST_TERRAIN_FEATURES,
    _with_robust_features,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_v2_coarse_terrain_v1.json"
REQUIRED_FRAME_COLUMNS = (
    "candidate_cell_id",
    "latitude",
    "longitude",
    "regional_tile_id",
    "outer_frame_identity",
    "field_outcomes_used",
    "private_exact_site_geometry_used",
    "occurrence_selected_tile",
)
COMPLETE = "COMPLETE"
POINT_MISSING = "INDETERMINATE_TERRAIN_MISSING"
PROVIDER_FAILURE = "INDETERMINATE_PROVIDER_FAILURE"


def _inside_repo(path: Path) -> bool:
    try:
        Path(path).resolve().relative_to(ROOT.resolve())
        return True
    except ValueError:
        return False


def _validate_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        raise ValueError("fresh-SENTINEL v2 outer frame cannot be empty")
    missing = [column for column in REQUIRED_FRAME_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"outer frame missing required columns: {missing}")
    if frame["candidate_cell_id"].isna().any() or frame["candidate_cell_id"].astype(str).duplicated().any():
        raise ValueError("candidate_cell_id must be complete and unique")
    if set(frame["outer_frame_identity"].astype(str)) != {"JP_PUBLIC_COUNTRY_BROAD_FRAME_V1"}:
        raise ValueError("outer-frame identity drifted")
    for column in ("field_outcomes_used", "private_exact_site_geometry_used", "occurrence_selected_tile"):
        if frame[column].map(bool).any():
            raise ValueError(f"{column} must remain false at coarse-terrain attachment")
    coordinates = frame[["latitude", "longitude"]].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(coordinates.to_numpy(float)).all():
        raise ValueError("outer-frame coordinates must be complete and finite")
    return frame.copy().reset_index(drop=True)


def _default_extractor(frame: pd.DataFrame) -> pd.DataFrame:
    from gbif_fieldmap_builder_app import extract_environment

    return extract_environment(
        frame,
        list(RAW_TERRAIN_FEATURES),
        "latitude",
        "longitude",
        "2.5m",
    )


def attach_coarse_terrain_primitives(
    frame: pd.DataFrame,
    *,
    extractor: Callable[[pd.DataFrame], pd.DataFrame] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Attach terrain without changing candidate membership or order."""
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if contract.get("status") != "FROZEN_BEFORE_COARSE_TERRAIN_ATTACHMENT":
        raise ValueError("coarse-terrain contract is not frozen")
    work = _validate_frame(frame)
    original_ids = work["candidate_cell_id"].astype(str).tolist()
    provider_error_class = ""

    try:
        enriched = (extractor or _default_extractor)(work.copy())
        if not isinstance(enriched, pd.DataFrame):
            raise TypeError("terrain extractor must return a DataFrame")
        if len(enriched) != len(work):
            raise ValueError("terrain extractor changed candidate row count")
        if "candidate_cell_id" not in enriched.columns:
            raise ValueError("terrain extractor removed candidate_cell_id")
        if enriched["candidate_cell_id"].astype(str).tolist() != original_ids:
            raise ValueError("terrain extractor changed candidate identity or order")
        for column in RAW_TERRAIN_FEATURES:
            if column not in enriched.columns:
                enriched[column] = np.nan
        enriched = _with_robust_features(enriched)
        matrix = enriched.loc[:, list(ROBUST_TERRAIN_FEATURES)].apply(
            pd.to_numeric, errors="coerce"
        ).to_numpy(float)
        complete = np.isfinite(matrix).all(axis=1)
        enriched["coarse_terrain_status"] = np.where(complete, COMPLETE, POINT_MISSING)
        enriched["coarse_terrain_provider_error_class"] = ""
    except Exception as exc:
        # Provider/computation failure is kept separate from ecological evidence.
        # The frozen outer-frame membership is preserved exactly.
        enriched = work.copy()
        for column in (*RAW_TERRAIN_FEATURES, *ROBUST_TERRAIN_FEATURES):
            if column not in enriched.columns:
                enriched[column] = np.nan
        enriched["coarse_terrain_status"] = PROVIDER_FAILURE
        provider_error_class = type(exc).__name__
        enriched["coarse_terrain_provider_error_class"] = provider_error_class
        complete = np.zeros(len(enriched), dtype=bool)

    if enriched["candidate_cell_id"].astype(str).tolist() != original_ids:
        raise AssertionError("coarse-terrain stage did not preserve candidate identity/order")
    if len(enriched) != len(work):
        raise AssertionError("coarse-terrain stage did not preserve candidate row count")

    counts = enriched["coarse_terrain_status"].astype(str).value_counts().to_dict()
    summary = {
        "schema_version": "cirsium-fresh-sentinel-v2-coarse-terrain-attachment-v1",
        "status": "COARSE_TERRAIN_PRIMITIVES_ATTACHED_PRE_OUTCOME",
        "source_outer_frame_identity": "JP_PUBLIC_COUNTRY_BROAD_FRAME_V1",
        "input_candidate_count": int(len(work)),
        "output_candidate_count": int(len(enriched)),
        "candidate_rows_dropped": 0,
        "candidate_identity_order_preserved": True,
        "terrain_resolution_token": "2.5m",
        "raw_terrain_features": list(RAW_TERRAIN_FEATURES),
        "robust_terrain_features": list(ROBUST_TERRAIN_FEATURES),
        "complete_candidate_count": int(np.sum(complete)),
        "incomplete_candidate_count": int(len(enriched) - np.sum(complete)),
        "status_counts": {str(key): int(value) for key, value in sorted(counts.items())},
        "provider_error_class": provider_error_class,
        "provider_failure_is_biological_negative": False,
        "missing_terrain_is_biological_negative": False,
        "candidate_selection_added": False,
        "candidate_ranking_added": False,
        "occurrence_prototypes_used": False,
        "private_exact_site_geometry_used": False,
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used": False,
        "human_access_used": False,
        "survey_days_input": False,
        "monetary_budget_input": False,
        "user_site_count_input": False,
    }
    return enriched, summary


def run(input_csv: Path, output_csv: Path, summary_json: Path) -> dict[str, Any]:
    input_csv = Path(input_csv).resolve()
    output_csv = Path(output_csv).resolve()
    summary_json = Path(summary_json).resolve()
    if not input_csv.is_file():
        raise ValueError(f"missing frozen outer-frame CSV: {input_csv}")
    if _inside_repo(output_csv) or _inside_repo(summary_json):
        raise ValueError("coordinate-bearing coarse-terrain outputs must remain outside the public repository")
    if output_csv.exists() or summary_json.exists():
        raise ValueError("refusing to overwrite existing coarse-terrain outputs")
    enriched, summary = attach_coarse_terrain_primitives(pd.read_csv(input_csv))
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    summary_json.parent.mkdir(parents=True, exist_ok=True)
    enriched.to_csv(output_csv, index=False)
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.input_csv, args.output_csv, args.summary_json)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
