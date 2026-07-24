#!/usr/bin/env python3
"""Regenerate audited candidate-level folds for the frozen baseline benchmark."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from acsp.comparator_benchmark import StandardBaselineProtocol
from acsp.comparator_export import write_comparator_pair_export
from acsp.planning import integrated_candidate_scores
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
            "standard baseline confirmatory export",
            str(row.region_name),
            override_row_ids=rebuilt["_row_id"].tolist(),
            taxon_metadata=metadata,
            survey_bounds=bounds,
            survey_features=[rectangle_feature(bounds, str(row.region_name))],
            candidate_generation_only=True,
        )
        potential = bundle["potential_candidates"].copy()
        potential["surface_domain"] = str(bundle.get("surface_domain") or "terrestrial")
        potential["taxon_class"] = str(metadata.get("class") or "unknown").lower()
        return integrated_candidate_scores(potential, exclude_occurrence_derived=True)

    return build


def run(args: argparse.Namespace) -> dict[str, object]:
    protocol = StandardBaselineProtocol.from_json(args.protocol)
    sample = pd.read_csv(args.sample_file)
    sample = sample[sample["status"].eq("predeclared")].head(args.pairs).copy()
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    sample.to_csv(root / "declared_pairs.csv", index=False)
    statuses: list[dict[str, object]] = []
    for _, row in sample.iterrows():
        pair_id = int(row.pair_id)
        pair_dir = root / f"pair_{pair_id:03d}"
        provenance = {
            "pair_id": pair_id,
            "scientific_name": str(row.scientific_name),
            "region_name": str(row.region_name),
            "taxon_group": str(row.taxon_group),
            "geographic_stratum": str(row.geographic_stratum),
            "species_key": int(row.speciesKey),
            "source_sample": str(Path(args.sample_file).resolve()),
            "candidate_builder": "build_automatic_discover_bundle(candidate_generation_only=True)",
        }
        try:
            occurrences = fetch_occurrences(row, args.records_per_pair)
            bounds = (float(row.west), float(row.south), float(row.east), float(row.north))
            status = write_comparator_pair_export(
                occurrences,
                candidate_builder_for(row, bounds),
                pair_dir,
                protocol,
                pair_id=pair_id,
                random_state=protocol.random_state + pair_id,
                provenance=provenance,
            )
            statuses.append({
                **provenance,
                "status": "complete",
                "written_folds": int(len(status)),
                "ready_folds": int(status["status"].eq("ready").sum()),
                "environmentally_eligible_folds": int(status["environmentally_eligible"].sum()),
            })
        except Exception as exc:
            statuses.append({
                **provenance,
                "status": "failed",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "written_folds": 0,
                "ready_folds": 0,
                "environmentally_eligible_folds": 0,
            })
        pd.DataFrame(statuses).to_csv(root / "pair_export_status.csv", index=False)
    result = {
        "protocol": protocol.manifest(),
        "sample_file": str(Path(args.sample_file).resolve()),
        "declared_pairs": int(len(sample)),
        "status_counts": pd.Series([item["status"] for item in statuses]).value_counts().to_dict(),
        "output": str(root.resolve()),
        "interpretation": (
            "This artifact freezes training-only candidate pools and outcomes for later same-pool selection. "
            "No comparator result is used to alter the protocol."
        ),
    }
    (root / "export_manifest.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return result


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--sample-file", required=True)
    command.add_argument("--protocol", default="validation/standard_baseline_protocol.json")
    command.add_argument("--output", required=True)
    command.add_argument("--pairs", type=int, default=24)
    command.add_argument("--records-per-pair", type=int, default=150)
    return command


if __name__ == "__main__":
    print(json.dumps(run(parser().parse_args()), indent=2, ensure_ascii=False))
