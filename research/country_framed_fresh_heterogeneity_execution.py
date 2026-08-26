#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from country_framed_integration_v2_pair_core import evaluate_one_v2_core
from predeclare_country_framed_integration_development_v2 import EXPECTED_PROTOCOL_FINGERPRINT

ROOT = Path(__file__).resolve().parents[1]
EXECUTION_PATH = ROOT / "validation" / "acsp_country_framed_fresh_heterogeneity_confirmation_execution_v1.json"
EXPECTED_FRESH_PROTOCOL_FINGERPRINT = "65ba06f174f4bdc9a49c24e54e8f7c67958757ab527fc23e4ccf427bf2d91a01"
EXPECTED_FRESH_EXECUTION_FINGERPRINT = "c8d8009ff692f71b1c076e1ee0e3c957527ea789c5c984011574ddd41f91095b"
EXPECTED_IDENTITY_SHA256 = "6175a892562ece19de543f33bc10aa3d9efe889d849b750550534eb9588b41a3"
EXPECTED_COHORT_MANIFEST_SHA256 = "b2624a2471d493f9627c7728d80436f1c796c5acb63208dcc72fc1ca8d0a68aa"
SOURCE_COHORT_RUN_ID = 32921623531
SOURCE_COHORT_ARTIFACT_ID = 9590098991
RU_PAIR_IDS = (2, 4, 6, 16)
FAILED_DECLARATION_PAIR_IDS = (19, 41)
ALL_PAIR_IDS = tuple(range(1, 49))
NON_RU_PAIR_IDS = tuple(i for i in ALL_PAIR_IDS if i not in RU_PAIR_IDS)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execution_contract() -> dict[str, object]:
    payload = json.loads(EXECUTION_PATH.read_text(encoding="utf-8"))
    stored = str(payload.pop("execution_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if stored != EXPECTED_FRESH_EXECUTION_FINGERPRINT or calculated != EXPECTED_FRESH_EXECUTION_FINGERPRINT:
        raise ValueError("fresh confirmation execution fingerprint mismatch")
    if payload["fresh_protocol_fingerprint"] != EXPECTED_FRESH_PROTOCOL_FINGERPRINT:
        raise ValueError("fresh protocol fingerprint drift")
    if payload["authoritative_v2_fingerprint"] != EXPECTED_PROTOCOL_FINGERPRINT:
        raise ValueError("fresh execution no longer targets authoritative v2")
    source = payload["cohort_source"]
    if int(source["workflow_run_id"]) != SOURCE_COHORT_RUN_ID or int(source["artifact_id"]) != SOURCE_COHORT_ARTIFACT_ID:
        raise ValueError("fresh cohort source drift")
    if source["identity_csv_sha256"] != EXPECTED_IDENTITY_SHA256 or source["manifest_sha256"] != EXPECTED_COHORT_MANIFEST_SHA256:
        raise ValueError("fresh cohort digest drift")
    if tuple(int(x) for x in source["ru_pair_ids"]) != RU_PAIR_IDS:
        raise ValueError("fresh RU pair IDs drift")
    if tuple(int(x) for x in source["failed_country_declaration_pair_ids"]) != FAILED_DECLARATION_PAIR_IDS:
        raise ValueError("fresh declaration-failure IDs drift")
    pair = payload["pair_execution"]
    if tuple(int(x) for x in pair["non_ru_pair_ids"]) != NON_RU_PAIR_IDS:
        raise ValueError("fresh non-RU pair IDs drift")
    if pair["non_ru_runner"] != "unchanged country_framed_integration_v2_pair_core.evaluate_one_v2_core":
        raise ValueError("fresh non-RU runner drift")
    if pair["failed_declarations_remain_in_48_denominator"] is not True or pair["failed_declarations_reassigned"] is not False:
        raise ValueError("fresh declaration-failure handling drift")
    guards = payload["guards"]
    for key, value in guards.items():
        if value is not False:
            raise ValueError(f"fresh execution guard drift: {key}")
    agg = payload["aggregate"]
    if int(agg["required_rows"]) != 48 or int(agg["candidate_generation_denominator"]) != 48 or int(agg["temporal_evaluability_denominator"]) != 48:
        raise ValueError("fresh aggregate denominator drift")
    if agg["all_seven_primary_gates_required"] is not True or agg["primary_gates_changed"] is not False:
        raise ValueError("fresh primary gate drift")
    if agg["heterogeneity_secondary_only"] is not True or agg["heterogeneity_changes_primary_decision"] is not False:
        raise ValueError("fresh heterogeneity decision boundary drift")
    payload["execution_fingerprint"] = stored
    return payload


def verify_frozen_cohort(declarations_path: Path, manifest_path: Path) -> pd.DataFrame:
    execution_contract()
    if _sha256(declarations_path) != EXPECTED_IDENTITY_SHA256:
        raise ValueError("fresh frozen declarations SHA-256 mismatch")
    if _sha256(manifest_path) != EXPECTED_COHORT_MANIFEST_SHA256:
        raise ValueError("fresh frozen cohort manifest SHA-256 mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["protocol_fingerprint"] != EXPECTED_FRESH_PROTOCOL_FINGERPRINT:
        raise ValueError("fresh cohort protocol fingerprint drift")
    if manifest["identity_csv_sha256"] != EXPECTED_IDENTITY_SHA256:
        raise ValueError("fresh cohort identity digest drift")
    if int(manifest["declared_taxa"]) != 48 or int(manifest["unique_species_keys"]) != 48:
        raise ValueError("fresh cohort must contain 48 unique taxa")
    if manifest["recent_outcomes_opened"] is not False or manifest["candidate_generation_run"] is not False:
        raise ValueError("fresh cohort was not frozen before candidate/outcome work")
    if manifest["robust_support_run"] is not False or manifest["random_baseline_run"] is not False:
        raise ValueError("fresh cohort freeze opened scientific evaluation")
    if manifest["replacement_after_freeze_allowed"] is not False or manifest["scientific_method_changed"] is not False:
        raise ValueError("fresh cohort permits replacement or method change")

    frame = pd.read_csv(declarations_path)
    if len(frame) != 48 or frame["speciesKey"].nunique() != 48 or frame["scientific_name"].nunique() != 48:
        raise ValueError("fresh declarations are not exactly 48 unique taxa")
    if "fresh_pair_id" not in frame.columns:
        raise ValueError("fresh declarations lack fresh_pair_id")
    ids = pd.to_numeric(frame["fresh_pair_id"], errors="raise").astype(int)
    if sorted(ids.tolist()) != list(ALL_PAIR_IDS):
        raise ValueError("fresh pair IDs must be exactly 1..48")
    frame = frame.copy()
    frame["integration_pair_id"] = ids
    ru_ids = tuple(sorted(frame.loc[frame["selected_country_code"].astype(str).str.upper().eq("RU"), "integration_pair_id"].astype(int).tolist()))
    if ru_ids != RU_PAIR_IDS:
        raise ValueError(f"fresh frozen RU IDs drifted: {ru_ids}")
    failed = tuple(sorted(frame.loc[frame["declaration_status"].astype(str).ne("declared"), "integration_pair_id"].astype(int).tolist()))
    if failed != FAILED_DECLARATION_PAIR_IDS:
        raise ValueError(f"fresh frozen declaration failures drifted: {failed}")
    if frame["taxon_group"].value_counts().to_dict() != {"plant": 24, "animal": 24}:
        raise ValueError("fresh taxon-group balance drift")
    for group in ("plant", "animal"):
        counts = frame.loc[frame["taxon_group"].eq(group), "record_count_stratum"].astype(int).value_counts().sort_index().to_dict()
        if counts != {0: 6, 1: 6, 2: 6, 3: 6}:
            raise ValueError(f"fresh record-count balance drift for {group}: {counts}")
    return frame


def evaluate_non_ru_pair(declarations_path: Path, manifest_path: Path, pair_id: int, output: Path) -> dict[str, object]:
    declarations = verify_frozen_cohort(declarations_path, manifest_path)
    pair_id = int(pair_id)
    if pair_id not in NON_RU_PAIR_IDS:
        raise ValueError("non-RU runner may not evaluate a frozen RU pair")
    hit = declarations.loc[declarations["integration_pair_id"].astype(int).eq(pair_id)]
    if len(hit) != 1:
        raise ValueError(f"expected one frozen declaration for pair {pair_id}")
    output.mkdir(parents=True, exist_ok=True)
    results, patches = evaluate_one_v2_core(hit.iloc[0])
    results = results.copy()
    results["fresh_protocol_fingerprint"] = EXPECTED_FRESH_PROTOCOL_FINGERPRINT
    results["fresh_execution_fingerprint"] = EXPECTED_FRESH_EXECUTION_FINGERPRINT
    results.to_csv(output / "taxon_country_results.csv", index=False)
    patches.to_csv(output / "integrated_candidate_patches.csv", index=False)
    manifest = {
        "integration_pair_id": pair_id,
        "fresh_protocol_fingerprint": EXPECTED_FRESH_PROTOCOL_FINGERPRINT,
        "fresh_execution_fingerprint": EXPECTED_FRESH_EXECUTION_FINGERPRINT,
        "authoritative_v2_protocol_fingerprint": EXPECTED_PROTOCOL_FINGERPRINT,
        "scientific_method_changed": False,
        "cohort_reselected": False,
        "declaration_reselected": False,
        "candidate_generation_preceded_recent_outcome_fetch": True,
        "ru_execution": False,
    }
    (output / "pair_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--declarations", type=Path, required=True)
    v.add_argument("--cohort-manifest", type=Path, required=True)
    p = sub.add_parser("evaluate-pair")
    p.add_argument("--declarations", type=Path, required=True)
    p.add_argument("--cohort-manifest", type=Path, required=True)
    p.add_argument("--pair-id", type=int, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "verify":
        out = {"execution": execution_contract(), "cohort_rows": len(verify_frozen_cohort(args.declarations, args.cohort_manifest))}
    elif args.command == "evaluate-pair":
        out = evaluate_non_ru_pair(args.declarations, args.cohort_manifest, args.pair_id, args.output)
    else:
        raise AssertionError(args.command)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
