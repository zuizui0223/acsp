#!/usr/bin/env python3
"""Freeze the 456-taxon exclusion union for vNext2 untouched confirmation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

EXPECTED_PRIOR_EXCLUSIONS = 264
EXPECTED_INSPECTED_FRESH_V2 = 192
EXPECTED_UNION = 456


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _names(path: Path, source: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if "scientific_name" not in frame.columns:
        raise ValueError(f"{path} lacks scientific_name")
    names = frame["scientific_name"].dropna().astype(str).str.strip()
    names = names[names.ne("")].drop_duplicates().sort_values(kind="mergesort")
    return pd.DataFrame({"scientific_name": names.to_numpy(), "exclusion_source": source})


def run(prior_264: Path, inspected_fresh_v2: Path, output: Path) -> dict[str, object]:
    prior = _names(prior_264, "prior_264_old192_plus_rescue72")
    fresh = _names(inspected_fresh_v2, "inspected_fresh_v2_192_reclassified_development")
    if len(prior) != EXPECTED_PRIOR_EXCLUSIONS:
        raise ValueError(f"prior exclusion input has {len(prior)} taxa, expected 264")
    if len(fresh) != EXPECTED_INSPECTED_FRESH_V2:
        raise ValueError(f"inspected fresh-v2 input has {len(fresh)} taxa, expected 192")
    overlap = sorted(set(prior.scientific_name) & set(fresh.scientific_name))
    if overlap:
        raise ValueError(f"prior exclusions overlap inspected fresh-v2 taxa: {overlap[:10]}")
    combined = pd.concat([prior, fresh], ignore_index=True)
    combined = combined.sort_values(["scientific_name", "exclusion_source"], kind="mergesort").reset_index(drop=True)
    if len(combined) != EXPECTED_UNION or combined["scientific_name"].nunique() != EXPECTED_UNION:
        raise ValueError("vNext2 fresh exclusion union is not exactly 456 unique taxa")

    output.mkdir(parents=True, exist_ok=True)
    path = output / "excluded_taxa.csv"
    combined.to_csv(path, index=False)
    manifest = {
        "status": "vnext2_untouched_confirmation_exclusion_set_frozen",
        "prior_exclusion_unique_taxa": len(prior),
        "inspected_fresh_v2_unique_taxa": len(fresh),
        "cross_source_overlap_taxa": 0,
        "excluded_unique_taxa": len(combined),
        "prior_264_input_sha256": _sha256(prior_264),
        "inspected_fresh_v2_input_sha256": _sha256(inspected_fresh_v2),
        "excluded_taxa_sha256": _sha256(path),
        "new_confirmation_taxa_sampled": False,
        "new_confirmation_occurrence_outcomes_inspected": False,
    }
    (output / "exclusion_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--prior-264", type=Path, required=True)
    command.add_argument("--inspected-fresh-v2", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    return command


if __name__ == "__main__":
    print(json.dumps(run(**vars(parser().parse_args())), indent=2, ensure_ascii=False))
