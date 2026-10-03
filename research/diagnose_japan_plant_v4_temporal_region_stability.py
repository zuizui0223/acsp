#!/usr/bin/env python3
"""Post-hoc temporal-region observability diagnosis for consumed #203 taxa.

This script does not rescore candidate frames and cannot alter the terminal #203
confirmation decision. It only asks where already-consumed 2021-2025 strict
provider evidence falls relative to each taxon's pre-outcome frozen historical
selected region.
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

COHORT_PATH = ROOT / "validation" / "japan_plant_v4_consumed_temporal_region_diagnostic_cohort.csv"


def region_registry() -> list[dict[str, Any]]:
    return [
        {
            "region_id": str(region_id),
            "region_name": str(region_name),
            "order": int(index),
            "west": float(west),
            "south": float(south),
            "east": float(east),
            "north": float(north),
        }
        for index, (region_id, region_name, _stratum, west, south, east, north) in enumerate(VALIDATED_JAPAN_REGIONS)
    ]


def classify_region_counts(
    counts: dict[str, int], historical_region: str, registry: list[dict[str, Any]] | None = None
) -> tuple[str, str, int]:
    registry = region_registry() if registry is None else registry
    order = {str(row["region_id"]): int(row["order"]) for row in registry}
    if historical_region not in order:
        raise ValueError(f"unknown historical region: {historical_region}")
    normalized = {str(key): int(value) for key, value in counts.items()}
    historical_count = int(normalized.get(historical_region, 0))
    best_region, best_count = min(
        ((str(region_id), int(normalized.get(str(region_id), 0))) for region_id in order),
        key=lambda item: (-item[1], order[item[0]]),
    )
    if historical_count > 0:
        classification = "same_region_recent_support"
    elif best_count > 0:
        classification = "other_fixed_region_recent_support"
    else:
        classification = "no_fixed_region_recent_support"
    return classification, best_region, best_count


def load_consumed_cohort(path: Path = COHORT_PATH) -> pd.DataFrame:
    cohort = pd.read_csv(path)
    required = {
        "speciesKey",
        "scientific_name",
        "historical_selected_region",
        "historical_population_count",
    }
    if not required.issubset(cohort.columns):
        raise ValueError(f"cohort missing columns: {sorted(required.difference(cohort.columns))}")
    if len(cohort) != 24 or cohort["speciesKey"].nunique() != 24:
        raise ValueError("#203 diagnostic cohort must contain exactly 24 unique provider identities")
    cohort["speciesKey"] = pd.to_numeric(cohort["speciesKey"], errors="raise").astype(int)
    cohort["historical_population_count"] = pd.to_numeric(
        cohort["historical_population_count"], errors="raise"
    ).astype(int)
    return cohort.sort_values("speciesKey").reset_index(drop=True)


def diagnose_taxon(row: pd.Series) -> dict[str, Any]:
    species_key = int(row["speciesKey"])
    scientific_name = str(row["scientific_name"])
    historical_region = str(row["historical_selected_region"])
    raw, audit = fetch_gbif_occurrence_evidence(
        scientific_name,
        country="JP",
        year_from=2021,
        year_to=2025,
        maximum_records=10000,
    )
    if int(audit.matched_usage_key) != species_key:
        raise RuntimeError(
            f"provider identity drift: expected {species_key}, got {audit.matched_usage_key} for {scientific_name}"
        )
    strict = _strict_exact(raw, 1000.0)
    registry = region_registry()
    counts: dict[str, int] = {}
    strict_records: dict[str, int] = {}
    for region in registry:
        subset = _inside_region(strict, region)
        strict_records[str(region["region_id"])] = int(len(subset))
        counts[str(region["region_id"])] = int(len(complete_link_clusters(subset, radius_km=0.5)))
    classification, best_region, best_count = classify_region_counts(counts, historical_region, registry)
    return {
        "speciesKey": species_key,
        "scientific_name": scientific_name,
        "historical_selected_region": historical_region,
        "historical_population_count": int(row["historical_population_count"]),
        "recent_raw_records_countrywide": int(len(raw)),
        "recent_strict_records_countrywide": int(len(strict)),
        "recent_strict_records_historical_region": int(strict_records[historical_region]),
        "recent_population_clusters_historical_region": int(counts[historical_region]),
        "best_recent_fixed_region": best_region,
        "best_recent_fixed_region_population_clusters": int(best_count),
        "region_support_class": classification,
        "recent_population_clusters_by_fixed_region": json.dumps(counts, sort_keys=True, separators=(",", ":")),
    }


def run(cohort_path: Path = COHORT_PATH) -> tuple[dict[str, Any], pd.DataFrame]:
    cohort = load_consumed_cohort(cohort_path)
    rows = [diagnose_taxon(row) for _, row in cohort.iterrows()]
    table = pd.DataFrame(rows).sort_values("speciesKey").reset_index(drop=True)
    counts = table["region_support_class"].value_counts().to_dict()
    transitions = (
        table.groupby(["historical_selected_region", "best_recent_fixed_region"], dropna=False)
        .size()
        .reset_index(name="taxa")
        .to_dict(orient="records")
    )
    summary = {
        "schema_version": "japan-plant-v4-temporal-region-stability-diagnostic-v1",
        "status": "POSTHOC_DIAGNOSTIC_COMPLETE_NO_CONFIRMATORY_RESCORING",
        "source_issue": 204,
        "source_confirmation_issue": 203,
        "taxa": int(len(table)),
        "classification_counts": {
            "same_region_recent_support": int(counts.get("same_region_recent_support", 0)),
            "other_fixed_region_recent_support": int(counts.get("other_fixed_region_recent_support", 0)),
            "no_fixed_region_recent_support": int(counts.get("no_fixed_region_recent_support", 0)),
        },
        "taxa_with_any_recent_strict_countrywide_record": int((table["recent_strict_records_countrywide"] > 0).sum()),
        "taxa_with_any_recent_fixed_region_population": int((table["best_recent_fixed_region_population_clusters"] > 0).sum()),
        "historical_to_best_recent_region_transitions": transitions,
        "terminal_203_decision_changed": False,
        "candidate_frames_rescored": False,
        "same_cohort_retuned": False,
        "claim_boundary": "This is provider-observability diagnosis on an already consumed cohort. It cannot rescue #203, establish biological absence, or justify a future confirmation without a new disjoint cohort and a newly frozen pre-outcome protocol.",
    }
    return summary, table


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
    table.to_csv(args.out_dir / "taxon_region_diagnostics.csv", index=False)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
