#!/usr/bin/env python3
"""Regenerate explicit ODSP fold inputs for a frozen ACSP taxon-region cohort."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from acsp.odsp_export import ODSPFoldExportConfig, write_odsp_fold_exports
from benchmark_general_random_taxa_regions import (
    _species_metadata,
    fetch_occurrences,
    rectangle_feature,
)
from gbif_fieldmap_builder_app import build_automatic_discover_bundle


def candidate_builder_for(row: pd.Series, bounds: tuple[float, float, float, float]):
    metadata = _species_metadata(int(row.speciesKey)) or {}
    metadata.setdefault("kingdom", "Plantae" if str(row.taxon_group) == "plant" else "Animalia")

    def build(training: pd.DataFrame) -> pd.DataFrame:
        rebuilt = training.copy().reset_index(drop=True)
        rebuilt["_row_id"] = range(len(rebuilt))
        bundle = build_automatic_discover_bundle(
            str(row.scientific_name),
            rebuilt,
            "ODSP confirmatory export",
            str(row.region_name),
            override_row_ids=rebuilt["_row_id"].tolist(),
            taxon_metadata=metadata,
            survey_bounds=bounds,
            survey_features=[rectangle_feature(bounds, str(row.region_name))],
            candidate_generation_only=True,
        )
        potential = bundle["potential_candidates"].copy()
        support = "integrated_support_score"
        if support not in potential.columns:
            support = "component_local_habitat_score"
        if support not in potential.columns:
            return pd.DataFrame(columns=["latitude", "longitude", "integrated_support_score"])
        return potential[["latitude", "longitude", support]].rename(columns={support: "integrated_support_score"})

    return build


def run(args: argparse.Namespace) -> dict[str, object]:
    sample = pd.read_csv(args.sample_file)
    sample = sample[sample["status"].eq("predeclared")].head(args.pairs).copy()
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    statuses = []
    for _, row in sample.iterrows():
        pair_id = int(row.pair_id)
        pair_dir = root / f"pair_{pair_id:03d}"
        try:
            occurrences = fetch_occurrences(row, args.records_per_pair)
            bounds = (float(row.west), float(row.south), float(row.east), float(row.north))
            config = ODSPFoldExportConfig(
                block_degrees=args.block_degrees,
                repeats=args.repeats,
                holdout_fraction=args.holdout_fraction,
                random_state=args.seed + pair_id,
            )
            summary = write_odsp_fold_exports(
                occurrences,
                candidate_builder_for(row, bounds),
                pair_dir,
                config=config,
                provenance={
                    "pair_id": pair_id,
                    "scientific_name": str(row.scientific_name),
                    "region_name": str(row.region_name),
                    "taxon_group": str(row.taxon_group),
                    "species_key": int(row.speciesKey),
                    "source_sample": str(Path(args.sample_file).resolve()),
                    "source_protocol": "ACSP frozen taxon-region cohort; ODSP explicit-coordinate regeneration",
                },
            )
            statuses.append({
                "pair_id": pair_id,
                "scientific_name": str(row.scientific_name),
                "region_name": str(row.region_name),
                "status": "complete",
                "exported_folds": int(len(summary)),
                "ready_folds": int(summary["status"].eq("ready").sum()),
            })
        except Exception as exc:
            statuses.append({
                "pair_id": pair_id,
                "scientific_name": str(row.scientific_name),
                "region_name": str(row.region_name),
                "status": "failed",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            })
        pd.DataFrame(statuses).to_csv(root / "pair_export_status.csv", index=False)
    result = {
        "sample_file": str(Path(args.sample_file).resolve()),
        "output": str(root.resolve()),
        "declared_pairs": int(len(sample)),
        "status_counts": pd.Series([row["status"] for row in statuses]).value_counts().to_dict(),
        "protocol": {
            "records_per_pair": args.records_per_pair,
            "block_degrees": args.block_degrees,
            "repeats": args.repeats,
            "holdout_fraction": args.holdout_fraction,
            "seed": args.seed,
        },
    }
    (root / "export_manifest.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--sample-file", required=True)
    command.add_argument("--output", required=True)
    command.add_argument("--pairs", type=int, default=24)
    command.add_argument("--records-per-pair", type=int, default=150)
    command.add_argument("--block-degrees", type=float, default=0.10)
    command.add_argument("--repeats", type=int, default=5)
    command.add_argument("--holdout-fraction", type=float, default=0.20)
    command.add_argument("--seed", type=int, default=20260702)
    return command


if __name__ == "__main__":
    print(json.dumps(run(parser().parse_args()), indent=2, ensure_ascii=False))
