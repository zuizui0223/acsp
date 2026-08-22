#!/usr/bin/env python3
"""Post-hoc development diagnostics for geographic-framing v1 misses.

This script does not alter v1 frame construction.  Held-out coordinates are
used only after frames are frozen to classify why misses occurred:

- ``training_supported_component``: in the full occupied-block graph, the held-
  out record belongs to a component that also contains at least one training
  block.  Such misses are potentially a within-range framing representation
  problem (holes/gaps/insufficient bridge geometry).
- ``heldout_only_component``: the full occupied-block component contains no
  training block.  Local training-component geometry has no direct evidence for
  that distribution component; changing a local padding heuristic alone cannot
  make the component identifiable.

A single training-coordinate bounding rectangle plus the same frozen 10 km
padding is also reported strictly as a diagnostic upper-envelope comparator.
It is not promoted as a framing method because it collapses disjunct structure.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from geographic_framing import (
    DEFAULT_BLOCK_DEGREES,
    DEFAULT_PADDING_KM,
    EARTH_KM_PER_DEG_LAT,
    _block_indices,
    _occupied_components,
    infer_training_block_frames,
)


EARTH_RADIUS_KM = 6371.0088


def _canonical_coordinates(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.loc[:, ["latitude", "longitude"]].copy()
    out["latitude"] = pd.to_numeric(out["latitude"], errors="coerce")
    out["longitude"] = pd.to_numeric(out["longitude"], errors="coerce")
    return out.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)


def _inside_frames(points: pd.DataFrame, frames: pd.DataFrame) -> np.ndarray:
    inside = np.zeros(len(points), dtype=bool)
    if points.empty or frames.empty:
        return inside
    lat = points["latitude"].to_numpy(float)
    lon = points["longitude"].to_numpy(float)
    for row in frames.itertuples(index=False):
        inside |= (
            (lon >= float(row.west))
            & (lon <= float(row.east))
            & (lat >= float(row.south))
            & (lat <= float(row.north))
        )
    return inside


def _training_bbox_frame(training: pd.DataFrame, padding_km: float = DEFAULT_PADDING_KM) -> pd.DataFrame:
    if training.empty:
        return pd.DataFrame(columns=["west", "south", "east", "north"])
    south = float(training["latitude"].min())
    north = float(training["latitude"].max())
    west = float(training["longitude"].min())
    east = float(training["longitude"].max())
    mid_lat = (south + north) / 2.0
    lat_pad = float(padding_km) / EARTH_KM_PER_DEG_LAT
    cosine = abs(math.cos(math.radians(mid_lat)))
    if cosine < 0.05:
        raise ValueError("diagnostic bbox does not support near-polar longitude padding")
    lon_pad = float(padding_km) / (EARTH_KM_PER_DEG_LAT * cosine)
    west -= lon_pad
    east += lon_pad
    south = max(-90.0, south - lat_pad)
    north = min(90.0, north + lat_pad)
    if west < -180.0 or east > 180.0:
        raise ValueError("diagnostic bbox does not support antimeridian crossing")
    return pd.DataFrame([{"west": west, "south": south, "east": east, "north": north}])


def _rect_area_km2(frame: pd.DataFrame) -> float:
    if frame.empty:
        return 0.0
    total = 0.0
    for row in frame.itertuples(index=False):
        total += (
            EARTH_RADIUS_KM**2
            * math.radians(float(row.east) - float(row.west))
            * (math.sin(math.radians(float(row.north))) - math.sin(math.radians(float(row.south))))
        )
    return float(total)


def _component_support_labels(training: pd.DataFrame, heldout: pd.DataFrame) -> np.ndarray:
    """Classify held-out rows by whether their full block component has training support."""
    combined = pd.concat(
        [
            training.assign(_origin="training"),
            heldout.assign(_origin="heldout"),
        ],
        ignore_index=True,
    )
    lat_idx = _block_indices(
        combined["latitude"].to_numpy(float),
        origin=-90.0,
        block_degrees=DEFAULT_BLOCK_DEGREES,
    )
    lon_idx = _block_indices(
        combined["longitude"].to_numpy(float),
        origin=-180.0,
        block_degrees=DEFAULT_BLOCK_DEGREES,
    )
    components = _occupied_components(lat_idx, lon_idx)
    row_to_component: dict[int, int] = {}
    component_has_training: dict[int, bool] = {}
    for component_id, component in enumerate(components):
        rows = list(component.rows)
        has_training = bool((combined.iloc[rows]["_origin"] == "training").any())
        component_has_training[component_id] = has_training
        for row in rows:
            row_to_component[int(row)] = int(component_id)
    offset = len(training)
    return np.asarray(
        [component_has_training[row_to_component[offset + i]] for i in range(len(heldout))],
        dtype=bool,
    )


def diagnose_fold(fold_dir: Path) -> dict[str, object]:
    manifest = json.loads((fold_dir / "fold_manifest.json").read_text(encoding="utf-8"))
    provenance = manifest.get("provenance") or {}
    meta = {
        "pair_id": int(provenance["pair_id"]),
        "repeat": int(manifest["repeat"]),
        "scientific_name": str(provenance["scientific_name"]),
        "taxon_group": str(provenance["taxon_group"]),
        "region_name": str(provenance["region_name"]),
    }
    if str(manifest.get("status")) != "ready":
        return {
            **meta,
            "status": "upstream_failed_retained_as_zero",
            "heldout_records": 0,
            "v1_contained_records": 0,
            "v1_missed_records": 0,
            "missed_training_supported_component": 0,
            "missed_heldout_only_component": 0,
            "training_supported_component_fraction": 0.0,
            "bbox_10km_containment": 0.0,
            "bbox_10km_area_ratio_to_fixed": 0.0,
            "failure_reason": str(manifest.get("failure_reason") or "upstream fold failure"),
        }
    try:
        training = _canonical_coordinates(pd.read_csv(fold_dir / "training_occurrences.csv"))
        heldout = _canonical_coordinates(pd.read_csv(fold_dir / "held_out_occurrences.csv"))
        if training.empty or heldout.empty:
            raise ValueError("empty canonical training or heldout coordinates")

        v1_frames, _, _ = infer_training_block_frames(
            training.rename(columns={"latitude": "_latitude", "longitude": "_longitude"})
        )
        v1_inside = _inside_frames(heldout, v1_frames)
        supported = _component_support_labels(training, heldout)
        missed = ~v1_inside

        bbox = _training_bbox_frame(training)
        bbox_inside = _inside_frames(heldout, bbox)
        fixed = pd.DataFrame(
            [{
                "west": float(provenance["west"]),
                "south": float(provenance["south"]),
                "east": float(provenance["east"]),
                "north": float(provenance["north"]),
            }]
        )
        fixed_area = _rect_area_km2(fixed)
        return {
            **meta,
            "status": "evaluated",
            "heldout_records": int(len(heldout)),
            "v1_contained_records": int(v1_inside.sum()),
            "v1_missed_records": int(missed.sum()),
            "missed_training_supported_component": int((missed & supported).sum()),
            "missed_heldout_only_component": int((missed & ~supported).sum()),
            "training_supported_component_fraction": float(supported.mean()),
            "bbox_10km_containment": float(bbox_inside.mean()),
            "bbox_10km_area_ratio_to_fixed": float(_rect_area_km2(bbox) / fixed_area),
            "failure_reason": "",
        }
    except Exception as exc:
        return {
            **meta,
            "status": "diagnostic_failed_retained_as_zero",
            "heldout_records": 0,
            "v1_contained_records": 0,
            "v1_missed_records": 0,
            "missed_training_supported_component": 0,
            "missed_heldout_only_component": 0,
            "training_supported_component_fraction": 0.0,
            "bbox_10km_containment": 0.0,
            "bbox_10km_area_ratio_to_fixed": 0.0,
            "failure_reason": f"{type(exc).__name__}: {exc}",
        }


def run(export_root: Path, output: Path) -> dict[str, object]:
    fold_dirs = sorted(path.parent for path in export_root.glob("pair_*/fold_*/fold_manifest.json"))
    if len(fold_dirs) != 480:
        raise RuntimeError(f"expected 480 development folds, found {len(fold_dirs)}")
    rows = [diagnose_fold(path) for path in fold_dirs]
    folds = pd.DataFrame(rows)
    output.mkdir(parents=True, exist_ok=True)
    folds.to_csv(output / "framing_v1_failure_diagnostics.csv", index=False)

    evaluated = folds["status"].eq("evaluated")
    evaluated_rows = folds.loc[evaluated].copy()
    total_misses = int(evaluated_rows["v1_missed_records"].sum())
    supported_misses = int(evaluated_rows["missed_training_supported_component"].sum())
    orphan_misses = int(evaluated_rows["missed_heldout_only_component"].sum())
    summary = {
        "status": "development_only_posthoc_v1_failure_diagnostic",
        "declared_folds": 480,
        "evaluated_folds": int(evaluated.sum()),
        "failed_folds_retained": int((~evaluated).sum()),
        "total_v1_missed_heldout_records_in_evaluated_folds": total_misses,
        "missed_records_in_training_supported_components": supported_misses,
        "missed_records_in_heldout_only_components": orphan_misses,
        "fraction_of_v1_misses_training_supported": float(supported_misses / total_misses) if total_misses else 0.0,
        "fraction_of_v1_misses_heldout_only_component": float(orphan_misses / total_misses) if total_misses else 0.0,
        "mean_heldout_training_supported_component_fraction": float(evaluated_rows["training_supported_component_fraction"].mean()) if len(evaluated_rows) else 0.0,
        "mean_bbox_10km_containment": float(evaluated_rows["bbox_10km_containment"].mean()) if len(evaluated_rows) else 0.0,
        "median_bbox_10km_area_ratio_to_fixed": float(evaluated_rows["bbox_10km_area_ratio_to_fixed"].median()) if len(evaluated_rows) else 0.0,
        "bbox_role": "post-hoc diagnostic upper-envelope comparator only; not a promoted framing method",
        "v1_method_changed": False,
        "candidate_generation_run": False,
        "fresh_confirmation_consumed": False,
    }
    (output / "framing_v1_failure_diagnostic_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.export_root, args.output), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
