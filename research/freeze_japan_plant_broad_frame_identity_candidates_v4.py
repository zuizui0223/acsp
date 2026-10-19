#!/usr/bin/env python3
"""Freeze 96 fresh Japanese plant identity candidates for issue #203.

This is stage 1 only. It reuses the already frozen Japanese plant registry/supply
mechanics from v3, but excludes every identity consumed by issue #202 before the
new deterministic v4 hash ordering is applied. It must not query focal
2000-2020 occurrence rows or any 2021-2025 outcome.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Callable

import pandas as pd

from freeze_global_availability_parity_identities_v1 import combined_exclusions
from freeze_global_availability_parity_identities_v2 import fetch_species_metadata
from freeze_japan_plant_broad_frame_identity_candidates_v3 import (
    _read_global_v2_exclusions,
    build_plant_registry as build_plant_registry_v3,
)

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "validation" / "japan_plant_broad_frame_confirmation_v4.json"
ISSUE_202_IDENTITIES = ROOT / "validation" / "japan_plant_broad_frame_identity_candidates_v3.csv"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def protocol() -> dict[str, object]:
    cfg = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    if cfg.get("protocol_id") != "japan_plant_broad_frame_confirmation_v4":
        raise ValueError("Japan plant broad-frame v4 protocol id drift")
    if cfg.get("status") != "FROZEN_BEFORE_IDENTITY_CANDIDATE_SELECTION_OR_FOCAL_HISTORICAL_QUERY":
        raise ValueError("Japan plant broad-frame v4 stage1 boundary drift")
    stage = cfg["stage1_identity_candidates"]
    if int(stage["target_candidates"]) != 96 or stage["taxon_group"] != "plant":
        raise ValueError("stage1 cohort contract drift")
    if int(stage["facet_limit_per_region"]) != 1000 or int(stage["minimum_region_coordinate_records"]) != 20:
        raise ValueError("v4 registry mechanics must remain identical to v3")
    if stage["selection_uses_focal_2000_2020_occurrences"] is not False:
        raise ValueError("stage1 cannot use focal historical rows")
    if stage["selection_uses_2021_2025"] is not False:
        raise ValueError("stage1 cannot use heldout rows")
    return cfg


def _identity_hash(seed: int, species_key: int) -> str:
    return hashlib.sha256(f"{int(seed)}|{int(species_key)}".encode()).hexdigest()


def _read_issue_202_exclusions() -> tuple[set[int], set[str], dict[str, object]]:
    cfg = protocol()
    path = ISSUE_202_IDENTITIES
    expected = str(cfg["exclusions"]["exclude_issue_202_identity_candidates_sha256"])
    got = _sha256_file(path)
    if got != expected:
        raise ValueError(f"issue #202 identity file digest drift: {got} != {expected}")
    frame = pd.read_csv(path)
    expected_n = int(cfg["exclusions"]["issue_202_consumed_identity_count"])
    if len(frame) != expected_n or frame["speciesKey"].nunique() != expected_n or frame["scientific_name"].nunique() != expected_n:
        raise ValueError("issue #202 consumed identity count drift")
    keys = set(pd.to_numeric(frame["speciesKey"], errors="raise").astype(int))
    names = set(frame["scientific_name"].astype(str).str.strip())
    return keys, names, {"path": str(path.relative_to(ROOT)), "sha256": got, "count": expected_n}


def freeze_identity_candidates(
    prior_supply_snapshot: Path,
    *,
    frame_provider=None,
    metadata_provider: Callable[[int], dict[str, object]] = fetch_species_metadata,
    exclusion_provider: Callable[[Path], tuple[set[int], set[str], dict[str, object]]] = combined_exclusions,
    global_exclusion_provider: Callable[[], tuple[set[int], set[str]]] = _read_global_v2_exclusions,
    issue_202_exclusion_provider: Callable[[], tuple[set[int], set[str], dict[str, object]]] = _read_issue_202_exclusions,
) -> tuple[pd.DataFrame, dict[str, object]]:
    cfg = protocol()
    stage = cfg["stage1_identity_candidates"]
    target = int(stage["target_candidates"])

    excluded_keys, excluded_names, exclusion_audit = exclusion_provider(Path(prior_supply_snapshot))
    global_keys, global_names = global_exclusion_provider()
    issue_202_keys, issue_202_names, issue_202_audit = issue_202_exclusion_provider()
    excluded_keys = set(excluded_keys) | set(global_keys) | set(issue_202_keys)
    excluded_names = set(excluded_names) | set(global_names) | set(issue_202_names)
    prefixes = tuple(str(x) for x in cfg["exclusions"]["excluded_name_prefixes"])

    registry_kwargs = {} if frame_provider is None else {"frame_provider": frame_provider}
    registry, query_audit = build_plant_registry_v3(**registry_kwargs)
    before = len(registry)
    registry = registry.loc[~registry["speciesKey"].isin(excluded_keys)].copy()
    after = len(registry)

    ordered_supply = registry.sort_values(
        ["registry_max_coordinate_records", "speciesKey"], kind="mergesort"
    ).reset_index(drop=True)
    upper = ordered_supply.iloc[len(ordered_supply) // 2 :].copy()
    if len(upper) < target:
        raise RuntimeError(f"upper-half fresh plant registry cannot supply {target} identities: {len(upper)}")
    upper["identity_selection_hash"] = [
        _identity_hash(int(stage["selection_seed"]), key) for key in upper["speciesKey"].astype(int)
    ]
    upper = upper.sort_values(["identity_selection_hash", "speciesKey"], kind="mergesort")

    selected: list[dict[str, object]] = []
    metadata_attempts = 0
    seen_names: set[str] = set()
    for row in upper.itertuples(index=False):
        key = int(row.speciesKey)
        metadata_attempts += 1
        meta = metadata_provider(key)
        if str(meta.get("rank") or "").upper() != "SPECIES":
            continue
        name = str(meta.get("scientificName") or "").strip()
        if not name or name in excluded_names or name.startswith(prefixes) or name in seen_names:
            continue
        seen_names.add(name)
        selected.append({
            "candidate_id": len(selected) + 1,
            "speciesKey": key,
            "scientific_name": name,
            "registry_max_coordinate_records": int(row.registry_max_coordinate_records),
            "registry_sum_coordinate_records": int(row.registry_sum_coordinate_records),
            "registry_source_region_count": int(row.registry_source_region_count),
            "registry_source_region_indices": str(row.registry_source_region_indices),
            "identity_selection_hash": str(row.identity_selection_hash),
        })
        if len(selected) == target:
            break

    candidates = pd.DataFrame(selected)
    if len(candidates) != target or candidates["speciesKey"].nunique() != target or candidates["scientific_name"].nunique() != target:
        raise RuntimeError(f"could not freeze {target} fresh plant identity candidates: {len(candidates)}")
    if set(candidates["speciesKey"].astype(int)) & excluded_keys:
        raise RuntimeError("v4 candidates overlap a consumed speciesKey")
    if set(candidates["scientific_name"].astype(str)) & excluded_names:
        raise RuntimeError("v4 candidates overlap a consumed scientific name")
    if any(name.startswith(prefixes) for name in candidates["scientific_name"].astype(str)):
        raise RuntimeError("v4 candidates overlap excluded genus prefixes")

    canonical = candidates[["candidate_id", "speciesKey", "scientific_name", "identity_selection_hash"]].to_dict(orient="records")
    audit = {
        "schema_version": "japan-plant-broad-frame-identity-candidates-v4",
        "status": "IDENTITY_CANDIDATES_FROZEN_PRE_FOCAL_HISTORICAL_QUERY",
        "candidate_count": target,
        "candidate_identity_sha256": _canonical_sha(canonical),
        "protocol_sha256": _sha256_file(PROTOCOL_PATH),
        "registry_count_before_exclusion": int(before),
        "registry_count_after_key_exclusion": int(after),
        "upper_half_registry_count": int(len(upper)),
        "metadata_attempt_count": int(metadata_attempts),
        "query_audit": query_audit,
        "exclusion_audit": exclusion_audit,
        "issue_202_exclusion_audit": issue_202_audit,
        "additional_global_v2_keys_excluded": int(len(global_keys)),
        "additional_issue_202_keys_excluded": int(len(issue_202_keys)),
        "focal_2000_2020_occurrences_opened": False,
        "heldout_2021_2025_opened": False,
        "candidate_frames_built": False,
        "selector_evaluated": False,
        "validated_japan_product_changed": False,
        "automatic_global_adapter_changed": False,
    }
    return candidates, audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior-supply-snapshot", type=Path, required=True)
    parser.add_argument("--candidates-output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    args = parser.parse_args()
    candidates, audit = freeze_identity_candidates(args.prior_supply_snapshot)
    args.candidates_output.parent.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(args.candidates_output, index=False)
    args.audit_output.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
