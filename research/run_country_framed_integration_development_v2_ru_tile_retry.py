#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from acsp.taxon_patches import RAW_TERRAIN_FEATURES, ROBUST_TERRAIN_FEATURES, _prototype_coordinates, _with_robust_features
from acsp.validated_robust import VALIDATED_ROBUST_PRIMARY_RADIUS_KM, validated_robust_candidate_patches
from country_framed_robust_integration import fetch_country_occurrences
from geoboundaries_v6_provider import fetch_geoboundaries_country_geometry
from regional_country_lattice import POINTS_PER_REGIONAL_TILE, build_regional_country_surface, iter_country_regional_tiles, sample_regional_tile
from run_country_framed_integration_development_v1_1 import (
    _geometry_digest_from_source_version,
    fetch_recent_country_occurrences,
    recovery_fraction,
    same_size_random_recovery,
)
from run_country_framed_integration_development_v2 import EXPECTED_PROTOCOL_FINGERPRINT, _protocol
from run_country_framed_integration_development_v2_timeout_retry_pair import EXPECTED_RETRY_FINGERPRINT

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "validation" / "acsp_country_framed_robust_integration_development_v2_ru_tile_retry_v1.json"
EXPECTED_EXECUTION_FINGERPRINT = "f3b58b3cb439fdea74009703d815a22b009a5dcac14e257ad9762e6d41347433"
RU_CODE = "RU"
RU_PAIR_IDS = (2, 7, 9, 16)
RU_GEOMETRY_SHA256 = "48d1a32e30c5bab33c7cd39ad9b8b1976a385848f9e6aea0c169acfd67b8b6e2"
PARENT_RETRY_RUN_ID = 32721251040


def _contract() -> dict[str, object]:
    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    stored = str(payload.pop("execution_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if stored != EXPECTED_EXECUTION_FINGERPRINT or calculated != EXPECTED_EXECUTION_FINGERPRINT:
        raise ValueError("RU tile retry execution fingerprint mismatch")
    if payload["authoritative_protocol_fingerprint"] != EXPECTED_PROTOCOL_FINGERPRINT:
        raise ValueError("RU tile retry no longer targets authoritative v2 protocol")
    if payload["first_retry_execution_fingerprint"] != EXPECTED_RETRY_FINGERPRINT:
        raise ValueError("RU tile retry no longer targets first exact retry")
    rule = payload["execution_rule"]
    for key in (
        "scientific_method_changed", "cohort_changed", "declarations_changed", "tile_selection_changed",
        "tile_sampler_changed", "points_per_tile_changed", "survey_area_id_changed", "prototype_scope_changed",
        "robust_core_changed", "random_baseline_changed", "gates_changed", "outcome_driven_tuning_allowed",
    ):
        if rule[key] is not False:
            raise ValueError(f"RU tile retry contract drift: {key}")
    payload["execution_fingerprint"] = stored
    return payload


def _verify_ru_geometry():
    geom = fetch_geoboundaries_country_geometry(RU_CODE)
    digest = _geometry_digest_from_source_version(geom.source_version)
    if digest != RU_GEOMETRY_SHA256:
        raise ValueError(f"frozen RU geometry digest mismatch: {digest}")
    return geom


def verify_frozen_cohort(path: Path) -> pd.DataFrame:
    contract = _contract()
    frame = pd.read_csv(path)
    if len(frame) != 24 or frame["integration_pair_id"].nunique() != 24:
        raise ValueError("RU tile retry must use exact 24 frozen declarations")
    ru = frame.loc[pd.to_numeric(frame["integration_pair_id"], errors="raise").astype(int).isin(RU_PAIR_IDS)].copy()
    if sorted(ru["integration_pair_id"].astype(int).tolist()) != list(RU_PAIR_IDS):
        raise ValueError("RU tile retry pair identity drift")
    if not ru["selected_country_code"].astype(str).eq(RU_CODE).all():
        raise ValueError("all RU retry pairs must retain frozen country RU")
    if not ru["geometry_canonical_sha256"].astype(str).str.lower().eq(RU_GEOMETRY_SHA256).all():
        raise ValueError("RU frozen declaration geometry digest drift")
    if contract["ru_timeout_pair_ids"] != list(RU_PAIR_IDS):
        raise ValueError("RU retry contract pair ids drift")
    return frame


def _extract_environment(points: pd.DataFrame) -> pd.DataFrame:
    from gbif_fieldmap_builder_app import extract_environment
    return extract_environment(points, list(RAW_TERRAIN_FEATURES), "latitude", "longitude", "2.5m")


def warm_worldclim() -> dict[str, object]:
    from gbif_fieldmap_builder_app import get_worldclim_raster_path
    path = Path(get_worldclim_raster_path("elevation", "2.5m"))
    if not path.is_file():
        raise FileNotFoundError(path)
    return {"path": str(path), "size_bytes": path.stat().st_size}


def terrain_equivalence(tile_count: int = 4) -> dict[str, object]:
    _contract()
    geom = _verify_ru_geometry()
    tiles = list(iter_country_regional_tiles(geom))[: int(tile_count)]
    if len(tiles) != int(tile_count):
        raise ValueError("RU equivalence smoke could not obtain requested tiles")
    frames = []
    for tile_ordinal, tile in enumerate(tiles):
        points = sample_regional_tile(tile, n_points=POINTS_PER_REGIONAL_TILE).copy()
        points["tile_ordinal"] = int(tile_ordinal)
        points["point_ordinal"] = np.arange(len(points), dtype=int)
        frames.append(points)
    geometry = pd.concat(frames, ignore_index=True)
    whole = _with_robust_features(_extract_environment(geometry))
    chunked_frames = []
    for tile_ordinal in range(len(tiles)):
        part = geometry.loc[geometry["tile_ordinal"].eq(tile_ordinal)].copy().reset_index(drop=True)
        chunked_frames.append(_with_robust_features(_extract_environment(part)))
    chunked = pd.concat(chunked_frames, ignore_index=True)
    key_cols = ["latitude", "longitude", "regional_tile_id", "tile_ordinal", "point_ordinal", "survey_area_id"]
    if not whole[key_cols].reset_index(drop=True).equals(chunked[key_cols].reset_index(drop=True)):
        raise AssertionError("tilewise terrain retry changed deterministic geometry row order")
    for col in ROBUST_TERRAIN_FEATURES:
        left = pd.to_numeric(whole[col], errors="coerce").to_numpy(float)
        right = pd.to_numeric(chunked[col], errors="coerce").to_numpy(float)
        if not np.array_equal(np.isnan(left), np.isnan(right)):
            raise AssertionError(f"tilewise terrain retry changed missing-value mask for {col}")
        if not np.allclose(left, right, rtol=0.0, atol=1e-10, equal_nan=True):
            finite = np.isfinite(left) & np.isfinite(right)
            delta = float(np.max(np.abs(left[finite] - right[finite]))) if finite.any() else float("nan")
            raise AssertionError(f"tilewise terrain retry changed {col}; max_abs_delta={delta}")
    return {"ru_tiles_tested": len(tiles), "rows_tested": len(geometry), "terrain_values_equivalent": True}


def terrain_shard(shard_id: int, shard_count: int, output: Path) -> dict[str, object]:
    contract = _contract()
    geom = _verify_ru_geometry()
    tiles = list(iter_country_regional_tiles(geom))
    shard_id = int(shard_id); shard_count = int(shard_count)
    if shard_count != int(contract["execution_rule"]["terrain_shard_count"]):
        raise ValueError("terrain shard count drift")
    if not 0 <= shard_id < shard_count:
        raise ValueError("invalid terrain shard id")
    frames = []
    selected = []
    for tile_ordinal, tile in enumerate(tiles):
        if tile_ordinal % shard_count != shard_id:
            continue
        points = sample_regional_tile(tile, n_points=POINTS_PER_REGIONAL_TILE).copy()
        points["tile_ordinal"] = int(tile_ordinal)
        points["point_ordinal"] = np.arange(len(points), dtype=int)
        enriched = _extract_environment(points)
        frames.append(enriched)
        selected.append(tile.tile_id)
    if not frames:
        raise ValueError(f"RU terrain shard {shard_id} selected no tiles")
    out = pd.concat(frames, ignore_index=True)
    output.mkdir(parents=True, exist_ok=True)
    out.to_parquet(output / f"terrain_shard_{shard_id:02d}.parquet", index=False)
    manifest = {
        "shard_id": shard_id,
        "shard_count": shard_count,
        "total_ru_tiles": len(tiles),
        "selected_tile_count": len(selected),
        "selected_tile_ids": selected,
        "geometry_rows": len(out),
        "points_per_tile": POINTS_PER_REGIONAL_TILE,
        "ru_geometry_canonical_sha256": RU_GEOMETRY_SHA256,
        "ru_tile_retry_execution_fingerprint": EXPECTED_EXECUTION_FINGERPRINT,
        "scientific_method_changed": False,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def assemble_surface(input_root: Path, output: Path) -> dict[str, object]:
    contract = _contract()
    expected_shards = int(contract["execution_rule"]["terrain_shard_count"])
    manifests = sorted(input_root.glob("ru-terrain-shard-*/manifest.json"))
    parquet_files = sorted(input_root.glob("ru-terrain-shard-*/terrain_shard_*.parquet"))
    if len(manifests) != expected_shards or len(parquet_files) != expected_shards:
        raise ValueError(f"expected {expected_shards} RU terrain shards; manifests={len(manifests)} parquet={len(parquet_files)}")
    meta = [json.loads(path.read_text(encoding="utf-8")) for path in manifests]
    if sorted(int(item["shard_id"]) for item in meta) != list(range(expected_shards)):
        raise ValueError("RU terrain shard ids are incomplete")
    total_tiles_values = {int(item["total_ru_tiles"]) for item in meta}
    if len(total_tiles_values) != 1:
        raise ValueError("RU shard total tile count drift")
    total_tiles = total_tiles_values.pop()
    raw = pd.concat([pd.read_parquet(path) for path in parquet_files], ignore_index=True)
    raw["tile_ordinal"] = pd.to_numeric(raw["tile_ordinal"], errors="raise").astype(int)
    raw["point_ordinal"] = pd.to_numeric(raw["point_ordinal"], errors="raise").astype(int)
    raw = raw.sort_values(["tile_ordinal", "point_ordinal"], kind="mergesort").reset_index(drop=True)
    counts = raw.groupby("tile_ordinal", sort=True).size()
    if len(counts) != total_tiles or not counts.eq(POINTS_PER_REGIONAL_TILE).all():
        raise ValueError("assembled RU terrain shards do not preserve exactly 800 geometry rows per tile")

    geom = _verify_ru_geometry()
    geometry, audit = build_regional_country_surface(geom, points_per_tile=POINTS_PER_REGIONAL_TILE)
    geometry = geometry.copy()
    geometry["tile_ordinal"] = geometry.groupby("regional_tile_id", sort=False).ngroup().astype(int)
    geometry["point_ordinal"] = geometry.groupby("regional_tile_id", sort=False).cumcount().astype(int)
    geometry = geometry.sort_values(["tile_ordinal", "point_ordinal"], kind="mergesort").reset_index(drop=True)
    key_cols = ["latitude", "longitude", "regional_tile_id", "survey_area_id", "tile_ordinal", "point_ordinal"]
    if len(raw) != len(geometry):
        raise ValueError("assembled RU terrain surface row count differs from frozen geometry sampler")
    if not raw[key_cols].reset_index(drop=True).equals(geometry[key_cols].reset_index(drop=True)):
        raise ValueError("assembled RU terrain surface does not exactly preserve frozen geometry rows/order")

    full = _with_robust_features(raw)
    complete_mask = full[list(ROBUST_TERRAIN_FEATURES)].notna().all(axis=1)
    complete = full.loc[complete_mask].copy().reset_index(drop=True)
    if complete.empty:
        raise ValueError("RU tilewise complete terrain surface is empty")
    output.mkdir(parents=True, exist_ok=True)
    complete.to_parquet(output / "ru_complete_surface.parquet", index=False)
    manifest = {
        "country_code": RU_CODE,
        "intersecting_tile_count": int(audit.intersecting_tile_count),
        "points_per_tile": int(POINTS_PER_REGIONAL_TILE),
        "geometry_surface_points": int(len(raw)),
        "complete_terrain_surface_points": int(len(complete)),
        "complete_fraction": float(len(complete) / len(raw)),
        "geometry_rows_match_frozen_sampler": True,
        "survey_area_id": "country-RU",
        "ru_geometry_canonical_sha256": RU_GEOMETRY_SHA256,
        "ru_tile_retry_execution_fingerprint": EXPECTED_EXECUTION_FINGERPRINT,
        "scientific_method_changed": False,
    }
    (output / "surface_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def evaluate_ru_pair(declarations_path: Path, surface_path: Path, surface_manifest_path: Path, pair_id: int, output: Path) -> dict[str, object]:
    protocol = _protocol(); _contract()
    declarations = verify_frozen_cohort(declarations_path)
    pair_id = int(pair_id)
    if pair_id not in RU_PAIR_IDS:
        raise ValueError("RU surface retry may evaluate only timed-out RU pair ids")
    hit = declarations.loc[pd.to_numeric(declarations["integration_pair_id"], errors="raise").astype(int).eq(pair_id)]
    if len(hit) != 1:
        raise ValueError(f"expected one frozen declaration for pair {pair_id}")
    base = hit.iloc[0].to_dict(); key = int(base["speciesKey"]); code = str(base["selected_country_code"]).upper()
    if code != RU_CODE or str(base["geometry_canonical_sha256"]).lower() != RU_GEOMETRY_SHA256:
        raise ValueError("RU frozen declaration drift")
    surface = pd.read_parquet(surface_path)
    surface_manifest = json.loads(surface_manifest_path.read_text(encoding="utf-8"))
    if surface_manifest["ru_tile_retry_execution_fingerprint"] != EXPECTED_EXECUTION_FINGERPRINT:
        raise ValueError("RU surface artifact execution fingerprint drift")
    if len(surface) != int(surface_manifest["complete_terrain_surface_points"]):
        raise ValueError("RU complete surface row count drift")
    if not surface[list(ROBUST_TERRAIN_FEATURES)].notna().all(axis=1).all():
        raise ValueError("RU complete surface contains incomplete terrain rows")

    evalcfg = protocol["evaluation"]
    radius = float(evalcfg["primary_recovery_radius_km"]); reps = int(evalcfg["random_baseline_repetitions"]); seedbase = int(evalcfg["random_seed"])
    if radius != 10.0 or radius != float(VALIDATED_ROBUST_PRIMARY_RADIUS_KM):
        raise ValueError("RU retry radius drift")
    cstatus = "not_attempted_declaration_failed"; creason = ""; tstatus = "not_attempted_no_declared_country"; treason = ""
    hist_n = recent_n = proto_n = patch_n = 0
    robust = random_mean = random_q025 = random_q975 = lift = float("nan")
    verified = ""; patches = pd.DataFrame()
    if str(base.get("declaration_status") or "") == "declared":
        try:
            geom = _verify_ru_geometry(); verified = _geometry_digest_from_source_version(geom.source_version)
            historical = fetch_country_occurrences(key, code); hist_n = len(historical)
            proto_points = _prototype_coordinates(historical)
            prototypes = _extract_environment(proto_points)
            prototypes = _with_robust_features(prototypes)
            prototypes = prototypes.loc[prototypes[list(ROBUST_TERRAIN_FEATURES)].notna().all(axis=1)].copy().drop_duplicates(list(ROBUST_TERRAIN_FEATURES)).reset_index(drop=True)
            proto_n = len(prototypes)
            if proto_n < 5:
                raise ValueError(f"fewer than five unique complete historical terrain prototypes: {proto_n}")
            patches, _ = validated_robust_candidate_patches(surface, prototypes, feature_columns=ROBUST_TERRAIN_FEATURES, area_col="survey_area_id")
            patch_n = len(patches)
            if patch_n <= 0:
                raise ValueError("frozen robust core returned zero candidate patches")
            cstatus = "generated"
            patches = patches.copy()
            patches["integration_pair_id"] = pair_id; patches["speciesKey"] = key; patches["scientific_name"] = str(base["scientific_name"])
            patches["taxon_group"] = str(base["taxon_group"]); patches["framing_country_code"] = code
        except Exception as exc:
            cstatus = "candidate_generation_failed"; creason = f"{type(exc).__name__}: {exc}"
        try:
            recent = fetch_recent_country_occurrences(key, code, years=(2021, 2025), cap=300); recent_n = len(recent)
            tstatus = "evaluated" if recent_n > 0 else "zero_recent_country_records"
        except Exception as exc:
            recent = pd.DataFrame(columns=["latitude", "longitude"]); tstatus = "recent_provider_failed"; treason = f"{type(exc).__name__}: {exc}"
        if cstatus == "generated" and tstatus == "evaluated":
            robust = recovery_fraction(recent, patches, radius)
            token = f"{seedbase}|{key}|{code}".encode(); rs = int(hashlib.sha256(token).hexdigest()[:16], 16) % (2**32 - 1)
            random_mean, random_q025, random_q975 = same_size_random_recovery(recent, surface, selected_count=patch_n, radius_km=radius, repetitions=reps, seed=rs)
            lift = float(robust - random_mean)
    row = {
        **base,
        "candidate_generation_status": cstatus,
        "candidate_generation_failure_reason": creason,
        "temporal_status": tstatus,
        "temporal_failure_reason": treason,
        "historical_training_occurrence_rows": hist_n,
        "recent_heldout_occurrence_rows": recent_n,
        "regional_tile_count": int(surface_manifest["intersecting_tile_count"]),
        "geometry_surface_points": int(surface_manifest["geometry_surface_points"]),
        "complete_terrain_surface_points": len(surface),
        "prototype_rows": proto_n,
        "candidate_patch_count": patch_n,
        "verified_geometry_canonical_sha256": verified,
        "primary_radius_km": radius,
        "robust_recall": robust,
        "random_recall_mean": random_mean,
        "random_recall_q025": random_q025,
        "random_recall_q975": random_q975,
        "robust_minus_random_recall": lift,
        "retry_execution_fingerprint": EXPECTED_RETRY_FINGERPRINT,
        "ru_tile_retry_execution_fingerprint": EXPECTED_EXECUTION_FINGERPRINT,
    }
    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([row]).to_csv(output / "taxon_country_results.csv", index=False)
    patches.to_csv(output / "integrated_candidate_patches.csv", index=False)
    manifest = {
        "integration_pair_id": pair_id,
        "authoritative_protocol_fingerprint": EXPECTED_PROTOCOL_FINGERPRINT,
        "retry_execution_fingerprint": EXPECTED_RETRY_FINGERPRINT,
        "scientific_method_changed": False,
        "declaration_reselected": False,
        "ru_tile_retry_execution_fingerprint": EXPECTED_EXECUTION_FINGERPRINT,
        "ru_surface_reused_across_ru_taxa": True,
    }
    (output / "pair_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def finalize_summary(result_dir: Path) -> dict[str, object]:
    _contract()
    summary_path = result_dir / "development_summary.json"
    results_path = result_dir / "taxon_country_results.csv"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    results = pd.read_csv(results_path)
    ru = results.loc[pd.to_numeric(results["integration_pair_id"], errors="raise").astype(int).isin(RU_PAIR_IDS)].copy()
    if len(ru) != 4 or not ru["ru_tile_retry_execution_fingerprint"].astype(str).eq(EXPECTED_EXECUTION_FINGERPRINT).all():
        raise ValueError("final v2 result does not contain all four RU tile retry rows")
    summary.update({
        "ru_tile_retry_execution_fingerprint": EXPECTED_EXECUTION_FINGERPRINT,
        "ru_tile_retry_parent_run_id": PARENT_RETRY_RUN_ID,
        "ru_tile_retry_pair_ids": list(RU_PAIR_IDS),
        "ru_tile_retry_scientific_method_changed": False,
        "ru_tile_retry_reason": "all four frozen RU pairs exceeded the 300-minute per-job limit under whole-country terrain extraction; only terrain execution was tiled",
    })
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)
    v = sub.add_parser("verify"); v.add_argument("--declarations", type=Path, required=True)
    sub.add_parser("warm-worldclim")
    e = sub.add_parser("equivalence"); e.add_argument("--tile-count", type=int, default=4)
    s = sub.add_parser("terrain-shard"); s.add_argument("--shard-id", type=int, required=True); s.add_argument("--shard-count", type=int, required=True); s.add_argument("--output", type=Path, required=True)
    a = sub.add_parser("assemble-surface"); a.add_argument("--input-root", type=Path, required=True); a.add_argument("--output", type=Path, required=True)
    r = sub.add_parser("evaluate-pair"); r.add_argument("--declarations", type=Path, required=True); r.add_argument("--surface", type=Path, required=True); r.add_argument("--surface-manifest", type=Path, required=True); r.add_argument("--pair-id", type=int, required=True); r.add_argument("--output", type=Path, required=True)
    f = sub.add_parser("finalize"); f.add_argument("--result-dir", type=Path, required=True)
    args = p.parse_args(argv)
    if args.command == "verify": out = {"frozen_rows": len(verify_frozen_cohort(args.declarations)), "contract": _contract()}
    elif args.command == "warm-worldclim": out = warm_worldclim()
    elif args.command == "equivalence": out = terrain_equivalence(args.tile_count)
    elif args.command == "terrain-shard": out = terrain_shard(args.shard_id, args.shard_count, args.output)
    elif args.command == "assemble-surface": out = assemble_surface(args.input_root, args.output)
    elif args.command == "evaluate-pair": out = evaluate_ru_pair(args.declarations, args.surface, args.surface_manifest, args.pair_id, args.output)
    elif args.command == "finalize": out = finalize_summary(args.result_dir)
    else: raise AssertionError(args.command)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
