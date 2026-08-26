#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

import run_replication_ru_robust_world_recovery as _ru
from country_framed_fresh_heterogeneity_execution import (
    EXPECTED_COHORT_MANIFEST_SHA256,
    EXPECTED_FRESH_EXECUTION_FINGERPRINT,
    EXPECTED_FRESH_PROTOCOL_FINGERPRINT,
    EXPECTED_IDENTITY_SHA256,
    RU_PAIR_IDS,
    SOURCE_COHORT_ARTIFACT_ID,
    SOURCE_COHORT_RUN_ID,
    execution_contract,
    verify_frozen_cohort,
)
from predeclare_country_framed_integration_development_v2 import EXPECTED_PROTOCOL_FINGERPRINT

WORLD_SHARD_COUNT = 8
WORLD_ARTIFACT_PREFIX = "fresh-ru-world"


def _configure_exact_ru_module() -> None:
    # Rebind only frozen identities/provenance. Scientific operations stay in the
    # already equivalence-tested RU recovery implementation.
    _ru.EXPECTED_RECOVERY_FINGERPRINT = EXPECTED_FRESH_EXECUTION_FINGERPRINT
    _ru.EXPECTED_IDENTITY_SHA256 = EXPECTED_IDENTITY_SHA256
    _ru.EXPECTED_COHORT_MANIFEST_SHA256 = EXPECTED_COHORT_MANIFEST_SHA256
    _ru.SOURCE_REPLICATION_RUN_ID = SOURCE_COHORT_RUN_ID
    _ru.SOURCE_COHORT_ARTIFACT_ID = SOURCE_COHORT_ARTIFACT_ID
    _ru.RU_PAIR_IDS = RU_PAIR_IDS
    _ru.EXPECTED_REPLICATION_PROTOCOL_FINGERPRINT = EXPECTED_FRESH_PROTOCOL_FINGERPRINT
    _ru.EXPECTED_EXECUTION_FINGERPRINT = EXPECTED_FRESH_EXECUTION_FINGERPRINT
    _ru.recovery_contract = execution_contract
    _ru.verify_cohort = verify_frozen_cohort
    _ru._world_dirs = lambda root, pair_id: sorted(
        p for p in Path(root).glob(f"{WORLD_ARTIFACT_PREFIX}-{int(pair_id)}-*") if p.is_dir()
    )


def _annotate_assembled(output: Path, pair_id: int) -> dict[str, object]:
    result_path = output / "taxon_country_results.csv"
    manifest_path = output / "pair_manifest.json"
    result = pd.read_csv(result_path)
    result["fresh_protocol_fingerprint"] = EXPECTED_FRESH_PROTOCOL_FINGERPRINT
    result["fresh_execution_fingerprint"] = EXPECTED_FRESH_EXECUTION_FINGERPRINT
    result.to_csv(result_path, index=False)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "integration_pair_id": int(pair_id),
            "fresh_protocol_fingerprint": EXPECTED_FRESH_PROTOCOL_FINGERPRINT,
            "fresh_execution_fingerprint": EXPECTED_FRESH_EXECUTION_FINGERPRINT,
            "authoritative_v2_protocol_fingerprint": EXPECTED_PROTOCOL_FINGERPRINT,
            "scientific_method_changed": False,
            "cohort_reselected": False,
            "declaration_reselected": False,
            "candidate_generation_preceded_recent_outcome_fetch": True,
            "ru_execution": True,
            "fresh_ru_pair_ids": list(RU_PAIR_IDS),
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    _configure_exact_ru_module()
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
            "execution": execution_contract(),
            "cohort_rows": len(verify_frozen_cohort(args.declarations, args.cohort_manifest)),
            "surface_manifest": _ru.verify_surface(args.surface, args.surface_manifest),
        }
    elif args.command == "prepare-pair":
        if int(args.pair_id) not in RU_PAIR_IDS:
            raise ValueError("fresh RU prepare may use only frozen RU pair IDs")
        out = _ru.prepare_pair(args.declarations, args.cohort_manifest, args.pair_id, args.output)
    elif args.command == "world-shard":
        if int(args.pair_id) not in RU_PAIR_IDS or not 0 <= int(args.shard_id) < WORLD_SHARD_COUNT:
            raise ValueError("invalid frozen RU pair/shard")
        out = _ru.world_shard(
            args.surface,
            args.surface_manifest,
            args.pair_prep,
            args.pair_id,
            args.shard_id,
            args.output,
        )
    elif args.command == "assemble-pair":
        if int(args.pair_id) not in RU_PAIR_IDS:
            raise ValueError("fresh RU assemble may use only frozen RU pair IDs")
        _ru.assemble_pair(
            args.declarations,
            args.cohort_manifest,
            args.surface,
            args.surface_manifest,
            args.pair_prep,
            args.worlds_root,
            args.pair_id,
            args.output,
        )
        out = _annotate_assembled(args.output, args.pair_id)
    else:
        raise AssertionError(args.command)

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
