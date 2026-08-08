#!/usr/bin/env python3
"""Predeclare the untouched taxon-region cohort for the fitted-SDM Top-k benchmark.

This script samples taxa only. It does not fetch focal-species occurrence rows,
build candidates, fit an SDM, or calculate held-out recovery.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from benchmark_general_random_taxa_regions import predeclare_pairs


def _canonical_fingerprint(protocol: dict[str, object]) -> str:
    payload = dict(protocol)
    expected = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if not expected or calculated != expected:
        raise ValueError(
            f"SDM Top-k protocol fingerprint mismatch: expected {expected!r}, calculated {calculated}"
        )
    return calculated


def _read_scientific_names(path: Path) -> set[str]:
    if not path.exists():
        raise FileNotFoundError(f"exclusion file does not exist: {path}")
    frame = pd.read_csv(path)
    if "scientific_name" not in frame.columns:
        raise ValueError(f"exclusion file lacks scientific_name: {path}")
    return set(frame["scientific_name"].dropna().astype(str).str.strip()) - {""}


def run(args: argparse.Namespace) -> dict[str, object]:
    protocol_path = Path(args.protocol)
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    fingerprint = _canonical_fingerprint(protocol)
    cohort = protocol["cohort"]
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    exclusion_rows: list[dict[str, str]] = []
    excluded_names: set[str] = set()
    for raw_path in protocol["exclusion_files"]:
        path = Path(str(raw_path))
        names = _read_scientific_names(path)
        excluded_names.update(names)
        exclusion_rows.extend(
            {"scientific_name": name, "source_file": str(path)}
            for name in sorted(names)
        )
    exclusions = pd.DataFrame(exclusion_rows).drop_duplicates().sort_values(
        ["scientific_name", "source_file"], kind="mergesort"
    )
    exclusions.to_csv(output / "excluded_taxa.csv", index=False)

    sample = predeclare_pairs(
        int(cohort["pair_count"]),
        int(cohort["seed"]),
        int(cohort["facet_limit"]),
        int(cohort["minimum_records"]),
        excluded_names,
        list(map(str, cohort["taxon_groups"])),
    )
    sample.to_csv(output / "predeclared_taxon_region_pairs.csv", index=False)

    declared = sample[sample.get("status", pd.Series(dtype=str)).eq("predeclared")].copy()
    overlap = sorted(set(declared.get("scientific_name", pd.Series(dtype=str)).dropna().astype(str)) & excluded_names)
    duplicate_taxa = sorted(
        declared.loc[declared["scientific_name"].astype(str).duplicated(), "scientific_name"].astype(str).unique()
    ) if not declared.empty else []
    group_counts = declared.get("taxon_group", pd.Series(dtype=str)).value_counts().sort_index().to_dict()
    stratum_counts = declared.get("geographic_stratum", pd.Series(dtype=str)).value_counts().sort_index().to_dict()

    result: dict[str, object] = {
        "status": "ready" if len(declared) == int(cohort["pair_count"]) and not overlap and not duplicate_taxa else "incomplete",
        "protocol_path": str(protocol_path),
        "protocol_fingerprint": fingerprint,
        "declared_pairs_requested": int(cohort["pair_count"]),
        "declared_pairs_obtained": int(len(declared)),
        "excluded_unique_taxa": int(len(excluded_names)),
        "excluded_taxon_source_files": list(map(str, protocol["exclusion_files"])),
        "overlap_with_excluded_taxa": overlap,
        "duplicate_declared_taxa": duplicate_taxa,
        "taxon_group_counts": {str(key): int(value) for key, value in group_counts.items()},
        "geographic_stratum_counts": {str(key): int(value) for key, value in stratum_counts.items()},
        "outcomes_inspected": False,
        "candidate_generation_run": False,
        "sdm_fitting_run": False,
        "heldout_recovery_run": False,
    }
    (output / "cohort_manifest.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if result["status"] != "ready":
        raise RuntimeError(json.dumps(result, ensure_ascii=False))
    return result


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--protocol", default="validation/sdm_topk_protocol.json")
    command.add_argument("--output", default="sdm_topk_cohort_predeclare")
    return command


if __name__ == "__main__":
    print(json.dumps(run(parser().parse_args()), indent=2, ensure_ascii=False))
