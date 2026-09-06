#!/usr/bin/env python3
"""Stage 1 for issue #197: freeze 48 fresh taxon identities only.

Allowed inputs:
- fixed Japanese discovery-region species facets/metadata;
- already-consumed identity files;
- the byte-pinned issue-169 candidate snapshot used only as an identity exclusion.

This script does NOT import or query focal historical-country facets, country
geometry, candidate generation, robust support, random baselines, or 2021-2025
heldout data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Callable

import pandas as pd

from benchmark_general_random_taxa_regions import REGION_CELLS, TAXON_GROUPS, taxon_frame
from predeclare_country_framed_fresh_heterogeneity_confirmation import exclusion_sets as base_exclusion_sets
from predeclare_country_framed_fresh_heterogeneity_confirmation import protocol as base_protocol
from predeclare_country_framed_fresh_heterogeneity_confirmation import target_strata

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "validation" / "acsp_global_availability_parity_confirmation_v1.json"
FRESH48_PATH = ROOT / "validation" / "acsp_country_framed_fresh_heterogeneity_confirmation_identities_v1.csv"
EXPECTED_FRESH48_SHA256 = "4dfe23ff32c2e3c3fd601afefabf733feab09f2c95db1def246ed793cd347cb9"
EXPECTED_PRIOR_SUPPLY_SHA256 = "a3ef9ed1ad1dc49f63702511297c56dc0c68f02a7cc0c3805906fcd4291dbe41"
EXPECTED_PRIOR_SUPPLY_UNIQUE = 3161
GROUP_ORDER = ("plant", "animal")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def protocol() -> dict[str, object]:
    value = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    if value.get("protocol_id") != "acsp_global_availability_parity_confirmation_v1":
        raise ValueError("availability-parity protocol id drift")
    if value.get("status") != "FROZEN_BEFORE_FRESH_IDENTITY_SELECTION_OR_FOCAL_HISTORICAL_QUERY":
        raise ValueError("availability-parity protocol freeze state drift")
    if value["cohort"]["target_taxa"] != 48 or value["cohort"]["plant"] != 24 or value["cohort"]["animal"] != 24:
        raise ValueError("availability-parity cohort size drift")
    if value["cohort"]["selection_uses_focal_historical_country_counts"] is not False:
        raise ValueError("stage1 cannot use focal historical country counts")
    if value["cohort"]["selection_uses_2021_2025"] is not False:
        raise ValueError("stage1 cannot use heldout years")
    return value


def identity_hash(seed: int, region: int, group: str, stratum: int, species_key: int) -> str:
    return hashlib.sha256(f"{int(seed)}|{int(region)}|{group}|{int(stratum)}|{int(species_key)}".encode("utf-8")).hexdigest()


def _read_identity_columns(frame: pd.DataFrame) -> tuple[set[int], set[str]]:
    lower = {str(column).lower(): str(column) for column in frame.columns}
    key_col = lower.get("specieskey") or lower.get("species_key")
    name_col = lower.get("scientific_name") or lower.get("scientificname")
    keys: set[int] = set()
    names: set[str] = set()
    if key_col:
        keys.update(pd.to_numeric(frame[key_col], errors="coerce").dropna().astype(int).tolist())
    if name_col:
        names.update(value for value in frame[name_col].dropna().astype(str).str.strip() if value)
    return keys, names


def combined_exclusions(prior_supply_snapshot: Path) -> tuple[set[int], set[str], dict[str, object]]:
    cfg = protocol()
    base = base_protocol()
    if base["protocol_fingerprint"] != cfg["exclusions"]["base_consumed_protocol_fingerprint"]:
        raise ValueError("base consumed protocol fingerprint drift")
    keys, names = base_exclusion_sets(base["exclusions"])

    if _sha256_file(FRESH48_PATH) != EXPECTED_FRESH48_SHA256:
        raise ValueError("terminal fresh-48 identity file hash drift")
    fresh = pd.read_csv(FRESH48_PATH)
    fresh_keys, fresh_names = _read_identity_columns(fresh)
    if len(fresh_keys) != 48 or len(fresh_names) != 48:
        raise ValueError("terminal fresh-48 identity exclusion must contain 48 unique taxa")
    keys.update(fresh_keys)
    names.update(fresh_names)

    snapshot = Path(prior_supply_snapshot)
    if _sha256_file(snapshot) != EXPECTED_PRIOR_SUPPLY_SHA256:
        raise ValueError("prior provider-supply candidate snapshot hash drift")
    supply = pd.read_csv(snapshot)
    supply_keys, supply_names = _read_identity_columns(supply)
    if len(supply_keys) != EXPECTED_PRIOR_SUPPLY_UNIQUE or len(supply_names) != EXPECTED_PRIOR_SUPPLY_UNIQUE:
        raise ValueError("prior provider-supply identity count drift")
    keys.update(supply_keys)
    names.update(supply_names)

    audit = {
        "base_consumed_key_count": int(len(base_exclusion_sets(base["exclusions"])[0])),
        "terminal_fresh48_excluded": 48,
        "prior_provider_supply_excluded": EXPECTED_PRIOR_SUPPLY_UNIQUE,
        "combined_excluded_species_keys": int(len(keys)),
        "combined_excluded_scientific_names": int(len(names)),
        "prior_supply_snapshot_sha256": EXPECTED_PRIOR_SUPPLY_SHA256,
    }
    return keys, names, audit


def freeze_identities(
    prior_supply_snapshot: Path,
    *,
    frame_provider: Callable[[tuple[float, float, float, float], int, int, int], pd.DataFrame] = taxon_frame,
) -> tuple[pd.DataFrame, dict[str, object]]:
    cfg = protocol()
    cohort = cfg["cohort"]
    excluded_keys, excluded_names, exclusion_audit = combined_exclusions(prior_supply_snapshot)
    prefixes = tuple(str(value) for value in cfg["exclusions"]["explicit_prefixes"])
    used_keys: set[int] = set()
    used_names: set[str] = set()
    rows: list[dict[str, object]] = []
    pool_audit: list[dict[str, object]] = []

    if len(REGION_CELLS) != int(cohort["regions"]):
        raise ValueError("fixed discovery-region count drift")

    for region_index, cell in enumerate(REGION_CELLS, start=1):
        geographic_stratum, region_name, west, south, east, north = cell
        bounds = (float(west), float(south), float(east), float(north))
        for group in GROUP_ORDER:
            frame = frame_provider(
                bounds,
                int(TAXON_GROUPS[group]),
                int(cohort["facet_limit"]),
                int(cohort["minimum_japan_region_coordinate_records"]),
            ).copy()
            required = {"speciesKey", "scientific_name", "coordinate_records"}
            missing = sorted(required.difference(frame.columns))
            if missing:
                raise ValueError(f"fresh identity frame missing columns: {missing}")
            frame["speciesKey"] = pd.to_numeric(frame["speciesKey"], errors="raise").astype(int)
            frame["scientific_name"] = frame["scientific_name"].astype(str).str.strip()
            frame["coordinate_records"] = pd.to_numeric(frame["coordinate_records"], errors="raise").astype(int)
            frame = frame.drop_duplicates(["speciesKey", "scientific_name"]).copy()
            before = int(len(frame))
            frame = frame[
                ~frame["speciesKey"].isin(excluded_keys)
                & ~frame["scientific_name"].isin(excluded_names)
                & ~frame["scientific_name"].str.startswith(prefixes)
            ].copy()
            after = int(len(frame))
            if len(frame) < 4:
                raise RuntimeError(f"fewer than four unconsumed taxa remain for region={region_index}, group={group}")
            frame["record_count_stratum"] = pd.qcut(
                frame["coordinate_records"].rank(method="first"), 4, labels=False
            ).astype(int)
            pool_audit.append({
                "region_cell_index": int(region_index),
                "taxon_group": group,
                "candidate_rows_before_exclusion": before,
                "candidate_rows_after_exclusion": after,
                "candidate_rows_removed": before - after,
            })

            for stratum in target_strata(region_index):
                pool = frame[
                    frame["record_count_stratum"].eq(int(stratum))
                    & ~frame["speciesKey"].isin(used_keys)
                    & ~frame["scientific_name"].isin(used_names)
                ].copy()
                if pool.empty:
                    raise RuntimeError(f"no unconsumed taxon for region={region_index}, group={group}, stratum={stratum}")
                pool["identity_selection_hash"] = [
                    identity_hash(int(cohort["selection_seed"]), region_index, group, int(stratum), int(key))
                    for key in pool["speciesKey"].astype(int)
                ]
                chosen = pool.sort_values(
                    ["identity_selection_hash", "speciesKey", "scientific_name"], kind="mergesort"
                ).iloc[0]
                key = int(chosen["speciesKey"])
                name = str(chosen["scientific_name"])
                used_keys.add(key)
                used_names.add(name)
                rows.append({
                    "availability_pair_id": len(rows) + 1,
                    "status": "IDENTITY_FROZEN_PRE_HISTORICAL_COUNTRY_QUERY",
                    "taxon_group": group,
                    "kingdomKey": int(TAXON_GROUPS[group]),
                    "geographic_stratum": str(geographic_stratum),
                    "region_name": str(region_name),
                    "region_cell_index": int(region_index),
                    "west": bounds[0],
                    "south": bounds[1],
                    "east": bounds[2],
                    "north": bounds[3],
                    "speciesKey": key,
                    "scientific_name": name,
                    "coordinate_records": int(chosen["coordinate_records"]),
                    "record_count_stratum": int(stratum),
                    "identity_selection_hash": str(chosen["identity_selection_hash"]),
                })

    identities = pd.DataFrame(rows)
    if len(identities) != 48 or identities["speciesKey"].nunique() != 48 or identities["scientific_name"].nunique() != 48:
        raise RuntimeError("fresh availability cohort is not exactly 48 unique taxa")
    if identities["taxon_group"].value_counts().to_dict() != {"plant": 24, "animal": 24}:
        raise RuntimeError("fresh availability cohort plant/animal balance drift")
    for group in GROUP_ORDER:
        counts = identities.loc[identities["taxon_group"].eq(group), "record_count_stratum"].astype(int).value_counts().sort_index().to_dict()
        if counts != {0: 6, 1: 6, 2: 6, 3: 6}:
            raise RuntimeError(f"fresh availability stratum balance drift for {group}: {counts}")
    if set(identities["speciesKey"].astype(int)) & excluded_keys:
        raise RuntimeError("fresh availability identities overlap excluded species keys")
    if set(identities["scientific_name"].astype(str)) & excluded_names:
        raise RuntimeError("fresh availability identities overlap excluded names")

    identity_records = identities[["availability_pair_id", "taxon_group", "region_cell_index", "record_count_stratum", "speciesKey", "scientific_name", "identity_selection_hash"]].to_dict(orient="records")
    audit = {
        "schema_version": "global-availability-parity-identity-freeze-v1",
        "status": "IDENTITY_FREEZE_COMPLETE_PRE_HISTORICAL_COUNTRY_QUERY",
        "protocol_sha256": _sha256_file(PROTOCOL_PATH),
        "identity_count": 48,
        "plant_count": 24,
        "animal_count": 24,
        "identity_canonical_sha256": _canonical_sha256(identity_records),
        "focal_historical_country_facets_opened": False,
        "country_geometry_opened": False,
        "candidate_generation_run": False,
        "heldout_2021_2025_opened": False,
        "robust_support_run": False,
        "random_baseline_run": False,
        "recall_or_lift_read": False,
        "outcome_driven_tuning": False,
        "validated_japan_core_changed": False,
        "exclusions": exclusion_audit,
        "pool_audit": pool_audit,
    }
    return identities, audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior-supply-snapshot", type=Path, required=True)
    parser.add_argument("--identities-output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    args = parser.parse_args()
    identities, audit = freeze_identities(args.prior_supply_snapshot)
    args.identities_output.parent.mkdir(parents=True, exist_ok=True)
    identities.to_csv(args.identities_output, index=False)
    args.audit_output.parent.mkdir(parents=True, exist_ok=True)
    args.audit_output.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in audit.items() if key != "pool_audit"}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
