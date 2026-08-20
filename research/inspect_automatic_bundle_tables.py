#!/usr/bin/env python3
"""Development diagnostic: list DataFrame products in one automatic ACSP bundle."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from benchmark_general_random_taxa_regions import _species_metadata, fetch_occurrences, rectangle_feature
from gbif_fieldmap_builder_app import build_automatic_discover_bundle


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-file", type=Path, required=True)
    parser.add_argument("--pair-id", type=int, required=True)
    parser.add_argument("--records", type=int, default=150)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    sample = pd.read_csv(args.sample_file)
    row = sample.loc[sample["pair_id"].eq(args.pair_id)].iloc[0]
    occurrences = fetch_occurrences(row, args.records)
    metadata = _species_metadata(int(row.speciesKey)) or {}
    metadata.setdefault("kingdom", "Plantae" if str(row.taxon_group) == "plant" else "Animalia")
    training = occurrences.copy().reset_index(drop=True)
    training["_row_id"] = range(len(training))
    bounds = (float(row.west), float(row.south), float(row.east), float(row.north))
    bundle = build_automatic_discover_bundle(
        str(row.scientific_name),
        training,
        "robust patch bundle diagnostic",
        str(row.region_name),
        override_row_ids=training["_row_id"].tolist(),
        taxon_metadata=metadata,
        survey_bounds=bounds,
        survey_features=[rectangle_feature(bounds, str(row.region_name))],
        candidate_generation_only=True,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    inventory = []
    for key, value in bundle.items():
        if isinstance(value, pd.DataFrame):
            inventory.append({
                "key": str(key),
                "rows": int(len(value)),
                "columns": list(map(str, value.columns)),
            })
            value.to_csv(args.out / f"{key}.csv", index=False)
        else:
            inventory.append({"key": str(key), "type": type(value).__name__})
    (args.out / "inventory.json").write_text(json.dumps(inventory, indent=2, default=str) + "\n")
    print(json.dumps(inventory, indent=2, default=str))


if __name__ == "__main__":
    main()
