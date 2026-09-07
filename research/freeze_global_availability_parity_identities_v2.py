#!/usr/bin/env python3
"""Stage 1 v2 for issue #197: freeze 48 fresh taxon identities only.

The 12 fixed Japanese cells are used only as a taxon-discovery registry. This
stage pools those identity-only species facets, applies all prior-consumption
exclusions, stratifies within plant and animal by registry record count, and
freezes exactly six identities per group per stratum by a deterministic hash.

It does NOT import or query focal historical-country facets, country geometry,
candidate generation, robust support, random baselines, or 2021-2025 heldout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Callable

import pandas as pd

from benchmark_general_random_taxa_regions import REGION_CELLS, TAXON_GROUPS, taxon_frame
from freeze_global_availability_parity_identities_v1 import combined_exclusions

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "validation" / "acsp_global_availability_parity_confirmation_v2.json"
GROUP_ORDER = ("plant", "animal")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: object) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def protocol() -> dict[str, object]:
    value = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    if value.get("protocol_id") != "acsp_global_availability_parity_confirmation_v2":
        raise ValueError("availability-parity v2 protocol id drift")
    if value.get("status") != "FROZEN_AFTER_V1_IDENTITY_FRAME_INFEASIBILITY_BEFORE_ANY_NEW_FOCAL_HISTORICAL_QUERY_OR_HELDOUT":
        raise ValueError("availability-parity v2 freeze state drift")
    cohort = value["cohort"]
    if cohort["target_taxa"] != 48 or cohort["plant"] != 24 or cohort["animal"] != 24:
        raise ValueError("availability-parity v2 cohort size drift")
    if cohort["required_per_group_per_stratum"] != 6 or cohort["record_count_strata"] != 4:
        raise ValueError("availability-parity v2 stratum contract drift")
    if cohort["selection_uses_focal_historical_country_counts"] is not False:
        raise ValueError("stage1-v2 cannot use focal historical country counts")
    if cohort["selection_uses_country_provider_eligibility"] is not False:
        raise ValueError("stage1-v2 cannot use provider eligibility")
    if cohort["selection_uses_candidate_generation"] is not False:
        raise ValueError("stage1-v2 cannot use candidate generation")
    if cohort["selection_uses_2021_2025"] is not False:
        raise ValueError("stage1-v2 cannot use heldout years")
    return value


def identity_hash(seed: int, group: str, stratum: int, species_key: int) -> str:
    token = f"{int(seed)}|{group}|{int(stratum)}|{int(species_key)}".encode("utf-8")
    return hashlib.sha256(token).hexdigest()


def _normalize_frame(frame: pd.DataFrame, *, region_index: int, group: str) -> pd.DataFrame:
    required = {"speciesKey", "scientific_name", "coordinate_records"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"identity registry frame missing columns: {missing}")
    work = frame.copy()
    work["speciesKey"] = pd.to_numeric(work["speciesKey"], errors="raise").astype(int)
    work["scientific_name"] = work["scientific_name"].astype(str).str.strip()
    work["coordinate_records"] = pd.to_numeric(work["coordinate_records"], errors="raise").astype(int)
    work = work.drop_duplicates(["speciesKey", "scientific_name"]).copy()
    work["region_cell_index"] = int(region_index)
    work["taxon_group"] = str(group)
    return work


def build_identity_registry(
    *,
    frame_provider: Callable[[tuple[float, float, float, float], int, int, int], pd.DataFrame] = taxon_frame,
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    cfg = protocol()
    cohort = cfg["cohort"]
    rows: list[pd.DataFrame] = []
    query_audit: list[dict[str, object]] = []
    if len(REGION_CELLS) != int(cohort["regions"]):
        raise ValueError("fixed discovery-region count drift")

    for region_index, cell in enumerate(REGION_CELLS, start=1):
        _, region_name, west, south, east, north = cell
        bounds = (float(west), float(south), float(east), float(north))
        for group in GROUP_ORDER:
            frame = frame_provider(
                bounds,
                int(TAXON_GROUPS[group]),
                int(cohort["facet_limit_per_region_group"]),
                int(cohort["minimum_japan_region_coordinate_records"]),
            )
            normalized = _normalize_frame(frame, region_index=region_index, group=group)
            rows.append(normalized)
            query_audit.append({
                "region_cell_index": int(region_index),
                "region_name": str(region_name),
                "taxon_group": group,
                "identity_rows": int(len(normalized)),
            })

    stacked = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    if stacked.empty:
        raise RuntimeError("pooled identity registry is empty")

    registry_rows: list[dict[str, object]] = []
    for (group, species_key), part in stacked.groupby(["taxon_group", "speciesKey"], sort=True):
        names = sorted(set(part["scientific_name"].astype(str)))
        if not names:
            continue
        regions = sorted(set(pd.to_numeric(part["region_cell_index"], errors="raise").astype(int)))
        counts = pd.to_numeric(part["coordinate_records"], errors="raise").astype(int)
        registry_rows.append({
            "taxon_group": str(group),
            "kingdomKey": int(TAXON_GROUPS[str(group)]),
            "speciesKey": int(species_key),
            "scientific_name": str(names[0]),
            "registry_max_coordinate_records": int(counts.max()),
            "registry_sum_coordinate_records": int(counts.sum()),
            "registry_source_region_count": int(len(regions)),
            "registry_source_region_indices": ";".join(str(value) for value in regions),
        })
    registry = pd.DataFrame(registry_rows)
    if registry.empty:
        raise RuntimeError("pooled identity registry has no resolved species identities")
    return registry.sort_values(["taxon_group", "speciesKey"], kind="mergesort").reset_index(drop=True), query_audit


def freeze_identities(
    prior_supply_snapshot: Path,
    *,
    frame_provider: Callable[[tuple[float, float, float, float], int, int, int], pd.DataFrame] = taxon_frame,
) -> tuple[pd.DataFrame, dict[str, object]]:
    cfg = protocol()
    cohort = cfg["cohort"]
    excluded_keys, excluded_names, exclusion_audit = combined_exclusions(prior_supply_snapshot)
    prefixes = tuple(str(value) for value in cfg["exclusions"]["explicit_prefixes"])

    registry, query_audit = build_identity_registry(frame_provider=frame_provider)
    before_counts = registry["taxon_group"].value_counts().to_dict()
    registry = registry[
        ~registry["speciesKey"].isin(excluded_keys)
        & ~registry["scientific_name"].isin(excluded_names)
        & ~registry["scientific_name"].str.startswith(prefixes)
    ].copy()
    after_counts = registry["taxon_group"].value_counts().to_dict()

    rows: list[dict[str, object]] = []
    stratum_audit: list[dict[str, object]] = []
    for group in GROUP_ORDER:
        frame = registry[registry["taxon_group"].eq(group)].copy()
        if len(frame) < 24:
            raise RuntimeError(f"fewer than 24 unconsumed pooled identities remain for group={group}: {len(frame)}")
        frame["record_count_stratum"] = pd.qcut(
            frame["registry_max_coordinate_records"].rank(method="first"),
            4,
            labels=False,
        ).astype(int)
        for stratum in range(4):
            pool = frame[frame["record_count_stratum"].eq(stratum)].copy()
            if len(pool) < 6:
                raise RuntimeError(f"fewer than six unconsumed identities for group={group}, stratum={stratum}: {len(pool)}")
            pool["identity_selection_hash"] = [
                identity_hash(int(cohort["selection_seed"]), group, stratum, int(key))
                for key in pool["speciesKey"].astype(int)
            ]
            chosen = pool.sort_values(
                ["identity_selection_hash", "speciesKey", "scientific_name"], kind="mergesort"
            ).head(6)
            stratum_audit.append({
                "taxon_group": group,
                "record_count_stratum": int(stratum),
                "eligible_identity_count": int(len(pool)),
                "selected_identity_count": int(len(chosen)),
            })
            for item in chosen.itertuples(index=False):
                rows.append({
                    "availability_pair_id": len(rows) + 1,
                    "status": "IDENTITY_FROZEN_PRE_HISTORICAL_COUNTRY_QUERY_V2",
                    "taxon_group": group,
                    "kingdomKey": int(item.kingdomKey),
                    "speciesKey": int(item.speciesKey),
                    "scientific_name": str(item.scientific_name),
                    "record_count_stratum": int(item.record_count_stratum),
                    "registry_max_coordinate_records": int(item.registry_max_coordinate_records),
                    "registry_sum_coordinate_records": int(item.registry_sum_coordinate_records),
                    "registry_source_region_count": int(item.registry_source_region_count),
                    "registry_source_region_indices": str(item.registry_source_region_indices),
                    "identity_selection_hash": str(item.identity_selection_hash),
                })

    identities = pd.DataFrame(rows).sort_values(
        ["taxon_group", "record_count_stratum", "identity_selection_hash"], kind="mergesort"
    ).reset_index(drop=True)
    identities["availability_pair_id"] = range(1, len(identities) + 1)
    if len(identities) != 48 or identities["speciesKey"].nunique() != 48 or identities["scientific_name"].nunique() != 48:
        raise RuntimeError("fresh availability v2 cohort is not exactly 48 unique taxa")
    if identities["taxon_group"].value_counts().to_dict() != {"plant": 24, "animal": 24}:
        raise RuntimeError("fresh availability v2 plant/animal balance drift")
    for group in GROUP_ORDER:
        counts = identities.loc[identities["taxon_group"].eq(group), "record_count_stratum"].value_counts().sort_index().to_dict()
        if counts != {0: 6, 1: 6, 2: 6, 3: 6}:
            raise RuntimeError(f"fresh availability v2 stratum balance drift for {group}: {counts}")
    if set(identities["speciesKey"].astype(int)) & excluded_keys:
        raise RuntimeError("fresh availability v2 identities overlap excluded species keys")
    if set(identities["scientific_name"].astype(str)) & excluded_names:
        raise RuntimeError("fresh availability v2 identities overlap excluded names")

    identity_records = identities[[
        "availability_pair_id", "taxon_group", "record_count_stratum", "speciesKey",
        "scientific_name", "identity_selection_hash",
    ]].to_dict(orient="records")
    audit = {
        "schema_version": "global-availability-parity-identity-freeze-v2",
        "status": "IDENTITY_FREEZE_COMPLETE_PRE_HISTORICAL_COUNTRY_QUERY_V2",
        "protocol_sha256": _sha256_file(PROTOCOL_PATH),
        "identity_count": 48,
        "plant_count": 24,
        "animal_count": 24,
        "identity_canonical_sha256": _canonical_sha256(identity_records),
        "registry_group_counts_before_exclusion": {str(k): int(v) for k, v in before_counts.items()},
        "registry_group_counts_after_exclusion": {str(k): int(v) for k, v in after_counts.items()},
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
        "query_audit": query_audit,
        "stratum_audit": stratum_audit,
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
    print(json.dumps({key: value for key, value in audit.items() if key not in {"query_audit", "stratum_audit"}}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
