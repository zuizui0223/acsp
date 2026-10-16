#!/usr/bin/env python3
"""Attach ESA WorldCover 2021 v200 point classes to a frozen v2 tile.

The coarse stage deliberately samples only the land-cover class at each frozen
geometry point. It does not reuse the Izu-specific 250 m neighborhood helper.
Candidate membership/order is immutable: missing classes and provider failures
remain explicit indeterminate states and never remove rows.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer

from acsp.discovery.providers.worldcover import (
    WORLD_COVER_2021_CLASS_NAMES,
    build_worldcover_2021_map_crop,
    worldcover_2021_map_url,
    worldcover_tile_id,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_v2_worldcover_point_primitives_v1.json"
REPAIR_RECEIPT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_v2_full_worldcover_result_v1.json"
REPAIR_IDENTITY = "POINT_BEARING_WORLDCOVER_COG_ONLY_V1"
COMPLETE = "COMPLETE"
POINT_MISSING = "INDETERMINATE_WORLDCOVER_MISSING"
PROVIDER_FAILURE = "INDETERMINATE_PROVIDER_FAILURE"
VALID_CODES = set(int(code) for code in WORLD_COVER_2021_CLASS_NAMES)
REQUIRED_FRAME_COLUMNS = (
    "candidate_cell_id",
    "latitude",
    "longitude",
    "regional_tile_id",
    "tile_west",
    "tile_south",
    "tile_east",
    "tile_north",
    "outer_frame_identity",
    "field_outcomes_used",
    "private_exact_site_geometry_used",
    "occurrence_selected_tile",
)


def _inside_repo(path: Path) -> bool:
    try:
        Path(path).resolve().relative_to(ROOT.resolve())
        return True
    except ValueError:
        return False


def _validate_tile_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        raise ValueError("WorldCover tile frame cannot be empty")
    missing = [column for column in REQUIRED_FRAME_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"WorldCover tile frame missing columns: {missing}")
    if frame["candidate_cell_id"].isna().any() or frame["candidate_cell_id"].astype(str).duplicated().any():
        raise ValueError("candidate_cell_id must be complete and unique")
    if frame["regional_tile_id"].astype(str).nunique() != 1:
        raise ValueError("WorldCover point attachment processes exactly one frozen regional tile at a time")
    if set(frame["outer_frame_identity"].astype(str)) != {"JP_PUBLIC_COUNTRY_BROAD_FRAME_V1"}:
        raise ValueError("outer-frame identity drifted")
    for column in ("field_outcomes_used", "private_exact_site_geometry_used", "occurrence_selected_tile"):
        if frame[column].map(bool).any():
            raise ValueError(f"{column} must remain false at WorldCover attachment")
    for column in ("latitude", "longitude", "tile_west", "tile_south", "tile_east", "tile_north"):
        numeric = pd.to_numeric(frame[column], errors="coerce")
        if not np.isfinite(numeric.to_numpy(float)).all():
            raise ValueError(f"{column} must be complete and finite")
    for column in ("tile_west", "tile_south", "tile_east", "tile_north"):
        if frame[column].astype(float).nunique() != 1:
            raise ValueError(f"{column} must be constant within one regional tile")
    return frame.copy().reset_index(drop=True)


def _sample_classes(frame: pd.DataFrame, crop_path: Path) -> np.ndarray:
    with rasterio.open(crop_path) as src:
        lon = frame["longitude"].to_numpy(float)
        lat = frame["latitude"].to_numpy(float)
        if src.crs is None:
            raise ValueError("WorldCover crop must declare a CRS")
        if src.crs.to_epsg() == 4326:
            xs, ys = lon, lat
        else:
            transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
            xs, ys = transformer.transform(lon, lat)
        values = np.asarray(
            [sample[0] for sample in src.sample(list(zip(xs, ys)))],
            dtype=float,
        )
        if src.nodata is not None:
            values[values == float(src.nodata)] = np.nan
        return values


def attach_worldcover_point_classes(
    frame: pd.DataFrame,
    *,
    crop_path: Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Attach point classes from an already materialized WorldCover crop."""
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if contract.get("status") != "FROZEN_BEFORE_WORLDCOVER_POINT_ATTACHMENT":
        raise ValueError("WorldCover point-primitive contract is not frozen")
    work = _validate_tile_frame(frame)
    original_ids = work["candidate_cell_id"].astype(str).tolist()
    values = _sample_classes(work, Path(crop_path))
    if len(values) != len(work):
        raise AssertionError("WorldCover sampler changed candidate row count")

    finite = np.isfinite(values)
    integer_like = finite & np.isclose(values, np.rint(values), rtol=0.0, atol=1e-9)
    codes = np.where(integer_like, np.rint(values), np.nan)
    known = np.asarray([
        bool(np.isfinite(value) and int(value) in VALID_CODES)
        for value in codes
    ])
    work["worldcover_class_code"] = codes
    work["worldcover_class_name"] = [
        WORLD_COVER_2021_CLASS_NAMES.get(int(value), "")
        if np.isfinite(value)
        else ""
        for value in codes
    ]
    work["worldcover_point_status"] = np.where(known, COMPLETE, POINT_MISSING)
    work["worldcover_provider_error_class"] = ""

    if work["candidate_cell_id"].astype(str).tolist() != original_ids:
        raise AssertionError("WorldCover stage changed candidate identity/order")
    counts = work["worldcover_point_status"].astype(str).value_counts().to_dict()
    summary = {
        "schema_version": "cirsium-fresh-sentinel-v2-worldcover-point-attachment-v1",
        "status": "WORLDCOVER_POINT_CLASSES_ATTACHED_PRE_OUTCOME",
        "regional_tile_id": str(work["regional_tile_id"].iloc[0]),
        "input_candidate_count": int(len(work)),
        "output_candidate_count": int(len(work)),
        "candidate_rows_dropped": 0,
        "candidate_identity_order_preserved": True,
        "complete_candidate_count": int(known.sum()),
        "incomplete_candidate_count": int(len(work) - known.sum()),
        "provider_failure_is_biological_negative": False,
        "missing_worldcover_is_biological_negative": False,
        "status_counts": {str(k): int(v) for k, v in sorted(counts.items())},
        "candidate_selection_added": False,
        "candidate_ranking_added": False,
        "neighborhood_fraction_used": False,
        "focal_occurrence_prototypes_used": False,
        "private_exact_site_geometry_used": False,
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used": False,
        "human_access_used": False,
    }
    return work, summary


def attach_worldcover_tile_with_provider(
    frame: pd.DataFrame,
    *,
    crop_path: Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Materialize a tile crop and attach classes, preserving rows on provider failure."""
    work = _validate_tile_frame(frame)
    bounds = (
        float(work["tile_west"].iloc[0]),
        float(work["tile_south"].iloc[0]),
        float(work["tile_east"].iloc[0]),
        float(work["tile_north"].iloc[0]),
    )
    original_ids = work["candidate_cell_id"].astype(str).tolist()
    try:
        audit = build_worldcover_2021_map_crop(bounds, Path(crop_path), margin_m=500.0)
        attached, summary = attach_worldcover_point_classes(work, crop_path=Path(crop_path))
        summary["provider_id"] = audit.provider_id
        summary["provider_release_id"] = audit.release_id
        summary["source_tile_ids"] = list(audit.source_tile_ids)
        summary["crop_sha256"] = audit.output_sha256
        summary["provider_error_class"] = ""
        return attached, summary
    except Exception as exc:
        out = work.copy()
        out["worldcover_class_code"] = np.nan
        out["worldcover_class_name"] = ""
        out["worldcover_point_status"] = PROVIDER_FAILURE
        out["worldcover_provider_error_class"] = type(exc).__name__
        if out["candidate_cell_id"].astype(str).tolist() != original_ids:
            raise AssertionError("WorldCover provider failure changed candidate identity/order")
        return out, {
            "schema_version": "cirsium-fresh-sentinel-v2-worldcover-point-attachment-v1",
            "status": "WORLDCOVER_POINT_CLASSES_ATTACHED_PRE_OUTCOME",
            "regional_tile_id": str(out["regional_tile_id"].iloc[0]),
            "input_candidate_count": int(len(out)),
            "output_candidate_count": int(len(out)),
            "candidate_rows_dropped": 0,
            "candidate_identity_order_preserved": True,
            "complete_candidate_count": 0,
            "incomplete_candidate_count": int(len(out)),
            "status_counts": {PROVIDER_FAILURE: int(len(out))},
            "provider_id": "ESA_WORLDCOVER",
            "provider_release_id": "2021_v200",
            "source_tile_ids": [],
            "crop_sha256": "",
            "provider_error_class": type(exc).__name__,
            "provider_failure_is_biological_negative": False,
            "candidate_selection_added": False,
            "candidate_ranking_added": False,
            "neighborhood_fraction_used": False,
            "focal_occurrence_prototypes_used": False,
            "private_exact_site_geometry_used": False,
            "prospective_field_outcomes_opened": False,
            "field_outcomes_used": False,
            "human_access_used": False,
        }


def _validate_repair_receipt() -> dict[str, Any]:
    value = json.loads(REPAIR_RECEIPT.read_text(encoding="utf-8"))
    if value.get("status") != "FULL_49_TILE_WORLDCOVER_COVERAGE_AUDIT_FROZEN":
        raise ValueError("WorldCover repair receipt is not frozen")
    if value.get("source_gate_complete") is not False:
        raise ValueError("WorldCover repair receipt no longer represents the failed source gate")
    repair = value.get("repair_boundary_frozen_before_retry") or {}
    if repair.get("repair_identity") != REPAIR_IDENTITY:
        raise ValueError("WorldCover repair identity drifted")
    if repair.get("candidate_membership_change_allowed") is not False:
        raise ValueError("WorldCover repair cannot change candidate membership")
    if repair.get("candidate_order_change_allowed") is not False:
        raise ValueError("WorldCover repair cannot change candidate order")
    if repair.get("worldcover_release_change_allowed") is not False:
        raise ValueError("WorldCover repair cannot change the WorldCover release")
    if repair.get("alternate_provider_allowed") is not False:
        raise ValueError("WorldCover repair cannot substitute another provider")
    return value


def _sample_official_point_cog(frame: pd.DataFrame, source_tile_id: str) -> np.ndarray:
    url = worldcover_2021_map_url(source_tile_id)
    with rasterio.open(url) as src:
        lon = frame["longitude"].to_numpy(float)
        lat = frame["latitude"].to_numpy(float)
        if src.crs is None:
            raise ValueError("WorldCover source COG must declare a CRS")
        if src.crs.to_epsg() == 4326:
            xs, ys = lon, lat
        else:
            transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
            xs, ys = transformer.transform(lon, lat)
        values = np.asarray(
            [sample[0] for sample in src.sample(list(zip(xs, ys)))],
            dtype=float,
        )
        if src.nodata is not None:
            values[values == float(src.nodata)] = np.nan
        return values


def attach_worldcover_point_bearing_cogs(
    frame: pd.DataFrame,
    *,
    sampler=None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Attach point classes using only official COGs that contain frozen points.

    This is the frozen source-mechanics repair after the first full execution
    diagnosed rectangular-bounds overfetch. Candidate identity, order, coordinates,
    release and class semantics are unchanged.
    """
    _validate_repair_receipt()
    work = _validate_tile_frame(frame)
    original_ids = work["candidate_cell_id"].astype(str).tolist()
    source_ids = [
        worldcover_tile_id(float(lat), float(lon))
        for lat, lon in zip(work["latitude"], work["longitude"])
    ]
    work["worldcover_source_tile_id"] = source_ids
    sample_fn = _sample_official_point_cog if sampler is None else sampler

    codes = np.full(len(work), np.nan, dtype=float)
    statuses = np.full(len(work), PROVIDER_FAILURE, dtype=object)
    errors = np.full(len(work), "", dtype=object)
    successful: list[str] = []
    failed: dict[str, str] = {}

    source_array = np.asarray(source_ids, dtype=object)
    for source_tile_id in sorted(set(source_ids)):
        indices = np.flatnonzero(source_array == source_tile_id)
        subset = work.iloc[indices].copy().reset_index(drop=True)
        try:
            values = np.asarray(sample_fn(subset, source_tile_id), dtype=float)
            if len(values) != len(indices):
                raise ValueError("point-bearing WorldCover sampler changed row count")
            finite = np.isfinite(values)
            integer_like = finite & np.isclose(values, np.rint(values), rtol=0.0, atol=1e-9)
            rounded = np.where(integer_like, np.rint(values), np.nan)
            known = np.asarray([
                bool(np.isfinite(value) and int(value) in VALID_CODES)
                for value in rounded
            ])
            codes[indices] = rounded
            statuses[indices] = np.where(known, COMPLETE, POINT_MISSING)
            successful.append(source_tile_id)
        except Exception as exc:
            statuses[indices] = PROVIDER_FAILURE
            errors[indices] = type(exc).__name__
            failed[source_tile_id] = type(exc).__name__

    work["worldcover_class_code"] = codes
    work["worldcover_class_name"] = [
        WORLD_COVER_2021_CLASS_NAMES.get(int(value), "")
        if np.isfinite(value) and int(value) in VALID_CODES
        else ""
        for value in codes
    ]
    work["worldcover_point_status"] = statuses
    work["worldcover_provider_error_class"] = errors

    if work["candidate_cell_id"].astype(str).tolist() != original_ids:
        raise AssertionError("point-bearing WorldCover repair changed candidate identity/order")

    counts = work["worldcover_point_status"].astype(str).value_counts().to_dict()
    complete_n = int((work["worldcover_point_status"].astype(str) == COMPLETE).sum())
    return work, {
        "schema_version": "cirsium-fresh-sentinel-v2-worldcover-point-bearing-cog-attachment-v1",
        "status": "POINT_BEARING_WORLDCOVER_COGS_ATTACHED_PRE_OUTCOME",
        "repair_identity": REPAIR_IDENTITY,
        "regional_tile_id": str(work["regional_tile_id"].iloc[0]),
        "input_candidate_count": int(len(work)),
        "output_candidate_count": int(len(work)),
        "candidate_rows_dropped": 0,
        "candidate_identity_order_preserved": True,
        "complete_candidate_count": complete_n,
        "incomplete_candidate_count": int(len(work) - complete_n),
        "status_counts": {str(k): int(v) for k, v in sorted(counts.items())},
        "source_tile_ids": sorted(set(source_ids)),
        "successful_source_tile_ids": sorted(successful),
        "failed_source_tile_ids": sorted(failed),
        "failed_source_tile_error_classes": dict(sorted(failed.items())),
        "bounds_overfetch_used": False,
        "point_bearing_cog_only": True,
        "provider_id": "ESA_WORLDCOVER",
        "provider_release_id": "2021_v200",
        "provider_failure_is_biological_negative": False,
        "missing_worldcover_is_biological_negative": False,
        "candidate_selection_added": False,
        "candidate_ranking_added": False,
        "habitat_threshold_added": False,
        "neighborhood_fraction_used": False,
        "focal_occurrence_prototypes_used": False,
        "private_exact_site_geometry_used": False,
        "p02_result_used": False,
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used": False,
        "human_access_used": False,
    }


def run(input_csv: Path, output_csv: Path, summary_json: Path, crop_path: Path) -> dict[str, Any]:
    input_csv = Path(input_csv).resolve()
    output_csv = Path(output_csv).resolve()
    summary_json = Path(summary_json).resolve()
    crop_path = Path(crop_path).resolve()
    if not input_csv.is_file():
        raise ValueError(f"missing frozen tile CSV: {input_csv}")
    for path in (output_csv, summary_json, crop_path):
        if _inside_repo(path):
            raise ValueError("coordinate-bearing WorldCover execution outputs must remain outside the public repository")
    if output_csv.exists() or summary_json.exists():
        raise ValueError("refusing to overwrite WorldCover point-primitive outputs")
    attached, summary = attach_worldcover_tile_with_provider(
        pd.read_csv(input_csv),
        crop_path=crop_path,
    )
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    summary_json.parent.mkdir(parents=True, exist_ok=True)
    attached.to_csv(output_csv, index=False)
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path, required=True)
    parser.add_argument("--crop-path", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.input_csv, args.output_csv, args.summary_json, args.crop_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
