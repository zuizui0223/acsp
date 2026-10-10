#!/usr/bin/env python3
"""Stage 3 v2 exact RU candidate freeze, stopping before heldout outcomes.

The national RU candidate surface is the already byte-pinned complete terrain
surface used by the equivalence-tested exact RU recovery path. The only change
here is the information boundary: candidate patches are assembled and frozen,
but 2021-2025 records and random recovery are never opened.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from acsp.robust_patches import robust_environment_geometry
from acsp.taxon_patches import RAW_TERRAIN_FEATURES, ROBUST_TERRAIN_FEATURES, _prototype_coordinates, _with_robust_features
from acsp.validated_robust import (
    VALIDATED_ROBUST_PATCH_MERGE_DISTANCE_M,
    VALIDATED_ROBUST_SUPPORT_FRACTION,
    _project_validated_patch_table,
)
from country_framed_robust_integration import fetch_country_occurrences
from exact_fast_complete_link import exact_fast_support_cells_to_patches
from freeze_global_availability_parity_candidate_pair_v2 import verify_inputs, _is_declared_evidence_failure
from run_country_framed_integration_development_v1_1 import _geometry_digest_from_source_version
from run_country_framed_integration_development_v2_ru_tile_retry import RU_GEOMETRY_SHA256, _verify_ru_geometry
from run_ru_robust_world_shard_fallback import verify_surface as verify_pinned_ru_surface

EXPECTED_SURFACE_SHA256 = "77729dfa45b9e123f035ca15a421f834a6b155140ae410b8806e9f4eca19c982"
EXPECTED_SURFACE_MANIFEST_SHA256 = "a4cd321cee240f050d4223ab19b3af8f956ac80d675229703d2dffdbb0908d7e"
WORLD_SHARD_COUNT = 8
RU_PAIR_ID = 48
RU_CODE = "RU"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_surface(surface_path: Path, manifest_path: Path) -> dict[str, object]:
    if _sha256_file(surface_path) != EXPECTED_SURFACE_SHA256:
        raise ValueError("pinned RU complete surface SHA256 drift")
    if _sha256_file(manifest_path) != EXPECTED_SURFACE_MANIFEST_SHA256:
        raise ValueError("pinned RU surface manifest SHA256 drift")
    return verify_pinned_ru_surface(surface_path, manifest_path)


def _extract_environment(points: pd.DataFrame) -> pd.DataFrame:
    from gbif_fieldmap_builder_app import extract_environment
    return extract_environment(points, list(RAW_TERRAIN_FEATURES), "latitude", "longitude", "2.5m")


def frozen_ru_base() -> dict[str, object]:
    plans = verify_inputs()
    hit = plans.loc[plans["availability_pair_id"].astype(int).eq(RU_PAIR_ID)]
    if len(hit) != 1:
        raise ValueError("expected exactly one frozen RU pair")
    base = hit.iloc[0].to_dict()
    if str(base["selected_country_code"]).upper() != RU_CODE:
        raise ValueError("frozen RU country drift")
    return base


def prepare_pair(output: Path) -> dict[str, object]:
    base = frozen_ru_base()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    key = int(base["speciesKey"])
    geom = _verify_ru_geometry()
    verified = _geometry_digest_from_source_version(geom.source_version)
    if verified != RU_GEOMETRY_SHA256:
        raise ValueError("verified RU geometry digest drift")
    try:
        historical = fetch_country_occurrences(key, RU_CODE)
    except Exception as exc:
        if _is_declared_evidence_failure(exc):
            return _write_pre_world_sentinel(output, base, verified, str(exc), historical_rows=0)
        raise
    hist_n = int(len(historical))
    prototype_points = _prototype_coordinates(historical)
    try:
        prototypes = _with_robust_features(_extract_environment(prototype_points))
    except Exception:
        raise
    prototypes = prototypes.loc[
        prototypes[list(ROBUST_TERRAIN_FEATURES)].notna().all(axis=1)
    ].copy().drop_duplicates(list(ROBUST_TERRAIN_FEATURES)).reset_index(drop=True)
    proto_n = int(len(prototypes))
    if proto_n < 5:
        return _write_pre_world_sentinel(
            output, base, verified,
            f"fewer than five unique complete historical terrain prototypes: {proto_n}",
            historical_rows=hist_n,
        )
    if proto_n > 32:
        raise ValueError(f"prototype rule drift: expected <=32, got {proto_n}")
    prototypes.to_parquet(output / "prototypes.parquet", index=False)
    state = {
        **{k: (v.item() if hasattr(v, "item") else v) for k, v in base.items()},
        "pre_world_status": "READY_FOR_EXACT_RU_WORLDS",
        "country_geometry_canonical_sha256": verified,
        "historical_training_occurrence_rows": hist_n,
        "prototype_rows": proto_n,
        "heldout_2021_2025_opened": False,
        "random_baseline_run": False,
        "recall_or_lift_read": False,
        "validated_japan_core_changed": False,
    }
    (output / "pair_state.json").write_text(json.dumps(state, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    return state


def _write_pre_world_sentinel(output: Path, base: dict[str, object], geometry_digest: str, reason: str, *, historical_rows: int) -> dict[str, object]:
    state = {
        **{k: (v.item() if hasattr(v, "item") else v) for k, v in base.items()},
        "pre_world_status": "SENTINEL_OR_ABSTAIN",
        "country_geometry_canonical_sha256": geometry_digest,
        "historical_training_occurrence_rows": int(historical_rows),
        "prototype_rows": 0,
        "evidence_failure_reason": reason,
        "heldout_2021_2025_opened": False,
        "random_baseline_run": False,
        "recall_or_lift_read": False,
        "validated_japan_core_changed": False,
    }
    (output / "pair_state.json").write_text(json.dumps(state, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    return state


def world_shard(surface_path: Path, surface_manifest_path: Path, pair_prep: Path, shard_id: int, output: Path) -> dict[str, object]:
    surface_manifest = verify_surface(surface_path, surface_manifest_path)
    shard_id = int(shard_id)
    if not 0 <= shard_id < WORLD_SHARD_COUNT:
        raise ValueError("invalid RU world shard id")
    state = json.loads((Path(pair_prep) / "pair_state.json").read_text(encoding="utf-8"))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if state["pre_world_status"] != "READY_FOR_EXACT_RU_WORLDS":
        meta = {"availability_pair_id": RU_PAIR_ID, "shard_id": shard_id, "status": "skipped_pre_world_sentinel", "removed_prototype_indices": []}
        (output / "world_manifest.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        return meta
    prototypes = pd.read_parquet(Path(pair_prep) / "prototypes.parquet").reset_index(drop=True)
    surface = pd.read_parquet(surface_path)
    if len(surface) != int(surface_manifest["complete_terrain_surface_points"]):
        raise ValueError("pinned RU surface row count drift")
    if not surface[list(ROBUST_TERRAIN_FEATURES)].notna().all(axis=1).all():
        raise ValueError("pinned RU surface contains incomplete robust terrain rows")
    removed_indices: list[int] = []
    worlds: list[np.ndarray] = []
    kernel_scales: list[float] = []
    for removed in range(len(prototypes)):
        if removed % WORLD_SHARD_COUNT != shard_id:
            continue
        subset = prototypes.drop(index=prototypes.index[removed]).reset_index(drop=True)
        _, support_rank, _, kernel_scale = robust_environment_geometry(surface, subset, feature_columns=ROBUST_TERRAIN_FEATURES)
        removed_indices.append(int(removed))
        worlds.append(np.asarray(support_rank).astype("float32", copy=False))
        kernel_scales.append(float(kernel_scale))
    matrix = np.vstack(worlds) if worlds else np.empty((0, len(surface)), dtype="float32")
    np.savez_compressed(
        output / "worlds.npz",
        removed_indices=np.asarray(removed_indices, dtype=np.int16),
        worlds=matrix,
        kernel_scales=np.asarray(kernel_scales, dtype=np.float64),
    )
    meta = {
        "availability_pair_id": RU_PAIR_ID,
        "shard_id": shard_id,
        "status": "computed",
        "prototype_rows": int(len(prototypes)),
        "surface_rows": int(len(surface)),
        "removed_prototype_indices": removed_indices,
        "support_world_dtype": str(matrix.dtype),
    }
    (output / "world_manifest.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


def assemble_pair(surface_path: Path, surface_manifest_path: Path, pair_prep: Path, worlds_root: Path, output: Path) -> dict[str, object]:
    surface_manifest = verify_surface(surface_path, surface_manifest_path)
    base = frozen_ru_base()
    state = json.loads((Path(pair_prep) / "pair_state.json").read_text(encoding="utf-8"))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if state["pre_world_status"] != "READY_FOR_EXACT_RU_WORLDS":
        pd.DataFrame().to_csv(output / "candidate_patches.csv", index=False)
        result = {
            **state,
            "preheldout_availability_state": "SENTINEL_OR_ABSTAIN",
            "candidate_patch_count": 0,
            "ru_candidate_surface_sha256": EXPECTED_SURFACE_SHA256,
            "ru_surface_manifest_sha256": EXPECTED_SURFACE_MANIFEST_SHA256,
        }
        (output / "pair_result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
        return result
    prototypes = pd.read_parquet(Path(pair_prep) / "prototypes.parquet").reset_index(drop=True)
    surface = pd.read_parquet(surface_path)
    records: list[tuple[int, np.ndarray]] = []
    for directory in sorted(Path(worlds_root).glob("global-parity-ru-world-48-*")):
        if not directory.is_dir():
            continue
        payload = np.load(directory / "worlds.npz")
        indices = np.asarray(payload["removed_indices"], dtype=int)
        worlds = np.asarray(payload["worlds"])
        if worlds.dtype != np.float32:
            raise ValueError("RU support world dtype drift")
        records.extend((int(removed), np.asarray(worlds[i])) for i, removed in enumerate(indices.tolist()))
    records.sort(key=lambda item: item[0])
    if [item[0] for item in records] != list(range(len(prototypes))):
        raise ValueError("RU world reassembly did not restore exact removed-prototype order")
    stack = np.vstack([item[1] for item in records])
    consensus = np.median(stack, axis=0)
    _, raw_zones = exact_fast_support_cells_to_patches(
        surface,
        consensus,
        threshold=float(VALIDATED_ROBUST_SUPPORT_FRACTION),
        merge_distance_m=float(VALIDATED_ROBUST_PATCH_MERGE_DISTANCE_M),
        area_col="survey_area_id",
        ecological_status="validated_cross_taxon_robust_support_patch",
    )
    patches = _project_validated_patch_table(raw_zones, area_col="survey_area_id")
    if not patches.empty:
        patches = patches.copy()
        patches["availability_pair_id"] = RU_PAIR_ID
        patches["speciesKey"] = int(base["speciesKey"])
        patches["scientific_name"] = str(base["scientific_name"])
        patches["taxon_group"] = str(base["taxon_group"])
        patches["framing_country_code"] = RU_CODE
    patches_path = output / "candidate_patches.csv"
    patches.to_csv(patches_path, index=False)
    result = {
        **state,
        "preheldout_availability_state": "ROBUST_READY_PREHELDOUT" if len(patches) > 0 else "ROBUST_EMPTY",
        "regional_tile_count": int(surface_manifest.get("intersecting_tile_count", 0)),
        "geometry_surface_points": int(surface_manifest.get("total_geometry_points", len(surface))),
        "complete_terrain_surface_points": int(len(surface)),
        "candidate_patch_count": int(len(patches)),
        "candidate_patches_sha256": _sha256_file(patches_path),
        "ru_candidate_surface_sha256": EXPECTED_SURFACE_SHA256,
        "ru_surface_manifest_sha256": EXPECTED_SURFACE_MANIFEST_SHA256,
        "support_world_dtype": "float32",
        "world_shard_count": WORLD_SHARD_COUNT,
        "heldout_2021_2025_opened": False,
        "random_baseline_run": False,
        "recall_or_lift_read": False,
        "validated_japan_core_changed": False,
    }
    (output / "pair_result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--output", type=Path, required=True)
    w = sub.add_parser("world-shard")
    w.add_argument("--surface", type=Path, required=True)
    w.add_argument("--surface-manifest", type=Path, required=True)
    w.add_argument("--pair-prep", type=Path, required=True)
    w.add_argument("--shard-id", type=int, required=True)
    w.add_argument("--output", type=Path, required=True)
    a = sub.add_parser("assemble")
    a.add_argument("--surface", type=Path, required=True)
    a.add_argument("--surface-manifest", type=Path, required=True)
    a.add_argument("--pair-prep", type=Path, required=True)
    a.add_argument("--worlds-root", type=Path, required=True)
    a.add_argument("--output", type=Path, required=True)
    v = sub.add_parser("verify-surface")
    v.add_argument("--surface", type=Path, required=True)
    v.add_argument("--surface-manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        result = prepare_pair(args.output)
    elif args.command == "world-shard":
        result = world_shard(args.surface, args.surface_manifest, args.pair_prep, args.shard_id, args.output)
    elif args.command == "assemble":
        result = assemble_pair(args.surface, args.surface_manifest, args.pair_prep, args.worlds_root, args.output)
    elif args.command == "verify-surface":
        result = verify_surface(args.surface, args.surface_manifest)
    else:
        raise AssertionError(args.command)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
