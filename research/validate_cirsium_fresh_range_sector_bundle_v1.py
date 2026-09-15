#!/usr/bin/env python3
"""Validate and split the one allowed private range-sector bundle for fresh SENTINEL evaluation.

The input is a private GeoJSON FeatureCollection containing exactly one Polygon or
MultiPolygon for each frozen unit CIR02/CIR06/CIR12/CIR13, keyed by
properties.cohort_unit_id. No geometry is inferred from textual sector labels.
Coordinate-bearing split outputs are refused inside the public repository.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")


def _inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT.resolve())
        return True
    except ValueError:
        return False


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def validate_bundle(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if payload.get("type") != "FeatureCollection":
        raise ValueError("private range-sector bundle must be a GeoJSON FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list) or len(features) != len(EXPECTED_UNITS):
        raise ValueError(f"bundle must contain exactly {len(EXPECTED_UNITS)} features")

    by_unit: dict[str, dict[str, Any]] = {}
    for feature in features:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError("every bundle member must be a GeoJSON Feature")
        properties = feature.get("properties") or {}
        unit_id = str(properties.get("cohort_unit_id") or "").strip()
        if unit_id not in EXPECTED_UNITS:
            raise ValueError(f"unexpected or missing cohort_unit_id: {unit_id!r}")
        if unit_id in by_unit:
            raise ValueError(f"duplicate cohort_unit_id in private range-sector bundle: {unit_id}")
        geometry_payload = feature.get("geometry")
        if not isinstance(geometry_payload, dict) or geometry_payload.get("type") not in {"Polygon", "MultiPolygon"}:
            raise ValueError(f"{unit_id} geometry must be Polygon or MultiPolygon")
        geometry = shape(geometry_payload)
        if geometry.is_empty or not geometry.is_valid or float(geometry.area) <= 0.0:
            raise ValueError(f"{unit_id} geometry must be non-empty, valid, and positive-area")
        by_unit[unit_id] = feature

    if set(by_unit) != set(EXPECTED_UNITS):
        raise ValueError(f"bundle unit set must equal {list(EXPECTED_UNITS)}")
    return by_unit


def split_private_bundle(bundle_path: Path, private_out_dir: Path) -> dict[str, object]:
    if not bundle_path.is_file():
        raise ValueError(f"missing private range-sector bundle: {bundle_path}")
    if _inside_repo(private_out_dir):
        raise ValueError("private range-sector split directory must be outside the git repository")
    payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    by_unit = validate_bundle(payload)
    private_out_dir.mkdir(parents=True, exist_ok=True)

    files: dict[str, dict[str, str]] = {}
    for unit_id in EXPECTED_UNITS:
        unit_payload = {
            "type": "FeatureCollection",
            "features": [by_unit[unit_id]],
        }
        encoded = (json.dumps(unit_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        out = private_out_dir / f"{unit_id}_range_sector.geojson"
        out.write_bytes(encoded)
        files[unit_id] = {"path": str(out), "sha256": _sha256_bytes(encoded)}

    summary = {
        "schema_version": "cirsium-fresh-sentinel-private-range-sector-bundle-v1",
        "status": "PRIVATE_RANGE_SECTOR_BUNDLE_VALIDATED_AND_SPLIT",
        "units": list(EXPECTED_UNITS),
        "files": files,
        "field_outcomes_used": False,
        "textual_sector_geometry_inference_used": False,
        "exact_coordinates_public": False,
    }
    summary_path = private_out_dir / "range_sector_bundle_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-geojson", type=Path, required=True)
    parser.add_argument("--private-out-dir", type=Path, required=True)
    args = parser.parse_args()
    summary = split_private_bundle(args.bundle_geojson, args.private_out_dir)
    print(json.dumps({
        "status": summary["status"],
        "units": summary["units"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
