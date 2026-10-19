#!/usr/bin/env python3
"""Freeze 48 fresh Japanese plant identity candidates for issue #202.

Stage 1 is identity/supply only. It must not query focal 2000-2020 occurrence
records or any 2021-2025 outcome. The 12 fixed Japanese regions are pooled only
as a species identity registry.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Callable

import pandas as pd

from benchmark_general_random_taxa_regions import REGION_CELLS, TAXON_GROUPS
from freeze_global_availability_parity_identities_v1 import combined_exclusions
from freeze_global_availability_parity_identities_v2 import raw_taxon_key_frame, fetch_species_metadata

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "validation" / "japan_plant_broad_frame_confirmation_v3.json"
GLOBAL_V2_IDENTITIES = ROOT / "validation" / "acsp_global_availability_parity_identities_v2.csv"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def protocol() -> dict[str, object]:
    cfg = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    if cfg.get("protocol_id") != "japan_plant_broad_frame_confirmation_v3":
        raise ValueError("Japan plant broad-frame v3 protocol id drift")
    if cfg.get("status") != "FROZEN_BEFORE_IDENTITY_CANDIDATE_SELECTION_OR_FOCAL_HISTORICAL_QUERY":
        raise ValueError("Japan plant broad-frame v3 stage1 boundary drift")
    stage = cfg["stage1_identity_candidates"]
    if int(stage["target_candidates"]) != 48 or stage["taxon_group"] != "plant":
        raise ValueError("stage1 cohort contract drift")
    if stage["selection_uses_focal_2000_2020_occurrences"] is not False or stage["selection_uses_2021_2025"] is not False:
        raise ValueError("stage1 information boundary drift")
    return cfg


def _identity_hash(seed: int, species_key: int) -> str:
    return hashlib.sha256(f"{int(seed)}|{int(species_key)}".encode()).hexdigest()


def _read_global_v2_exclusions() -> tuple[set[int], set[str]]:
    frame = pd.read_csv(GLOBAL_V2_IDENTITIES)
    if len(frame) != 48 or frame["speciesKey"].nunique() != 48:
        raise ValueError("global availability v2 identity exclusion drift")
    keys = set(pd.to_numeric(frame["speciesKey"], errors="raise").astype(int))
    names = set(frame["scientific_name"].astype(str).str.strip())
    return keys, names


def build_plant_registry(
    *,
    frame_provider: Callable[[tuple[float, float, float, float], int, int, int], pd.DataFrame] = raw_taxon_key_frame,
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    cfg = protocol()["stage1_identity_candidates"]
    rows: list[pd.DataFrame] = []
    audit: list[dict[str, object]] = []
    if len(REGION_CELLS) != 12:
        raise ValueError("fixed Japanese region registry drift")
    for index, cell in enumerate(REGION_CELLS, start=1):
        _, region_name, west, south, east, north = cell
        frame = frame_provider(
            (float(west), float(south), float(east), float(north)),
            int(TAXON_GROUPS["plant"]),
            int(cfg["facet_limit_per_region"]),
            int(cfg["minimum_region_coordinate_records"]),
        ).copy()
        required = {"speciesKey", "coordinate_records"}
        if not required.issubset(frame.columns):
            raise ValueError(f"plant identity facet missing columns: {sorted(required.difference(frame.columns))}")
        frame["speciesKey"] = pd.to_numeric(frame["speciesKey"], errors="raise").astype(int)
        frame["coordinate_records"] = pd.to_numeric(frame["coordinate_records"], errors="raise").astype(int)
        frame = frame.drop_duplicates("speciesKey")
        frame["region_index"] = int(index)
        rows.append(frame[["speciesKey", "coordinate_records", "region_index"]])
        audit.append({"region_index": index, "region_name": str(region_name), "facet_rows": int(len(frame))})
    stacked = pd.concat(rows, ignore_index=True)
    records: list[dict[str, object]] = []
    for key, part in stacked.groupby("speciesKey", sort=True):
        counts = part["coordinate_records"].astype(int)
        regions = sorted(set(part["region_index"].astype(int)))
        records.append({
            "speciesKey": int(key),
            "registry_max_coordinate_records": int(counts.max()),
            "registry_sum_coordinate_records": int(counts.sum()),
            "registry_source_region_count": len(regions),
            "registry_source_region_indices": ";".join(map(str, regions)),
        })
    return pd.DataFrame(records).sort_values("speciesKey").reset_index(drop=True), audit


def freeze_identity_candidates(
    prior_supply_snapshot: Path,
    *,
    frame_provider: Callable[[tuple[float, float, float, float], int, int, int], pd.DataFrame] = raw_taxon_key_frame,
    metadata_provider: Callable[[int], dict[str, object]] = fetch_species_metadata,
    exclusion_provider: Callable[[Path], tuple[set[int], set[str], dict[str, object]]] = combined_exclusions,
) -> tuple[pd.DataFrame, dict[str, object]]:
    cfg = protocol()
    stage = cfg["stage1_identity_candidates"]
    excluded_keys, excluded_names, exclusion_audit = exclusion_provider(Path(prior_supply_snapshot))
    global_keys, global_names = _read_global_v2_exclusions()
    excluded_keys = set(excluded_keys) | global_keys
    excluded_names = set(excluded_names) | global_names
    prefixes = tuple(str(x) for x in cfg["exclusions"]["excluded_name_prefixes"])

    registry, query_audit = build_plant_registry(frame_provider=frame_provider)
    before = len(registry)
    registry = registry.loc[~registry["speciesKey"].isin(excluded_keys)].copy()
    after = len(registry)
    if after < 96:
        raise RuntimeError(f"fewer than 96 fresh plant identities remain after key exclusion: {after}")

    ordered_supply = registry.sort_values(
        ["registry_max_coordinate_records", "speciesKey"], kind="mergesort"
    ).reset_index(drop=True)
    upper = ordered_supply.iloc[len(ordered_supply) // 2 :].copy()
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
        if len(selected) == int(stage["target_candidates"]):
            break
    candidates = pd.DataFrame(selected)
    if len(candidates) != 48 or candidates["speciesKey"].nunique() != 48 or candidates["scientific_name"].nunique() != 48:
        raise RuntimeError(f"could not freeze 48 fresh plant identity candidates: {len(candidates)}")
    if set(candidates["speciesKey"].astype(int)) & excluded_keys:
        raise RuntimeError("stage1 candidates overlap excluded species keys")
    if any(name.startswith(prefixes) for name in candidates["scientific_name"].astype(str)):
        raise RuntimeError("stage1 candidates overlap excluded genus prefixes")

    canonical = candidates[["candidate_id", "speciesKey", "scientific_name", "identity_selection_hash"]].to_dict(orient="records")
    audit = {
        "schema_version": "japan-plant-broad-frame-identity-candidates-v3",
        "status": "IDENTITY_CANDIDATES_FROZEN_PRE_FOCAL_HISTORICAL_QUERY",
        "candidate_count": 48,
        "candidate_identity_sha256": _canonical_sha(canonical),
        "protocol_sha256": _sha256_file(PROTOCOL_PATH),
        "registry_count_before_exclusion": int(before),
        "registry_count_after_key_exclusion": int(after),
        "upper_half_registry_count": int(len(upper)),
        "metadata_attempt_count": int(metadata_attempts),
        "query_audit": query_audit,
        "exclusion_audit": exclusion_audit,
        "additional_global_v2_keys_excluded": 48,
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
