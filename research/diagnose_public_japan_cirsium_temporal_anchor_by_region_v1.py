#!/usr/bin/env python3
"""Post-v1 public diagnostic: temporal occurrence-anchor recovery inside fixed Japan regions.

This diagnostic keeps the v1 species, GBIF record filter, temporal split, cluster rule,
and 2/5 km recovery radii unchanged. The only change is to evaluate each species
inside the same 12 fixed Japanese rectangles used by the validated regional ACSP
benchmark. It diagnoses whether the national v1 failure was dominated by later
records appearing in geographically detached components.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from benchmark_public_japan_cirsium_temporal_anchor_v1 import evaluate_species, fetch_gbif_species

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "validation" / "public_japan_cirsium_temporal_anchor_region_diagnostic_v1.json"
DEFAULT_COHORT = ROOT / "validation" / "cirsium_aza3_prospective_validation_cohort_v1.csv"
DEFAULT_PARENT = ROOT / "validation" / "public_japan_cirsium_temporal_anchor_benchmark_result_v1.json"


def inside_region(records: pd.DataFrame, region: dict[str, object]) -> pd.DataFrame:
    if records.empty:
        return records.copy()
    west = float(region["west"])
    south = float(region["south"])
    east = float(region["east"])
    north = float(region["north"])
    mask = (
        records["longitude"].between(west, east, inclusive="both")
        & records["latitude"].between(south, north, inclusive="both")
    )
    return records.loc[mask].copy().reset_index(drop=True)


def evaluate_species_regions(species_name: str, records: pd.DataFrame, regions: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for region in regions:
        subset = inside_region(records, region)
        result = evaluate_species(species_name, subset, cluster_radius_km=0.5)
        result["region_name"] = str(region["region_name"])
        rows.append(result)
    return rows


def summarize_region_units(rows: list[dict[str, object]], parent: dict[str, object]) -> dict[str, object]:
    any_records = [row for row in rows if int(row["eligible_records"]) > 0]
    evaluable = [row for row in rows if bool(row["temporally_evaluable"])]
    with_novel = [row for row in evaluable if int(row["novel_recent_clusters"]) > 0]
    novel_total = sum(int(row["novel_recent_clusters"]) for row in with_novel)
    within2 = sum(int(row["novel_recent_within_2km"]) for row in with_novel)
    within5 = sum(int(row["novel_recent_within_5km"]) for row in with_novel)
    unit2 = [float(row["fraction_novel_recent_within_2km"]) for row in with_novel if row["fraction_novel_recent_within_2km"] is not None]
    unit5 = [float(row["fraction_novel_recent_within_5km"]) for row in with_novel if row["fraction_novel_recent_within_5km"] is not None]
    regional2 = float(within2 / novel_total) if novel_total else None
    regional5 = float(within5 / novel_total) if novel_total else None
    parent2 = parent.get("pooled_fraction_novel_recent_within_2km")
    parent5 = parent.get("pooled_fraction_novel_recent_within_5km")
    return {
        "schema_version": "public-japan-cirsium-temporal-anchor-region-diagnostic-result-v1",
        "status": "POST_V1_DESCRIPTIVE_DIAGNOSTIC_COMPLETE",
        "field_outcomes_used": False,
        "private_localities_used": False,
        "parent_result_retuned": False,
        "validated_product_changed": False,
        "declared_species_region_units": int(len(rows)),
        "units_with_any_eligible_records": int(len(any_records)),
        "temporally_evaluable_units": int(len(evaluable)),
        "units_with_novel_recent_clusters": int(len(with_novel)),
        "sentinel_units": int(sum(bool(row["sentinel_no_historical_anchor"]) for row in rows)),
        "novel_recent_cluster_count": int(novel_total),
        "pooled_fraction_novel_recent_within_2km": regional2,
        "pooled_fraction_novel_recent_within_5km": regional5,
        "unit_level_fraction_within_2km_median": float(np.median(unit2)) if unit2 else None,
        "unit_level_fraction_within_5km_median": float(np.median(unit5)) if unit5 else None,
        "parent_national_fraction_within_2km": parent2,
        "parent_national_fraction_within_5km": parent5,
        "regional_minus_national_2km": float(regional2 - float(parent2)) if regional2 is not None and parent2 is not None else None,
        "regional_minus_national_5km": float(regional5 - float(parent5)) if regional5 is not None and parent5 is not None else None,
        "interpretation_boundary": "Changing only the outer fixed regional frame diagnoses geographic-component mixing. It does not rescue or replace the parent national v1 result and does not validate structural habitat ranking or occupancy."
    }


def run_diagnostic(contract_path: Path = DEFAULT_CONTRACT, cohort_path: Path = DEFAULT_COHORT, parent_path: Path = DEFAULT_PARENT) -> tuple[pd.DataFrame, dict[str, object], pd.DataFrame]:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract["status"] != "POST_V1_DESCRIPTIVE_DIAGNOSTIC_FROZEN_BEFORE_EXECUTION":
        raise ValueError("regional diagnostic contract is not frozen")
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    cohort = pd.read_csv(cohort_path)
    species = list(dict.fromkeys(cohort["species_binomial"].astype(str).tolist()))
    if len(species) != int(contract["species_count"]):
        raise ValueError("frozen species count mismatch")
    regions = list(contract["fixed_regions"])
    rows: list[dict[str, object]] = []
    audits: list[dict[str, object]] = []
    for species_name in species:
        records, audit = fetch_gbif_species(species_name)
        audits.append(audit)
        rows.extend(evaluate_species_regions(species_name, records, regions))
    table = pd.DataFrame(rows)
    summary = summarize_region_units(rows, parent)
    return table, summary, pd.DataFrame(audits)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--cohort", type=Path, default=DEFAULT_COHORT)
    parser.add_argument("--parent", type=Path, default=DEFAULT_PARENT)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    table, summary, audit = run_diagnostic(args.contract, args.cohort, args.parent)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.out_dir / "species_region_temporal_anchor_metrics.csv", index=False)
    audit.to_csv(args.out_dir / "gbif_fetch_audit.csv", index=False)
    (args.out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
