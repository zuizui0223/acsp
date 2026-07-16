#!/usr/bin/env python3
"""Run direct occurrence-environment confirmation using the correct bundle tables.

The automatic candidate bundle exposes known occurrence environments separately as
``known_candidates`` and unknown survey environments as ``potential_candidates``.
The first direct benchmark incorrectly searched for known rows inside
``potential_candidates``. This wrapper fixes that table selection while preserving
all frozen confirmation thresholds and reporting.
"""

from __future__ import annotations

import json

import pandas as pd

import benchmark_random_taxa_occupancy_geometry_direct as direct
from benchmark_general_random_taxa_regions import _species_metadata, rectangle_feature
from gbif_fieldmap_builder_app import build_automatic_discover_bundle


def _environment_tables(
    row: pd.Series,
    occurrences: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    bounds = (float(row.west), float(row.south), float(row.east), float(row.north))
    metadata = _species_metadata(int(row.speciesKey)) or {}
    metadata.setdefault("kingdom", "Plantae" if row.taxon_group == "plant" else "Animalia")
    bundle = build_automatic_discover_bundle(
        str(row.scientific_name),
        occurrences.reset_index(drop=True),
        "random taxa direct occupancy-geometry benchmark",
        str(row.region_name),
        taxon_metadata=metadata,
        survey_bounds=bounds,
        survey_features=[rectangle_feature(bounds, str(row.region_name))],
        candidate_generation_only=True,
    )

    known = bundle.get("known_candidates", pd.DataFrame()).copy()
    available = bundle.get("potential_candidates", pd.DataFrame()).copy()
    shared = [
        column
        for column in direct.FEATURES
        if column in known.columns and column in available.columns
    ]
    if len(shared) < 2:
        raise ValueError(
            "fewer than two shared environmental features are available "
            f"(known={list(known.columns)}, available={list(available.columns)})"
        )

    required = shared + ["latitude", "longitude"]
    for frame in (known, available):
        for column in required:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    known = known.dropna(subset=required).drop_duplicates(
        subset=["latitude", "longitude"], keep="first"
    ).reset_index(drop=True)
    available = available.dropna(subset=required).drop_duplicates(
        subset=["latitude", "longitude"], keep="first"
    ).reset_index(drop=True)

    if len(known) < 4:
        raise ValueError(
            f"fewer than four complete known-candidate environmental rows remain ({len(known)})"
        )
    if len(available) < 10:
        raise ValueError(
            f"fewer than ten complete potential environments remain ({len(available)})"
        )
    return known, available, shared


def main() -> None:
    direct._environment_tables = _environment_tables
    args = direct.parser().parse_args()
    result = direct.run(args)
    result["environment_table_fix"] = {
        "occurrence_environment_source": "bundle.known_candidates",
        "null_environment_source": "bundle.potential_candidates",
    }
    output = direct.Path(args.output) / "occupancy_geometry_benchmark_summary.json"
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not result.get("passes_direct_confirmation_gate", False):
        raise SystemExit("Direct occurrence-environment confirmation gate failed")


if __name__ == "__main__":
    main()
