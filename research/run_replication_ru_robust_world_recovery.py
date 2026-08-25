#!/usr/bin/env python3
"""Exact technical recovery for RU pairs in the frozen v2 replication.

This recovery never re-freezes identities. It consumes the exact cohort artifact
from replication run 1 and the previously verified complete RU terrain surface.
For only source jobs that actually time out, it partitions the unchanged
float32 leave-one-prototype-out worlds into eight execution shards, restores the
original removed-prototype order, applies the same median / 2.5% support tier,
and uses the already-proven exact 1 km complete-link lookup acceleration.
Held-out 2021-2025 records are opened only after candidate patches are complete.
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
from acsp.taxon_patches import (
    RAW_TERRAIN_FEATURES,
    ROBUST_TERRAIN_FEATURES,
    _prototype_coordinates,
    _with_robust_features,
)
from acsp.validated_robust import (
    VALIDATED_ROBUST_PATCH_MERGE_DISTANCE_M,
    VALIDATED_ROBUST_PRIMARY_RADIUS_KM,
    VALIDATED_ROBUST_SUPPORT_FRACTION,
    _project_validated_patch_table,
)
from country_framed_robust_integration import fetch_country_occurrences
from country_framed_integration_v2_replication_execution_contract import EXPECTED_EXECUTION_FINGERPRINT
from exact_fast_complete_link import exact_fast_support_cells_to_patches
from predeclare_country_framed_integration_development_v2 import EXPECTED_PROTOCOL_FINGERPRINT, _protocol
from predeclare_country_framed_integration_development_v2_replication import EXPECTED_REPLICATION_PROTOCOL_FINGERPRINT
from run_country_framed_integration_development_v1_1 import (
    _geometry_digest_from_source_version,
    fetch_recent_country_occurrences,
    recovery_fraction,
    same_size_random_recovery,
)
from run_country_framed_integration_development_v2_ru_tile_retry import RU_GEOMETRY_SHA256, _verify_ru_geometry
from run_ru_robust_world_shard_fallback import verify_surface as verify_pinned_ru_surface

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "validation" / "acsp_country_framed_robust_integration_development_v2_replication_ru_recovery_v1.json"
EXPECTED_RECOVERY_FINGERPRINT = "694e838b02717a20429070e291d7226c1b7c2c575d736020895f2676c1cbb504"
EXPECTED_IDENTITY_SHA256 = "98457e5586d32c84fac60b2e159371e3771fd0965a47c80de7f98a71f7186a85"
EXPECTED_COHORT_MANIFEST_SHA256 = "5b82c8fa86e6b99ecf26e98fe1469149da946657924763b0c6ccb048b15bd54f"
EXPECTED_SURFACE_SHA256 = "77729dfa45b9e123f035ca15a421f834a6b155140ae410b8806e9f4eca19c982"
EXPECTED_SURFACE_MANIFEST_SHA256 = "a4cd321cee240f050d4223ab19b3af8f956ac80d675229703d2dffdbb0908d7e"
SOURCE_REPLICATION_RUN_ID = 32811169261
SOURCE_COHORT_ARTIFACT_ID = 9549850449
SOURCE_RU_SURFACE_RUN_ID = 32795662847
SOURCE_RU_SURFACE_ARTIFACT_ID = 9544853686
RU_PAIR_IDS = (1, 4, 15, 19)
WORLD_SHARD_COUNT = 8
RU_CODE = "RU"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonable(value):
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if pd.isna(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return str(value)


def recovery_contract() -> dict[str, object]:
    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    stored = str(payload.pop("execution_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if stored != EXPECTED_RECOVERY_FINGERPRINT or calculated != EXPECTED_RECOVERY_FINGERPRINT:
        raise ValueError("replication RU recovery fingerprint mismatch")
    source = payload["source_replication"]
    if int(source["workflow_run_id"]) != SOURCE_REPLICATION_RUN_ID or int(source["workflow_run_number"]) != 1:
        raise ValueError("replication source run drift")
    if int(source["cohort_artifact_id"]) != SOURCE_COHORT_ARTIFACT_ID:
        raise ValueError("replication cohort artifact drift")
    if source["replication_protocol_fingerprint"] != EXPECTED_REPLICATION_PROTOCOL_FINGERPRINT:
        raise ValueError("replication protocol drift")
    if source["replication_execution_fingerprint"] != EXPECTED_EXECUTION_FINGERPRINT:
        raise ValueError("replication execution drift")
    if tuple(int(x) for x in source["ru_pair_ids"]) != RU_PAIR_IDS:
        raise ValueError("frozen RU pair ids drift")
    surface = payload["ru_surface_source"]
    if int(surface["workflow_run_id"]) != SOURCE_RU_SURFACE_RUN_ID or int(surface["artifact_id"]) != SOURCE_RU_SURFACE_ARTIFACT_ID:
        raise ValueError("pinned RU surface source drift")
    if surface["ru_complete_surface_parquet_sha256"] != EXPECTED_SURFACE_SHA256:
        raise ValueError("pinned RU surface digest drift")
    if surface["surface_manifest_sha256"] != EXPECTED_SURFACE_MANIFEST_SHA256:
        raise ValueError("pinned RU surface manifest digest drift")
    rule = payload["execution_rule"]
    if int(rule["world_shard_count"]) != WORLD_SHARD_COUNT or rule["support_world_dtype"] != "float32":
        raise ValueError("world-shard representation drift")
    if int(rule["max_prototypes"]) != 32 or rule["world_partition_only"] is not True:
        raise ValueError("prototype/world partition drift")
    if rule["patch_lookup_implementation_only"] is not True or rule["patch_equivalence_required"] is not True:
        raise ValueError("patch lookup equivalence contract drift")
    for key in (
        "scientific_method_changed", "cohort_changed", "declarations_changed", "country_changed",
        "country_geometry_changed", "complete_ru_surface_changed", "historical_training_scope_changed",
        "prototype_rule_changed", "leave_one_out_world_definition_changed", "support_world_dtype_changed",
        "consensus_reduction_changed", "support_threshold_changed", "patch_aggregation_changed",
        "patch_compatibility_rule_changed", "patch_tie_break_changed", "patch_projection_changed",
        "random_baseline_changed", "heldout_outcome_opening_order_changed", "gates_changed",
        "outcome_driven_tuning_allowed",
    ):
        if rule[key] is not False:
            raise ValueError(f"recovery contract drift: {key}")
    payload["execution_fingerprint"] = stored
    return payload


def verify_cohort(declarations_path: Path, manifest_path: Path) -> pd.DataFrame:
    recovery_contract()
    if _sha256(declarations_path) != EXPECTED_IDENTITY_SHA256:
        raise ValueError("frozen replication declarations SHA-256 mismatch")
    if _sha256(manifest_path) != EXPECTED_COHORT_MANIFEST_SHA256:
        raise ValueError("frozen replication cohort manifest SHA-256 mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["replication_protocol_fingerprint"] != EXPECTED_REPLICATION_PROTOCOL_FINGERPRINT:
        raise ValueError("frozen cohort replication fingerprint drift")
    if manifest["authoritative_v2_protocol_fingerprint"] != EXPECTED_PROTOCOL_FINGERPRINT:
        raise ValueError("frozen cohort authoritative v2 fingerprint drift")
    if manifest["identity_csv_sha256"] != EXPECTED_IDENTITY_SHA256:
        raise ValueError("cohort manifest identity digest drift")
    if manifest["recent_outcomes_inspected"] is not False or manifest["candidate_generation_run"] is not False:
        raise ValueError("frozen cohort was not identity-only")
    if manifest["replacement_after_declaration_allowed"] is not False or manifest["retuning_allowed"] is not False:
        raise ValueError("frozen cohort permits replacement/retuning")
    declarations = pd.read_csv(declarations_path)
    if len(declarations) != 24 or declarations["speciesKey"].nunique() != 24:
        raise ValueError("frozen replication cohort must contain exactly 24 unique taxa")
    ru_ids = tuple(
        sorted(
            pd.to_numeric(
                declarations.loc[declarations["selected_country_code"].astype(str).str.upper().eq(RU_CODE), "integration_pair_id"],
                errors="raise",
            ).astype(int).tolist()
        )
    )
    if ru_ids != RU_PAIR_IDS:
        raise ValueError(f"frozen replication RU identities drifted: {ru_ids}")
    return declarations


def verify_surface(surface_path: Path, manifest_path: Path) -> dict[str, object]:
    recovery_contract()
    if _sha256(surface_path) != EXPECTED_SURFACE_SHA256:
        raise ValueError("replication recovery RU surface SHA-256 mismatch")
    if _sha256(manifest_path) != EXPECTED_SURFACE_MANIFEST_SHA256:
        raise ValueError("replication recovery RU surface manifest SHA-256 mismatch")
    return verify_pinned_ru_surface(surface_path, manifest_path)


def _frozen_pair(declarations_path: Path, cohort_manifest_path: Path, pair_id: int) -> dict[str, object]:
    declarations = verify_cohort(declarations_path, cohort_manifest_path)
    pair_id = int(pair_id)
    if pair_id not in RU_PAIR_IDS:
        raise ValueError("replication RU recovery may use only frozen RU pair ids")
    hit = declarations.loc[pd.to_numeric(declarations["integration_pair_id"], errors="raise").astype(int).eq(pair_id)]
    if len(hit) != 1:
        raise ValueError(f"expected one frozen declaration for pair {pair_id}")
    base = {str(k): _jsonable(v) for k, v in hit.iloc[0].to_dict().items()}
    if str(base["selected_country_code"]).upper() != RU_CODE:
        raise ValueError("recovery pair country drift")
    if str(base["geometry_canonical_sha256"]).lower() != RU_GEOMETRY_SHA256:
        raise ValueError("recovery pair RU geometry digest drift")
    return base


def _extract_environment(points: pd.DataFrame) -> pd.DataFrame:
    from gbif_fieldmap_builder_app import extract_environment
    return extract_environment(points, list(RAW_TERRAIN_FEATURES), "latitude", "longitude", "2.5m")


def prepare_pair(declarations_path: Path, cohort_manifest_path: Path, pair_id: int, output: Path) -> dict[str, object]:
    recovery_contract()
    base = _frozen_pair(declarations_path, cohort_manifest_path, pair_id)
    key = int(base["speciesKey"])
    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([base]).to_csv(output / "base_declaration.csv", index=False)
    verified = ""
    hist_n = proto_n = 0
    status = "ready"
    failure = ""
    try:
        geom = _verify_ru_geometry()
        verified = _geometry_digest_from_source_version(geom.source_version)
        if verified != RU_GEOMETRY_SHA256:
            raise ValueError("verified RU geometry digest drift")
        historical = fetch_country_occurrences(key, RU_CODE)
        hist_n = int(len(historical))
        prototype_points = _prototype_coordinates(historical)
        prototypes = _with_robust_features(_extract_environment(prototype_points))
        prototypes = prototypes.loc[
            prototypes[list(ROBUST_TERRAIN_FEATURES)].notna().all(axis=1)
        ].copy().drop_duplicates(list(ROBUST_TERRAIN_FEATURES)).reset_index(drop=True)
        proto_n = int(len(prototypes))
        if proto_n < 5:
            raise ValueError(f"fewer than five unique complete historical terrain prototypes: {proto_n}")
        if proto_n > 32:
            raise ValueError(f"prototype rule drift: expected <=32, got {proto_n}")
        prototypes.to_parquet(output / "prototypes.parquet", index=False)
    except Exception as exc:
        status = "candidate_generation_failed_pre_worlds"
        failure = f"{type(exc).__name__}: {exc}"
    state = {
        "integration_pair_id": int(pair_id),
        "speciesKey": key,
        "scientific_name": str(base["scientific_name"]),
        "taxon_group": str(base["taxon_group"]),
        "selected_country_code": RU_CODE,
        "historical_training_occurrence_rows": hist_n,
        "prototype_rows": proto_n,
        "verified_geometry_canonical_sha256": verified,
        "pre_world_status": status,
        "pre_world_failure_reason": failure,
        "replication_protocol_fingerprint": EXPECTED_REPLICATION_PROTOCOL_FINGERPRINT,
        "replication_execution_fingerprint": EXPECTED_EXECUTION_FINGERPRINT,
        "replication_ru_recovery_execution_fingerprint": EXPECTED_RECOVERY_FINGERPRINT,
        "scientific_method_changed": False,
        "declaration_reselected": False,
        "outcome_opened": False,
    }
    (output / "pair_state.json").write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return state


def world_shard(surface_path: Path, surface_manifest_path: Path, pair_prep_dir: Path, pair_id: int, shard_id: int, output: Path) -> dict[str, object]:
    surface_manifest = verify_surface(surface_path, surface_manifest_path)
    pair_id = int(pair_id)
    shard_id = int(shard_id)
    if not 0 <= shard_id < WORLD_SHARD_COUNT:
        raise ValueError("invalid world shard id")
    state = json.loads((pair_prep_dir / "pair_state.json").read_text(encoding="utf-8"))
    if int(state["integration_pair_id"]) != pair_id:
        raise ValueError("world shard pair state mismatch")
    output.mkdir(parents=True, exist_ok=True)
    if state["pre_world_status"] != "ready":
        meta = {
            "integration_pair_id": pair_id,
            "shard_id": shard_id,
            "status": "skipped_pre_world_failure",
            "removed_prototype_indices": [],
            "replication_ru_recovery_execution_fingerprint": EXPECTED_RECOVERY_FINGERPRINT,
            "scientific_method_changed": False,
        }
        (output / "world_manifest.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        return meta
    prototypes = pd.read_parquet(pair_prep_dir / "prototypes.parquet").reset_index(drop=True)
    surface = pd.read_parquet(surface_path)
    if len(surface) != int(surface_manifest["complete_terrain_surface_points"]):
        raise ValueError("surface row count drift")
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
        "integration_pair_id": pair_id,
        "shard_id": shard_id,
        "status": "computed",
        "prototype_rows": int(len(prototypes)),
        "surface_rows": int(len(surface)),
        "removed_prototype_indices": removed_indices,
        "support_world_dtype": str(matrix.dtype),
        "replication_ru_recovery_execution_fingerprint": EXPECTED_RECOVERY_FINGERPRINT,
        "scientific_method_changed": False,
    }
    (output / "world_manifest.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


def _world_dirs(root: Path, pair_id: int) -> list[Path]:
    return sorted(p for p in root.glob(f"replication-ru-recovery-world-{int(pair_id)}-*") if p.is_dir())


def assemble_pair(declarations_path: Path, cohort_manifest_path: Path, surface_path: Path, surface_manifest_path: Path, pair_prep_dir: Path, worlds_root: Path, pair_id: int, output: Path) -> dict[str, object]:
    protocol = _protocol()
    surface_manifest = verify_surface(surface_path, surface_manifest_path)
    base = _frozen_pair(declarations_path, cohort_manifest_path, pair_id)
    state = json.loads((pair_prep_dir / "pair_state.json").read_text(encoding="utf-8"))
    pair_id = int(pair_id)
    surface = pd.read_parquet(surface_path)
    output.mkdir(parents=True, exist_ok=True)
    cstatus = "candidate_generation_failed"
    creason = str(state.get("pre_world_failure_reason") or "")
    patches = pd.DataFrame()
    patch_n = 0
    if state["pre_world_status"] == "ready":
        prototypes = pd.read_parquet(pair_prep_dir / "prototypes.parquet").reset_index(drop=True)
        dirs = _world_dirs(worlds_root, pair_id)
        if len(dirs) != WORLD_SHARD_COUNT:
            raise ValueError(f"expected {WORLD_SHARD_COUNT} world artifacts for pair {pair_id}, got {len(dirs)}")
        records: list[tuple[int, np.ndarray]] = []
        for directory in dirs:
            meta = json.loads((directory / "world_manifest.json").read_text(encoding="utf-8"))
            if int(meta["integration_pair_id"]) != pair_id or meta["status"] != "computed":
                raise ValueError("world artifact identity/status drift")
            if meta["replication_ru_recovery_execution_fingerprint"] != EXPECTED_RECOVERY_FINGERPRINT:
                raise ValueError("world artifact recovery fingerprint drift")
            blob = np.load(directory / "worlds.npz")
            indices = blob["removed_indices"].astype(int)
            worlds = blob["worlds"]
            if worlds.dtype != np.dtype("float32") or len(indices) != len(worlds):
                raise ValueError("world shard dtype/length drift")
            records.extend((int(removed), np.asarray(worlds[i])) for i, removed in enumerate(indices.tolist()))
        records.sort(key=lambda x: x[0])
        if [x[0] for x in records] != list(range(len(prototypes))):
            raise ValueError("world reassembly did not restore exact removed-prototype order")
        stack = np.vstack([x[1] for x in records])
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
        patch_n = int(len(patches))
        if patch_n > 0:
            cstatus = "generated"
            creason = ""
            patches = patches.copy()
            patches["integration_pair_id"] = pair_id
            patches["speciesKey"] = int(base["speciesKey"])
            patches["scientific_name"] = str(base["scientific_name"])
            patches["taxon_group"] = str(base["taxon_group"])
            patches["framing_country_code"] = RU_CODE
        else:
            creason = "ValueError: frozen robust core returned zero candidate patches"

    # Held-out records are opened only after the candidate patch artifact exists in memory.
    recent_n = 0
    tstatus = "not_attempted_no_declared_country"
    treason = ""
    recent = pd.DataFrame(columns=["latitude", "longitude"])
    try:
        recent = fetch_recent_country_occurrences(int(base["speciesKey"]), RU_CODE, years=(2021, 2025), cap=300)
        recent_n = int(len(recent))
        tstatus = "evaluated" if recent_n > 0 else "zero_recent_country_records"
    except Exception as exc:
        tstatus = "recent_provider_failed"
        treason = f"{type(exc).__name__}: {exc}"

    robust = random_mean = random_q025 = random_q975 = lift = float("nan")
    evalcfg = protocol["evaluation"]
    radius = float(evalcfg["primary_recovery_radius_km"])
    reps = int(evalcfg["random_baseline_repetitions"])
    seedbase = int(evalcfg["random_seed"])
    if radius != 10.0 or radius != float(VALIDATED_ROBUST_PRIMARY_RADIUS_KM):
        raise ValueError("recovery radius drift")
    if cstatus == "generated" and tstatus == "evaluated":
        robust = recovery_fraction(recent, patches, radius)
        token = f"{seedbase}|{int(base['speciesKey'])}|{RU_CODE}".encode()
        rs = int(hashlib.sha256(token).hexdigest()[:16], 16) % (2**32 - 1)
        random_mean, random_q025, random_q975 = same_size_random_recovery(
            recent,
            surface,
            selected_count=patch_n,
            radius_km=radius,
            repetitions=reps,
            seed=rs,
        )
        lift = float(robust - random_mean)

    row = {
        **base,
        "candidate_generation_status": cstatus,
        "candidate_generation_failure_reason": creason,
        "temporal_status": tstatus,
        "temporal_failure_reason": treason,
        "historical_training_occurrence_rows": int(state["historical_training_occurrence_rows"]),
        "recent_heldout_occurrence_rows": recent_n,
        "regional_tile_count": int(surface_manifest["intersecting_tile_count"]),
        "geometry_surface_points": int(surface_manifest["geometry_surface_points"]),
        "complete_terrain_surface_points": int(len(surface)),
        "prototype_rows": int(state["prototype_rows"]),
        "candidate_patch_count": patch_n,
        "verified_geometry_canonical_sha256": str(state["verified_geometry_canonical_sha256"]),
        "primary_radius_km": radius,
        "robust_recall": robust,
        "random_recall_mean": random_mean,
        "random_recall_q025": random_q025,
        "random_recall_q975": random_q975,
        "robust_minus_random_recall": lift,
        "replication_protocol_fingerprint": EXPECTED_REPLICATION_PROTOCOL_FINGERPRINT,
        "replication_execution_fingerprint": EXPECTED_EXECUTION_FINGERPRINT,
        "replication_ru_recovery_execution_fingerprint": EXPECTED_RECOVERY_FINGERPRINT,
    }
    pd.DataFrame([row]).to_csv(output / "taxon_country_results.csv", index=False)
    patches.to_csv(output / "integrated_candidate_patches.csv", index=False)
    manifest = {
        "integration_pair_id": pair_id,
        "replication_protocol_fingerprint": EXPECTED_REPLICATION_PROTOCOL_FINGERPRINT,
        "replication_execution_fingerprint": EXPECTED_EXECUTION_FINGERPRINT,
        "authoritative_v2_protocol_fingerprint": EXPECTED_PROTOCOL_FINGERPRINT,
        "scientific_method_changed": False,
        "cohort_reselected": False,
        "declaration_reselected": False,
        "candidate_generation_preceded_recent_outcome_fetch": True,
        "replication_ru_recovery_execution_fingerprint": EXPECTED_RECOVERY_FINGERPRINT,
        "ru_surface_source_run_id": SOURCE_RU_SURFACE_RUN_ID,
        "ru_surface_parquet_sha256": EXPECTED_SURFACE_SHA256,
        "world_shard_count": WORLD_SHARD_COUNT,
        "worlds_reassembled_in_original_order": True,
        "patch_lookup_only_accelerated": True,
    }
    (output / "pair_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--declarations", type=Path, required=True)
    v.add_argument("--cohort-manifest", type=Path, required=True)
    v.add_argument("--surface", type=Path, required=True)
    v.add_argument("--surface-manifest", type=Path, required=True)
    p = sub.add_parser("prepare-pair")
    p.add_argument("--declarations", type=Path, required=True)
    p.add_argument("--cohort-manifest", type=Path, required=True)
    p.add_argument("--pair-id", type=int, required=True)
    p.add_argument("--output", type=Path, required=True)
    w = sub.add_parser("world-shard")
    w.add_argument("--surface", type=Path, required=True)
    w.add_argument("--surface-manifest", type=Path, required=True)
    w.add_argument("--pair-prep", type=Path, required=True)
    w.add_argument("--pair-id", type=int, required=True)
    w.add_argument("--shard-id", type=int, required=True)
    w.add_argument("--output", type=Path, required=True)
    a = sub.add_parser("assemble-pair")
    a.add_argument("--declarations", type=Path, required=True)
    a.add_argument("--cohort-manifest", type=Path, required=True)
    a.add_argument("--surface", type=Path, required=True)
    a.add_argument("--surface-manifest", type=Path, required=True)
    a.add_argument("--pair-prep", type=Path, required=True)
    a.add_argument("--worlds-root", type=Path, required=True)
    a.add_argument("--pair-id", type=int, required=True)
    a.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "verify":
        out = {
            "contract": recovery_contract(),
            "cohort_rows": len(verify_cohort(args.declarations, args.cohort_manifest)),
            "surface_manifest": verify_surface(args.surface, args.surface_manifest),
        }
    elif args.command == "prepare-pair":
        out = prepare_pair(args.declarations, args.cohort_manifest, args.pair_id, args.output)
    elif args.command == "world-shard":
        out = world_shard(args.surface, args.surface_manifest, args.pair_prep, args.pair_id, args.shard_id, args.output)
    elif args.command == "assemble-pair":
        out = assemble_pair(
            args.declarations,
            args.cohort_manifest,
            args.surface,
            args.surface_manifest,
            args.pair_prep,
            args.worlds_root,
            args.pair_id,
            args.output,
        )
    else:
        raise AssertionError(args.command)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
