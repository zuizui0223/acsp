#!/usr/bin/env python3
"""Build the frozen taxon exclusion set for Practical Rescue confirmation.

This helper reads only already-frozen cohort/development tables. It does not
query occurrences, generate candidates, inspect held-out outcomes, or sample a
new confirmation taxon.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

EXPECTED_OLD_CONFIRMATION_TAXA = 192
EXPECTED_RESCUE_DEVELOPMENT_TAXA = 72
EXPECTED_UNION_TAXA = 264


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _names(path: Path, source: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if "scientific_name" not in frame.columns:
        raise ValueError(f"{path} lacks scientific_name")
    names = (
        frame["scientific_name"]
        .dropna()
        .astype(str)
        .str.strip()
    )
    names = names[names.ne("")].drop_duplicates().sort_values(kind="mergesort")
    return pd.DataFrame({"scientific_name": names.to_numpy(), "exclusion_source": source})


def run(old_cohort: Path, rescue_development: Path, output: Path) -> dict[str, object]:
    old = _names(old_cohort, "old_192_untouched_confirmation")
    rescue = _names(rescue_development, "rescue_72_development")
    if len(old) != EXPECTED_OLD_CONFIRMATION_TAXA:
        raise ValueError(f"old confirmation contains {len(old)} unique taxa, expected 192")
    if len(rescue) != EXPECTED_RESCUE_DEVELOPMENT_TAXA:
        raise ValueError(f"rescue development contains {len(rescue)} unique taxa, expected 72")

    overlap = sorted(set(old.scientific_name) & set(rescue.scientific_name))
    if overlap:
        raise ValueError(f"old confirmation and rescue development taxa overlap: {overlap[:10]}")

    combined = pd.concat([old, rescue], ignore_index=True)
    if combined["scientific_name"].duplicated().any():
        raise AssertionError("fresh confirmation exclusion union contains duplicates")
    combined = combined.sort_values(["scientific_name", "exclusion_source"], kind="mergesort").reset_index(drop=True)
    if len(combined) != EXPECTED_UNION_TAXA:
        raise ValueError(f"exclusion union contains {len(combined)} taxa, expected 264")

    output.mkdir(parents=True, exist_ok=True)
    exclusion_path = output / "excluded_taxa.csv"
    combined.to_csv(exclusion_path, index=False)
    manifest = {
        "status": "fresh_confirmation_exclusion_set_frozen",
        "old_confirmation_unique_taxa": int(len(old)),
        "rescue_development_unique_taxa": int(len(rescue)),
        "cross_source_overlap_taxa": 0,
        "excluded_unique_taxa": int(len(combined)),
        "old_cohort_input_sha256": _sha256(old_cohort),
        "rescue_development_input_sha256": _sha256(rescue_development),
        "excluded_taxa_sha256": _sha256(exclusion_path),
        "new_confirmation_taxa_sampled": False,
        "occurrence_outcomes_inspected": False,
    }
    (output / "exclusion_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--old-cohort", type=Path, required=True)
    command.add_argument("--rescue-development", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    return command


if __name__ == "__main__":
    print(json.dumps(run(**vars(parser().parse_args())), indent=2, ensure_ascii=False))
