#!/usr/bin/env python3
"""Develop one pre-outcome temporal-persistence gate on the consumed #203 cohort.

The only candidate gate is whether the frozen historical selected region has at
least one strict 0.5-km population cluster during 2016-2020. #203 outcome labels
are used only to measure development enrichment; no candidate frame is rescored.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

from acsp.discovery import complete_link_clusters
from acsp.discovery.providers import fetch_gbif_occurrence_evidence
from acsp.taxon_patches import VALIDATED_JAPAN_REGIONS
from prepare_cirsium_disjoint_broad_frame_replication_v1 import _inside_region, _strict_exact

COHORT_PATH = ROOT / "validation" / "japan_plant_v4_temporal_persistence_development_cohort.csv"
RECENT_HISTORICAL_START = 2016
RECENT_HISTORICAL_END = 2020


def region_registry() -> list[dict[str, Any]]:
    return [
        {
            "region_id": str(region_id),
            "order": int(index),
            "west": float(west),
            "south": float(south),
            "east": float(east),
            "north": float(north),
        }
        for index, (region_id, _name, _stratum, west, south, east, north) in enumerate(VALIDATED_JAPAN_REGIONS)
    ]


def load_cohort(path: Path = COHORT_PATH) -> pd.DataFrame:
    cohort = pd.read_csv(path)
    required = {
        "speciesKey",
        "scientific_name",
        "frozen_historical_selected_region",
        "frozen_historical_population_count",
        "terminal_temporally_evaluable",
    }
    if not required.issubset(cohort.columns):
        raise ValueError(f"cohort missing columns: {sorted(required.difference(cohort.columns))}")
    if len(cohort) != 24 or cohort["speciesKey"].nunique() != 24:
        raise ValueError("temporal-persistence development cohort must contain exactly 24 identities")
    cohort["speciesKey"] = pd.to_numeric(cohort["speciesKey"], errors="raise").astype(int)
    cohort["frozen_historical_population_count"] = pd.to_numeric(
        cohort["frozen_historical_population_count"], errors="raise"
    ).astype(int)
    cohort["terminal_temporally_evaluable"] = (
        cohort["terminal_temporally_evaluable"].astype(str).str.lower().eq("true")
    )
    if int(cohort["terminal_temporally_evaluable"].sum()) != 6:
        raise ValueError("#203 development labels must contain exactly 6 temporally evaluable taxa")
    return cohort.sort_values("speciesKey").reset_index(drop=True)


def diagnose_taxon(row: pd.Series) -> dict[str, Any]:
    species_key = int(row["speciesKey"])
    scientific_name = str(row["scientific_name"])
    frozen_region_id = str(row["frozen_historical_selected_region"])
    raw, audit = fetch_gbif_occurrence_evidence(
        scientific_name,
        country="JP",
        year_from=2000,
        year_to=2020,
        maximum_records=10000,
    )
    if int(audit.matched_usage_key) != species_key:
        raise RuntimeError(
            f"provider identity drift: expected {species_key}, got {audit.matched_usage_key} for {scientific_name}"
        )
    strict = _strict_exact(raw, 1000.0)
    registry = region_registry()
    by_id = {str(region["region_id"]): region for region in registry}
    if frozen_region_id not in by_id:
        raise ValueError(f"unknown frozen historical region: {frozen_region_id}")

    full_counts: dict[str, int] = {}
    for region in registry:
        subset = _inside_region(strict, region)
        full_counts[str(region["region_id"])] = int(len(complete_link_clusters(subset, radius_km=0.5)))
    order = {str(region["region_id"]): int(region["order"]) for region in registry}
    reconstructed_region, reconstructed_count = min(
        ((region_id, int(full_counts[region_id])) for region_id in order),
        key=lambda item: (-item[1], order[item[0]]),
    )
    frozen_count = int(row["frozen_historical_population_count"])
    reconstruction_matches = bool(
        reconstructed_region == frozen_region_id and reconstructed_count == frozen_count
    )

    frozen_region_rows = _inside_region(strict, by_id[frozen_region_id])
    years = pd.to_numeric(frozen_region_rows["event_year"], errors="coerce")
    recent_historical = frozen_region_rows.loc[
        years.between(RECENT_HISTORICAL_START, RECENT_HISTORICAL_END, inclusive="both")
    ].copy().reset_index(drop=True)
    recent_historical_populations = int(
        len(complete_link_clusters(recent_historical, radius_km=0.5))
    )
    gate_pass = bool(recent_historical_populations >= 1)
    return {
        "speciesKey": species_key,
        "scientific_name": scientific_name,
        "frozen_historical_selected_region": frozen_region_id,
        "frozen_historical_population_count": frozen_count,
        "historical_reconstruction_matches_frozen": reconstruction_matches,
        "recent_historical_period": "2016-2020",
        "recent_historical_strict_records": int(len(recent_historical)),
        "recent_historical_population_count": recent_historical_populations,
        "recent_historical_persistence_gate_pass": gate_pass,
        "terminal_temporally_evaluable": bool(row["terminal_temporally_evaluable"]),
    }


def summarize(table: pd.DataFrame) -> dict[str, Any]:
    gate = table["recent_historical_persistence_gate_pass"].astype(bool)
    outcome = table["terminal_temporally_evaluable"].astype(bool)
    tp = int((gate & outcome).sum())
    fp = int((gate & ~outcome).sum())
    fn = int((~gate & outcome).sum())
    tn = int((~gate & ~outcome).sum())
    baseline = float(outcome.mean())
    sensitivity = float(tp / (tp + fn)) if (tp + fn) else 0.0
    ppv = float(tp / (tp + fp)) if (tp + fp) else 0.0
    enrichment = float(ppv / baseline) if baseline > 0 else 0.0
    stable = int(table["historical_reconstruction_matches_frozen"].sum())
    return {
        "schema_version": "japan-plant-v4-temporal-persistence-gate-development-v1",
        "status": (
            "DEVELOPMENT_COMPLETE_HISTORICAL_RECONSTRUCTION_STABLE"
            if stable == len(table)
            else "DEVELOPMENT_COMPLETE_WITH_HISTORICAL_DRIFT_NO_GATE_PROMOTION"
        ),
        "source_issue": 206,
        "source_confirmation_issue": 203,
        "taxa": int(len(table)),
        "historical_reconstruction_match_taxa": stable,
        "historical_reconstruction_drift_taxa": int(len(table) - stable),
        "candidate_gate": "frozen selected region has >=1 strict 0.5-km population cluster during 2016-2020",
        "gate_pass_taxa": int(gate.sum()),
        "ungated_temporally_evaluable_taxa": int(outcome.sum()),
        "ungated_evaluable_fraction": baseline,
        "two_by_two": {
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
            "true_negative": tn,
        },
        "evaluable_retention_sensitivity": sensitivity,
        "evaluable_fraction_among_gate_pass_ppv": ppv,
        "ppv_enrichment_over_ungated": enrichment,
        "candidate_frames_rescored": False,
        "terminal_203_decision_changed": False,
        "threshold_search_performed": False,
        "future_cohort_selected": False,
        "claim_boundary": "Development diagnostic only. A useful enrichment here does not validate the gate; promotion requires a new disjoint cohort whose gate and outcomes are frozen before heldout opening.",
    }


def run(cohort_path: Path = COHORT_PATH) -> tuple[dict[str, Any], pd.DataFrame]:
    cohort = load_cohort(cohort_path)
    table = pd.DataFrame([diagnose_taxon(row) for _, row in cohort.iterrows()])
    return summarize(table), table.sort_values("speciesKey").reset_index(drop=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, default=COHORT_PATH)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    summary, table = run(args.cohort)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    table.to_csv(args.out_dir / "taxon_temporal_persistence_diagnostics.csv", index=False)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
