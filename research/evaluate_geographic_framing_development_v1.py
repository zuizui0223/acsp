#!/usr/bin/env python3
"""Evaluate frozen geographic-framing v1 on already-opened development taxa.

This stage deliberately stops before robust candidate generation.  It measures
whether a training-occurrence-only inferred frame contains the held-out spatial
fold and how much geographic area it exposes relative to the original fixed
confirmation rectangle.  The 96 v2 taxa are already opened and are treated as
framing development evidence only.

Because the original confirmation workflow did not archive per-fold occurrence
CSVs, this evaluator consumes a freshly re-exported GBIF snapshot produced by
the unchanged v2 fold exporter.  The snapshot is fingerprinted in the output;
these results are therefore development diagnostics, not a replay of untouched
confirmation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from geographic_framing import infer_training_block_frames


PROTOCOL_PATH = Path("validation/acsp_geographic_framing_development_protocol_v1.json")
EXPECTED_PROTOCOL = "887526145c4fc0e2c9c3986c8424b4814b50155108a937b5d6a613b2ee974c0f"
EARTH_RADIUS_KM = 6371.0088


def _protocol() -> dict[str, object]:
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    stored = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if stored != EXPECTED_PROTOCOL or calculated != EXPECTED_PROTOCOL:
        raise ValueError(
            f"framing protocol fingerprint mismatch: file={stored}, calculated={calculated}, expected={EXPECTED_PROTOCOL}"
        )
    payload["protocol_fingerprint"] = stored
    return payload


def _manifest(fold_dir: Path) -> dict[str, object]:
    payload = json.loads((fold_dir / "fold_manifest.json").read_text(encoding="utf-8"))
    provenance = payload.get("provenance") or {}
    return {
        "pair_id": int(provenance["pair_id"]),
        "repeat": int(payload["repeat"]),
        "scientific_name": str(provenance["scientific_name"]),
        "taxon_group": str(provenance["taxon_group"]),
        "region_name": str(provenance["region_name"]),
        "geographic_stratum": str(provenance["geographic_stratum"]),
        "fold_status": str(payload.get("status") or "unknown"),
        "fold_failure_reason": str(payload.get("failure_reason") or ""),
        "west": float(provenance["west"]),
        "south": float(provenance["south"]),
        "east": float(provenance["east"]),
        "north": float(provenance["north"]),
    }


def _spherical_rect_area_km2(west: float, south: float, east: float, north: float) -> float:
    if not (west < east and south < north):
        raise ValueError("invalid rectangle bounds")
    if west < -180.0 or east > 180.0 or south < -90.0 or north > 90.0:
        raise ValueError("rectangle bounds outside geographic domain")
    lon_width = math.radians(east - west)
    lat_term = math.sin(math.radians(north)) - math.sin(math.radians(south))
    return float(EARTH_RADIUS_KM**2 * lon_width * lat_term)


def _frames_area_km2(frames: pd.DataFrame) -> float:
    if frames.empty:
        return 0.0
    return float(
        sum(
            _spherical_rect_area_km2(
                float(row.west), float(row.south), float(row.east), float(row.north)
            )
            for row in frames.itertuples(index=False)
        )
    )


def _heldout_containment(heldout: pd.DataFrame, frames: pd.DataFrame) -> tuple[int, int, float]:
    if heldout.empty:
        return 0, 0, 0.0
    held = heldout.copy()
    held["latitude"] = pd.to_numeric(held["latitude"], errors="coerce")
    held["longitude"] = pd.to_numeric(held["longitude"], errors="coerce")
    held = held.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)
    total = int(len(held))
    if total == 0 or frames.empty:
        return 0, total, 0.0
    lat = held["latitude"].to_numpy(float)
    lon = held["longitude"].to_numpy(float)
    inside = np.zeros(total, dtype=bool)
    for row in frames.itertuples(index=False):
        inside |= (
            (lon >= float(row.west))
            & (lon <= float(row.east))
            & (lat >= float(row.south))
            & (lat <= float(row.north))
        )
    count = int(inside.sum())
    return count, total, float(count / total)


def _snapshot_fingerprint(fold_dirs: list[Path]) -> str:
    digest = hashlib.sha256()
    for fold_dir in fold_dirs:
        relative = f"{fold_dir.parent.name}/{fold_dir.name}"
        digest.update(relative.encode("utf-8"))
        for name in ("fold_manifest.json", "training_occurrences.csv", "held_out_occurrences.csv"):
            path = fold_dir / name
            digest.update(name.encode("utf-8"))
            if path.exists():
                digest.update(path.read_bytes())
            else:
                digest.update(b"<missing>")
    return digest.hexdigest()


def _zero_row(meta: dict[str, object], reason: str) -> dict[str, object]:
    fixed_area = _spherical_rect_area_km2(
        float(meta["west"]), float(meta["south"]), float(meta["east"]), float(meta["north"])
    )
    return {
        **meta,
        "training_records": 0,
        "heldout_records": 0,
        "heldout_inside_frames": 0,
        "heldout_frame_containment": 0.0,
        "frame_count": 0,
        "initial_component_count": 0,
        "occupied_block_count": 0,
        "inferred_frame_area_km2": 0.0,
        "fixed_region_area_km2": fixed_area,
        "frame_area_ratio_to_fixed": 0.0,
        "framing_status": "failed_retained_as_zero",
        "failure_reason": str(reason),
    }


def evaluate_fold(fold_dir: Path) -> dict[str, object]:
    meta = _manifest(fold_dir)
    if meta["fold_status"] != "ready":
        return _zero_row(meta, meta["fold_failure_reason"] or f"fold_status={meta['fold_status']}")
    try:
        training = pd.read_csv(fold_dir / "training_occurrences.csv")
        heldout = pd.read_csv(fold_dir / "held_out_occurrences.csv")
        if training.empty or heldout.empty:
            return _zero_row(meta, "empty training or heldout fold")
        # The unchanged v2 exporter preserves source columns and also writes
        # canonical ``latitude``/``longitude`` columns. Select only the
        # canonical pair before renaming so pre-existing ``_latitude`` /
        # ``_longitude`` source columns cannot create duplicate column names.
        training_frame = training.loc[:, ["latitude", "longitude"]].copy().rename(
            columns={"latitude": "_latitude", "longitude": "_longitude"}
        )
        frames, _, frame_summary = infer_training_block_frames(training_frame)
        inside, held_count, containment = _heldout_containment(heldout, frames)
        inferred_area = _frames_area_km2(frames)
        fixed_area = _spherical_rect_area_km2(
            float(meta["west"]), float(meta["south"]), float(meta["east"]), float(meta["north"])
        )
        return {
            **meta,
            "training_records": int(len(training)),
            "heldout_records": int(held_count),
            "heldout_inside_frames": int(inside),
            "heldout_frame_containment": float(containment),
            "frame_count": int(len(frames)),
            "initial_component_count": int(frame_summary["initial_component_count"]),
            "occupied_block_count": int(frame_summary["occupied_block_count"]),
            "inferred_frame_area_km2": float(inferred_area),
            "fixed_region_area_km2": float(fixed_area),
            "frame_area_ratio_to_fixed": float(inferred_area / fixed_area),
            "framing_status": "evaluated",
            "failure_reason": "",
        }
    except Exception as exc:
        return _zero_row(meta, f"{type(exc).__name__}: {exc}")


def run(export_root: Path, output: Path) -> dict[str, object]:
    protocol = _protocol()
    fold_dirs = sorted(path.parent for path in export_root.glob("pair_*/fold_*/fold_manifest.json"))
    expected_folds = 96 * 5
    if len(fold_dirs) != expected_folds:
        raise RuntimeError(f"expected {expected_folds} development folds, found {len(fold_dirs)}")

    snapshot_fingerprint = _snapshot_fingerprint(fold_dirs)
    rows = [evaluate_fold(fold_dir) for fold_dir in fold_dirs]
    folds = pd.DataFrame(rows)
    if len(folds) != expected_folds:
        raise AssertionError("development evaluator must retain all 480 folds")

    output.mkdir(parents=True, exist_ok=True)
    folds.to_csv(output / "framing_fold_diagnostics.csv", index=False)

    pairs = (
        folds.groupby(
            ["pair_id", "scientific_name", "taxon_group", "region_name", "geographic_stratum"],
            as_index=False,
        )
        .agg(
            fold_count=("repeat", "count"),
            mean_heldout_frame_containment=("heldout_frame_containment", "mean"),
            mean_frame_count=("frame_count", "mean"),
            mean_frame_area_ratio_to_fixed=("frame_area_ratio_to_fixed", "mean"),
            failed_folds=("framing_status", lambda s: int((pd.Series(s).astype(str) != "evaluated").sum())),
        )
    )
    pairs.to_csv(output / "framing_pair_diagnostics.csv", index=False)

    evaluated = folds["framing_status"].eq("evaluated")
    summary: dict[str, object] = {
        "status": "development_only_framing_diagnostic_complete",
        "protocol_fingerprint": EXPECTED_PROTOCOL,
        "framing_method": protocol["framing_baseline"]["name"],
        "development_taxa": int(pairs["pair_id"].nunique()),
        "declared_folds": int(len(folds)),
        "evaluated_folds": int(evaluated.sum()),
        "failed_folds_retained_as_zero": int((~evaluated).sum()),
        "mean_fold_heldout_frame_containment": float(folds["heldout_frame_containment"].mean()),
        "mean_pair_heldout_frame_containment": float(pairs["mean_heldout_frame_containment"].mean()),
        "median_fold_frame_count": float(folds["frame_count"].median()),
        "median_fold_frame_area_ratio_to_fixed": float(folds["frame_area_ratio_to_fixed"].median()),
        "mean_fold_frame_area_ratio_to_fixed": float(folds["frame_area_ratio_to_fixed"].mean()),
        "taxon_group_mean_containment": {
            str(group): float(frame["mean_heldout_frame_containment"].mean())
            for group, frame in pairs.groupby("taxon_group")
        },
        "reexported_occurrence_snapshot_fingerprint": snapshot_fingerprint,
        "original_untouched_confirmation_replayed": False,
        "candidate_generation_run": False,
        "robust_support_run": False,
        "fresh_confirmation_taxa_consumed": False,
        "development_taxa_now_nonconfirmatory_for_framing": True,
        "interpretation": "framing containment/area diagnostic only; do not promote to validated product from this result",
    }
    (output / "framing_diagnostic_summary.json").write_text(
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
