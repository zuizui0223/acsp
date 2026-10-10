#!/usr/bin/env python3
"""Diagnose whether #204 shifted recent regions were already supported pre-outcome.

This is post-hoc design diagnosis on the consumed #203/#204 cohort. It re-opens
only 2000-2020 historical evidence, never rescoring candidate frames or changing
the terminal #203 decision.
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

COHORT_PATH = ROOT / "validation" / "japan_plant_v4_shifted_region_historical_support_cohort.csv"
HISTORICAL_QUALIFICATION_THRESHOLD = 5


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
        "posthoc_best_recent_fixed_region",
        "posthoc_best_recent_population_count",
    }
    if not required.issubset(cohort.columns):
        raise ValueError(f"cohort missing columns: {sorted(required.difference(cohort.columns))}")
    if len(cohort) != 10 or cohort["speciesKey"].nunique() != 10:
        raise ValueError("shifted-region diagnostic cohort must contain exactly 10 unique identities")
    cohort["speciesKey"] = pd.to_numeric(cohort["speciesKey"], errors="raise").astype(int)
    cohort["frozen_historical_population_count"] = pd.to_numeric(
        cohort["frozen_historical_population_count"], errors="raise"
    ).astype(int)
    cohort["posthoc_best_recent_population_count"] = pd.to_numeric(
        cohort["posthoc_best_recent_population_count"], errors="raise"
    ).astype(int)
    return cohort.sort_values("speciesKey").reset_index(drop=True)


def classify_later_region_historical_count(count: int) -> str:
    count = int(count)
    if count >= HISTORICAL_QUALIFICATION_THRESHOLD:
        return "later_region_already_historically_qualified"
    if count > 0:
        return "later_region_historically_supported_below_threshold"
    return "later_region_no_historical_support"


def diagnose_taxon(row: pd.Series) -> dict[str, Any]:
    species_key = int(row["speciesKey"])
    scientific_name = str(row["scientific_name"])
    frozen_region = str(row["frozen_historical_selected_region"])
    later_region = str(row["posthoc_best_recent_fixed_region"])
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
    counts: dict[str, int] = {}
    for region in registry:
        subset = _inside_region(strict, region)
        counts[str(region["region_id"])] = int(len(complete_link_clusters(subset, radius_km=0.5)))

    order = {str(region["region_id"]): int(region["order"]) for region in registry}
    current_best_region, current_best_count = min(
        ((region_id, int(counts[region_id])) for region_id in order),
        key=lambda item: (-item[1], order[item[0]]),
    )
    frozen_count = int(row["frozen_historical_population_count"])
    reconstruction_matches = bool(current_best_region == frozen_region and current_best_count == frozen_count)
    later_historical_count = int(counts[later_region])
    qualified_regions = [
        region_id
        for region_id in order
        if int(counts[region_id]) >= HISTORICAL_QUALIFICATION_THRESHOLD
    ]
    return {
        "speciesKey": species_key,
        "scientific_name": scientific_name,
        "frozen_historical_selected_region": frozen_region,
        "frozen_historical_population_count": frozen_count,
        "reconstructed_historical_selected_region": current_best_region,
        "reconstructed_historical_population_count": int(current_best_count),
        "historical_reconstruction_matches_frozen": reconstruction_matches,
        "posthoc_best_recent_fixed_region": later_region,
        "posthoc_best_recent_population_count": int(row["posthoc_best_recent_population_count"]),
        "later_region_historical_population_count": later_historical_count,
        "later_region_historical_support_class": classify_later_region_historical_count(later_historical_count),
        "historically_qualified_region_count": int(len(qualified_regions)),
        "historically_qualified_regions": json.dumps(qualified_regions, separators=(",", ":")),
        "historical_population_clusters_by_fixed_region": json.dumps(counts, sort_keys=True, separators=(",", ":")),
    }


def run(cohort_path: Path = COHORT_PATH) -> tuple[dict[str, Any], pd.DataFrame]:
    cohort = load_cohort(cohort_path)
    table = pd.DataFrame([diagnose_taxon(row) for _, row in cohort.iterrows()])
    class_counts = table["later_region_historical_support_class"].value_counts().to_dict()
    stable = int(table["historical_reconstruction_matches_frozen"].sum())
    qualified = int(class_counts.get("later_region_already_historically_qualified", 0))
    below = int(class_counts.get("later_region_historically_supported_below_threshold", 0))
    none = int(class_counts.get("later_region_no_historical_support", 0))
    design_inference_allowed = bool(stable == len(table))
    summary = {
        "schema_version": "japan-plant-v4-shifted-region-historical-support-diagnostic-v1",
        "status": (
            "POSTHOC_DIAGNOSTIC_COMPLETE_HISTORICAL_RECONSTRUCTION_STABLE"
            if design_inference_allowed
            else "POSTHOC_DIAGNOSTIC_COMPLETE_WITH_HISTORICAL_DRIFT_NO_DESIGN_INFERENCE"
        ),
        "source_issue": 205,
        "source_confirmation_issue": 203,
        "source_region_diagnostic_issue": 204,
        "taxa": int(len(table)),
        "historical_reconstruction_match_taxa": stable,
        "historical_reconstruction_drift_taxa": int(len(table) - stable),
        "later_region_historical_support_counts": {
            "later_region_already_historically_qualified": qualified,
            "later_region_historically_supported_below_threshold": below,
            "later_region_no_historical_support": none,
        },
        "fraction_shifted_taxa_later_region_already_historically_qualified": float(qualified / len(table)),
        "fraction_shifted_taxa_later_region_with_any_historical_support": float((qualified + below) / len(table)),
        "design_inference_allowed": design_inference_allowed,
        "terminal_203_decision_changed": False,
        "candidate_frames_rescored": False,
        "future_cohort_selected": False,
        "claim_boundary": "This post-hoc result diagnoses whether a multi-region pre-outcome unit definition could have retained already-visible historical support. It does not rescue #203 and cannot itself validate a revised method; any revised confirmation requires a new disjoint cohort frozen before heldout outcomes are opened.",
    }
    return summary, table.sort_values("speciesKey").reset_index(drop=True)


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
    table.to_csv(args.out_dir / "taxon_historical_support_diagnostics.csv", index=False)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
