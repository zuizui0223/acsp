#!/usr/bin/env python3
"""Predeclare the untouched factorial cohort for ACSP v2 confirmation.

This script only resolves species sampling frames and draws taxon-region pairs.
It never fetches focal occurrence rows, builds candidates, runs ACSP/GRTS/SDM,
or calculates held-out recovery.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from benchmark_general_random_taxa_regions import REGION_CELLS, TAXON_GROUPS, taxon_frame


PROTOCOL_PATH = Path("validation/acsp_v2_untouched_confirmation_protocol.json")
EXPECTED_PROTOCOL = "8b540a965e25789174ce97a976c36d8b659c3c0d2919693b8fcd766330532ebb"


def _canonical_fingerprint(path: Path) -> tuple[dict[str, object], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if expected != calculated or calculated != EXPECTED_PROTOCOL:
        raise ValueError(
            f"ACSP v2 confirmation protocol fingerprint mismatch: "
            f"file={expected!r}, calculated={calculated!r}, expected={EXPECTED_PROTOCOL!r}"
        )
    payload["protocol_fingerprint"] = expected
    return payload, calculated


def _read_scientific_names(path: Path) -> set[str]:
    if not path.exists():
        raise FileNotFoundError(f"exclusion file does not exist: {path}")
    frame = pd.read_csv(path)
    if "scientific_name" not in frame.columns:
        raise ValueError(f"exclusion file lacks scientific_name: {path}")
    return {
        value
        for value in frame["scientific_name"].dropna().astype(str).str.strip()
        if value
    }


def _prefix_excluded(name: str, prefixes: tuple[str, ...]) -> bool:
    text = str(name).strip().casefold()
    return any(text.startswith(prefix.casefold()) for prefix in prefixes)


def _record_strata(frame: pd.DataFrame, n_strata: int) -> pd.DataFrame:
    work = frame.copy().reset_index(drop=True)
    if work.empty:
        return work.assign(record_count_stratum=pd.Series(dtype="Int64"))
    if work["coordinate_records"].nunique() < n_strata or len(work) < n_strata:
        raise ValueError(
            f"sampling frame cannot form {n_strata} record-count strata: "
            f"rows={len(work)}, unique_counts={work['coordinate_records'].nunique()}"
        )
    rank = work["coordinate_records"].rank(method="first")
    work["record_count_stratum"] = pd.qcut(
        rank,
        q=n_strata,
        labels=False,
        duplicates="raise",
    ).astype(int)
    return work


def run(protocol_path: Path, output: Path) -> dict[str, object]:
    protocol, fingerprint = _canonical_fingerprint(protocol_path)
    cohort = protocol["cohort"]
    groups = list(map(str, cohort["taxon_groups"]))
    n_strata = int(cohort["record_count_strata"])
    per_cell = int(cohort["taxa_per_region_group_record_stratum"])
    expected_pairs = int(cohort["pair_count"])
    if expected_pairs != len(REGION_CELLS) * len(groups) * n_strata * per_cell:
        raise ValueError("factorial cohort dimensions do not equal declared pair_count")

    excluded_exact: set[str] = set()
    exclusion_rows: list[dict[str, str]] = []
    for raw in protocol["exclusion_files"]:
        path = Path(str(raw))
        names = _read_scientific_names(path)
        excluded_exact.update(names)
        exclusion_rows.extend(
            {"scientific_name": name, "exclusion_source": str(path), "exclusion_type": "exact"}
            for name in sorted(names)
        )
    prefixes = tuple(map(str, protocol.get("explicit_exclusion_prefixes", [])))
    exclusion_rows.extend(
        {"scientific_name": prefix, "exclusion_source": "protocol", "exclusion_type": "prefix"}
        for prefix in prefixes
    )

    rng_master = np.random.SeedSequence(int(cohort["seed"]))
    # One independent seed stream per fixed region x group x record stratum.
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
            eligible_for_strata = frame.loc[
                ~(frame["excluded_exact"] | frame["excluded_prefix"])
            ].copy()
            eligible_for_strata = _record_strata(eligible_for_strata, n_strata)

            for record_stratum in range(n_strata):
                child = np.random.default_rng(child_seeds[child_index])
                child_index += 1
                stratum = eligible_for_strata.loc[
                    eligible_for_strata["record_count_stratum"].eq(record_stratum)
                ].copy()
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
                    "post_protocol_exclusion_frame": int(len(eligible_for_strata)),
                    "stratum_frame": int(len(stratum)),
                    "available_unused_before_draw": int(len(available)),
                    "required_draws": per_cell,
                })
                if len(available) < per_cell:
                    raise RuntimeError(
                        f"insufficient untouched taxa for {region_name}/{group}/stratum{record_stratum}: "
                        f"available={len(available)}, required={per_cell}"
                    )

                chosen_positions = child.choice(len(available), size=per_cell, replace=False)
                chosen = available.iloc[np.sort(chosen_positions)].copy()
                for replicate, (_, row) in enumerate(chosen.iterrows(), start=1):
                    scientific_name = str(row.scientific_name).strip()
                    if scientific_name in used_taxa:
                        raise AssertionError("duplicate taxon selected despite global exclusion")
                    used_taxa.add(scientific_name)
                    selections.append({
                        "pair_id": pair_id,
                        "status": "predeclared",
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
    if len(declared) != expected_pairs:
        raise RuntimeError(f"declared {len(declared)} pairs, expected {expected_pairs}")
    if declared["scientific_name"].duplicated().any():
        duplicates = declared.loc[
            declared["scientific_name"].duplicated(keep=False), "scientific_name"
        ].tolist()
        raise RuntimeError(f"duplicate declared taxa: {duplicates}")
    if set(declared["scientific_name"]) & excluded_exact:
        raise RuntimeError("declared cohort overlaps exact exclusion set")
    if any(_prefix_excluded(value, prefixes) for value in declared["scientific_name"]):
        raise RuntimeError("declared cohort overlaps prefix exclusion set")

    expected_region_count = len(groups) * n_strata * per_cell
    expected_group_count = len(REGION_CELLS) * n_strata * per_cell
    expected_record_count = len(REGION_CELLS) * len(groups) * per_cell
    region_counts = declared["region_name"].value_counts().sort_index()
    group_counts = declared["taxon_group"].value_counts().sort_index()
    record_counts = declared["record_count_stratum"].value_counts().sort_index()
    if not (region_counts == expected_region_count).all():
        raise RuntimeError(f"region-cell imbalance: {region_counts.to_dict()}")
    if not (group_counts == expected_group_count).all():
        raise RuntimeError(f"taxon-group imbalance: {group_counts.to_dict()}")
    if not (record_counts == expected_record_count).all():
        raise RuntimeError(f"record-stratum imbalance: {record_counts.to_dict()}")

    output.mkdir(parents=True, exist_ok=True)
    declared.to_csv(output / "predeclared_taxon_region_pairs.csv", index=False)
    audit.to_csv(output / "sampling_frame_audit.csv", index=False)
    exclusions = pd.DataFrame(exclusion_rows).drop_duplicates().sort_values(
        ["exclusion_type", "scientific_name", "exclusion_source"], kind="mergesort"
    )
    exclusions.to_csv(output / "excluded_taxa.csv", index=False)

    result = {
        "status": "ready",
        "protocol_path": str(protocol_path),
        "protocol_fingerprint": fingerprint,
        "declared_pairs": int(len(declared)),
        "unique_declared_taxa": int(declared["scientific_name"].nunique()),
        "excluded_unique_exact_taxa": int(len(excluded_exact)),
        "explicit_exclusion_prefixes": list(prefixes),
        "taxon_group_counts": {str(key): int(value) for key, value in group_counts.items()},
        "geographic_stratum_counts": {
            str(key): int(value)
            for key, value in declared["geographic_stratum"].value_counts().sort_index().items()
        },
        "region_cell_counts": {str(key): int(value) for key, value in region_counts.items()},
        "record_count_stratum_counts": {str(key): int(value) for key, value in record_counts.items()},
        "sampling_frame_cells": int(len(audit)),
        "minimum_available_unused_in_cell_stratum": int(audit["available_unused_before_draw"].min()),
        "outcomes_inspected": False,
        "occurrence_rows_fetched_for_declared_taxa": False,
        "candidate_generation_run": False,
        "acsp_v2_run": False,
        "grts_run": False,
        "sdm_fitting_run": False,
        "heldout_recovery_run": False,
        "taxon_replacement_after_declaration_allowed": False,
    }
    (output / "cohort_manifest.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return result


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--protocol", type=Path, default=PROTOCOL_PATH)
    command.add_argument("--output", type=Path, default=Path("acsp_v2_confirmation_cohort"))
    return command


if __name__ == "__main__":
    print(json.dumps(run(**vars(parser().parse_args())), indent=2, ensure_ascii=False))
