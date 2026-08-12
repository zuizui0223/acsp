#!/usr/bin/env python3
"""Predeclare the model-bound fresh Practical Rescue confirmation cohort.

This stage samples taxon-region pairs only after the final rescue model and the
fresh confirmation protocol are cryptographically frozen. It never fetches
focal occurrence rows, generates candidates, runs selectors, or scores held-out
recovery.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from benchmark_general_random_taxa_regions import REGION_CELLS, TAXON_GROUPS, taxon_frame
from predeclare_practical_core_confirmation_cohort import (
    _prefix_excluded,
    _read_scientific_names,
    _record_strata,
)


def _canonical_protocol(path: Path) -> tuple[dict[str, object], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    stored = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if not stored or stored != calculated:
        raise ValueError(
            f"fresh confirmation protocol mismatch: stored={stored!r}, calculated={calculated!r}"
        )
    payload["protocol_fingerprint"] = stored
    return payload, calculated


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(protocol_path: Path, output: Path) -> dict[str, object]:
    protocol, fingerprint = _canonical_protocol(protocol_path)
    if protocol.get("confirmation_taxa_sampled_at_protocol_freeze") is not False:
        raise ValueError("fresh confirmation protocol was not frozen before taxon sampling")
    if protocol.get("confirmation_occurrence_outcomes_inspected_at_protocol_freeze") is not False:
        raise ValueError("fresh confirmation protocol reports pre-freeze outcome inspection")
    if protocol.get("missing_pair_artifacts_scored_as_zero") is not False:
        raise ValueError("fresh confirmation protocol permits missing artifacts to become zero")

    cohort = protocol["cohort"]
    groups = list(map(str, cohort["taxon_groups"]))
    n_strata = int(cohort["record_count_strata"])
    per_cell = int(cohort["taxa_per_region_group_record_stratum"])
    expected_pairs = int(cohort["pair_count"])
    expected_from_design = len(REGION_CELLS) * len(groups) * n_strata * per_cell
    if expected_pairs != expected_from_design:
        raise ValueError(
            f"fresh factorial dimensions imply {expected_from_design} pairs, not {expected_pairs}"
        )
    if expected_pairs != 192:
        raise ValueError("fresh promotion confirmation is frozen to exactly 192 pairs")

    exclusion_paths = [Path(str(value)) for value in protocol["exclusion_files"]]
    excluded_exact: set[str] = set()
    for path in exclusion_paths:
        excluded_exact.update(_read_scientific_names(path))
    expected_excluded = int(protocol["exclusion"]["excluded_unique_taxa"])
    if len(excluded_exact) != expected_excluded or expected_excluded != 264:
        raise ValueError(
            f"fresh exclusion union has {len(excluded_exact)} taxa, expected frozen 264"
        )
    canonical_exclusion_path = Path(str(protocol["exclusion"]["excluded_taxa_path"]))
    if canonical_exclusion_path not in exclusion_paths:
        raise ValueError("protocol exclusion path is not present in exclusion_files")
    if _sha256(canonical_exclusion_path) != str(protocol["exclusion"]["excluded_taxa_sha256"]):
        raise ValueError("fresh exclusion file hash differs from frozen protocol")

    prefixes = tuple(map(str, protocol.get("explicit_exclusion_prefixes", [])))
    rng_master = np.random.SeedSequence(int(cohort["seed"]))
    child_seeds = rng_master.spawn(len(REGION_CELLS) * len(groups) * n_strata)
    child_index = 0
    used_taxa: set[str] = set()
    selections: list[dict[str, object]] = []
    audits: list[dict[str, object]] = []
    pair_id = 1

    for region_index, cell_tuple in enumerate(REGION_CELLS):
        geographic, region_name, west, south, east, north = cell_tuple
        bounds = (float(west), float(south), float(east), float(north))
        for group in groups:
            if group not in TAXON_GROUPS:
                raise ValueError(f"unknown taxon group: {group}")
            frame = taxon_frame(
                bounds,
                TAXON_GROUPS[group],
                int(cohort["facet_limit"]),
                int(cohort["minimum_records"]),
            )
            if frame.empty:
                raise RuntimeError(f"empty taxon frame for {region_name} / {group}")
            frame = frame.drop_duplicates("scientific_name").copy()
            frame["excluded_exact"] = frame["scientific_name"].astype(str).isin(excluded_exact)
            frame["excluded_prefix"] = frame["scientific_name"].map(
                lambda value: _prefix_excluded(value, prefixes)
            )
            eligible = frame.loc[~(frame["excluded_exact"] | frame["excluded_prefix"])].copy()
            eligible = _record_strata(eligible, n_strata)

            for record_stratum in range(n_strata):
                child = np.random.default_rng(child_seeds[child_index])
                child_index += 1
                stratum = eligible.loc[eligible["record_count_stratum"].eq(record_stratum)].copy()
                available = stratum.loc[
                    ~stratum["scientific_name"].astype(str).isin(used_taxa)
                ].copy()
                available = available.sort_values(
                    ["scientific_name", "speciesKey"], kind="mergesort"
                ).reset_index(drop=True)
                audits.append({
                    "geographic_stratum": geographic,
                    "region_name": region_name,
                    "taxon_group": group,
                    "record_count_stratum": record_stratum,
                    "raw_taxon_frame": int(len(frame)),
                    "post_264_exclusion_frame": int(len(eligible)),
                    "stratum_frame": int(len(stratum)),
                    "available_unused_before_draw": int(len(available)),
                    "required_draws": per_cell,
                })
                if len(available) < per_cell:
                    raise RuntimeError(
                        f"insufficient fresh taxa for {region_name}/{group}/stratum{record_stratum}: "
                        f"available={len(available)}, required={per_cell}"
                    )
                chosen_positions = child.choice(len(available), size=per_cell, replace=False)
                chosen = available.iloc[np.sort(chosen_positions)].copy()
                for replicate, (_, row) in enumerate(chosen.iterrows(), start=1):
                    scientific_name = str(row.scientific_name).strip()
                    if scientific_name in used_taxa or scientific_name in excluded_exact:
                        raise AssertionError("fresh sampler selected a used or excluded taxon")
                    if _prefix_excluded(scientific_name, prefixes):
                        raise AssertionError("fresh sampler selected an excluded prefix")
                    used_taxa.add(scientific_name)
                    selections.append({
                        "pair_id": pair_id,
                        "status": "predeclared_fresh_after_final_model_freeze",
                        "taxon_group": group,
                        "kingdomKey": TAXON_GROUPS[group],
                        "geographic_stratum": geographic,
                        "region_name": region_name,
                        "region_cell_index": region_index + 1,
                        "west": bounds[0],
                        "south": bounds[1],
                        "east": bounds[2],
                        "north": bounds[3],
                        "speciesKey": int(row.speciesKey),
                        "scientific_name": scientific_name,
                        "coordinate_records": int(row.coordinate_records),
                        "record_count_stratum": record_stratum,
                        "within_cell_stratum_replicate": replicate,
                    })
                    pair_id += 1

    declared = pd.DataFrame(selections)
    audit = pd.DataFrame(audits)
    if len(declared) != expected_pairs or declared["scientific_name"].nunique() != expected_pairs:
        raise RuntimeError("fresh sampler failed the 192-pair unique-taxon contract")
    if set(declared["scientific_name"].astype(str)) & excluded_exact:
        raise RuntimeError("fresh cohort overlaps the frozen 264-taxon exclusion union")

    expected_region_count = len(groups) * n_strata * per_cell
    expected_group_count = len(REGION_CELLS) * n_strata * per_cell
    expected_record_count = len(REGION_CELLS) * len(groups) * per_cell
    region_counts = declared["region_name"].value_counts().sort_index()
    group_counts = declared["taxon_group"].value_counts().sort_index()
    record_counts = declared["record_count_stratum"].value_counts().sort_index()
    if not (region_counts == expected_region_count).all():
        raise RuntimeError(f"fresh region-cell imbalance: {region_counts.to_dict()}")
    if not (group_counts == expected_group_count).all():
        raise RuntimeError(f"fresh taxon-group imbalance: {group_counts.to_dict()}")
    if not (record_counts == expected_record_count).all():
        raise RuntimeError(f"fresh record-stratum imbalance: {record_counts.to_dict()}")

    output.mkdir(parents=True, exist_ok=True)
    cohort_path = output / "predeclared_taxon_region_pairs.csv"
    audit_path = output / "sampling_frame_audit.csv"
    declared.to_csv(cohort_path, index=False)
    audit.to_csv(audit_path, index=False)
    result = {
        "status": "fresh_confirmation_cohort_ready",
        "protocol_fingerprint": fingerprint,
        "final_model_sha256": str(protocol["final_model"]["model_sha256"]),
        "excluded_unique_taxa": 264,
        "declared_pairs": int(len(declared)),
        "unique_declared_taxa": int(declared["scientific_name"].nunique()),
        "taxon_group_counts": {str(k): int(v) for k, v in group_counts.items()},
        "region_cell_counts": {str(k): int(v) for k, v in region_counts.items()},
        "record_count_stratum_counts": {str(k): int(v) for k, v in record_counts.items()},
        "minimum_available_unused_in_cell_stratum": int(audit["available_unused_before_draw"].min()),
        "cohort_sha256": _sha256(cohort_path),
        "sampling_frame_audit_sha256": _sha256(audit_path),
        "occurrence_rows_fetched_for_declared_taxa": False,
        "candidate_generation_run": False,
        "rescue_selector_run": False,
        "grts_run": False,
        "heldout_recovery_run": False,
        "taxon_replacement_after_declaration_allowed": False,
    }
    (output / "cohort_manifest.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return result


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--protocol", dest="protocol_path", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    return command


if __name__ == "__main__":
    print(json.dumps(run(**vars(parser().parse_args())), indent=2, ensure_ascii=False))
