#!/usr/bin/env python3
"""Predeclare the untouched island cohort for frozen robust-support validation.

This script queries only GBIF species facets / species metadata to construct
sampling frames.  It never fetches occurrence coordinates for selected taxa,
builds an NDVI support envelope, or inspects held-out recovery.

All island sampling frames are audited for sufficient eligible taxa before any
random draw occurs.  If one island is insufficient, no cohort is declared.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from benchmark_general_random_taxa_regions import TAXON_GROUPS, taxon_frame

PROTOCOL_PATH = Path("validation/robust_support_island_random_validation_protocol.json")
EXPECTED_PROTOCOL = "6eb1e5e931ad50717b26e160911571af8dcebf92417c403035ba5bc492ccac2b"


def canonical_protocol(path: Path) -> tuple[dict, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    if expected != calculated or calculated != EXPECTED_PROTOCOL:
        raise ValueError(
            "island validation protocol fingerprint mismatch: "
            f"file={expected!r}, calculated={calculated!r}, "
            f"expected={EXPECTED_PROTOCOL!r}"
        )
    payload["protocol_fingerprint"] = expected
    return payload, calculated


def read_names(path: Path) -> set[str]:
    frame = pd.read_csv(path)
    if "scientific_name" not in frame.columns:
        raise ValueError(f"{path} lacks scientific_name")
    return {
        value
        for value in frame["scientific_name"].dropna().astype(str).str.strip()
        if value
    }


def prefix_excluded(name: str, prefixes: tuple[str, ...]) -> bool:
    text = str(name).strip().casefold()
    return any(text.startswith(prefix.casefold()) for prefix in prefixes)


def two_record_strata(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy().sort_values(
        ["coordinate_records", "scientific_name", "speciesKey"],
        kind="mergesort",
    ).reset_index(drop=True)
    if len(work) < 2 or work["coordinate_records"].nunique() < 2:
        raise ValueError("sampling frame cannot form two record-count strata")
    rank = work["coordinate_records"].rank(method="first")
    work["record_count_stratum"] = pd.qcut(
        rank, q=2, labels=False, duplicates="raise"
    ).astype(int)
    return work


def run(protocol_path: Path, output: Path) -> dict:
    protocol, fingerprint = canonical_protocol(protocol_path)
    cohort = protocol["cohort"]
    cells = list(protocol["scope"]["island_cells"])
    expected_pairs = int(cohort["pair_count"])
    per_island = int(cohort["taxa_per_island"])
    n_strata = int(cohort["within_island_record_count_strata"])
    if n_strata != 2 or per_island != 2:
        raise ValueError("v1 sampler expects exactly two strata and two taxa per island")
    if len(cells) * per_island != expected_pairs:
        raise ValueError("declared island design does not equal pair_count")

    excluded: set[str] = set()
    exclusion_rows = []
    for raw in protocol["exclusions"]["files"]:
        path = Path(str(raw))
        names = read_names(path)
        excluded.update(names)
        exclusion_rows.extend(
            {
                "scientific_name": name,
                "exclusion_source": str(path),
            }
            for name in sorted(names)
        )
    prefixes = tuple(map(str, protocol["exclusions"].get("explicit_prefixes", [])))

    frames: dict[str, pd.DataFrame] = {}
    audits = []
    insufficient = []
    for cell in cells:
        island = str(cell["island_id"])
        bounds = (
            float(cell["west"]),
            float(cell["south"]),
            float(cell["east"]),
            float(cell["north"]),
        )
        raw = taxon_frame(
            bounds,
            TAXON_GROUPS["plant"],
            int(cohort["facet_limit"]),
            int(cohort["minimum_coordinate_records_in_cell"]),
        )
        if raw.empty:
            filtered = raw.copy()
        else:
            filtered = raw.drop_duplicates("scientific_name").copy()
            filtered = filtered.loc[
                ~filtered["scientific_name"].astype(str).isin(excluded)
            ].copy()
            filtered = filtered.loc[
                ~filtered["scientific_name"].map(
                    lambda value: prefix_excluded(value, prefixes)
                )
            ].copy()
        try:
            stratified = two_record_strata(filtered)
        except ValueError:
            stratified = filtered.assign(record_count_stratum=pd.Series(dtype="Int64"))
        frames[island] = stratified
        stratum_counts = {
            int(key): int(value)
            for key, value in stratified["record_count_stratum"].value_counts().to_dict().items()
        } if "record_count_stratum" in stratified.columns else {}
        sufficient = all(stratum_counts.get(index, 0) >= 1 for index in range(n_strata))
        audits.append(
            {
                "island_id": island,
                "west": bounds[0],
                "south": bounds[1],
                "east": bounds[2],
                "north": bounds[3],
                "raw_species_frame": int(len(raw)),
                "post_exclusion_frame": int(len(filtered)),
                "stratum_0": int(stratum_counts.get(0, 0)),
                "stratum_1": int(stratum_counts.get(1, 0)),
                "sufficient_for_declared_draw": bool(sufficient),
            }
        )
        if not sufficient:
            insufficient.append(island)

    output.mkdir(parents=True, exist_ok=True)
    audit = pd.DataFrame(audits)
    audit.to_csv(output / "sampling_frame_audit.csv", index=False)
    pd.DataFrame(exclusion_rows).drop_duplicates().to_csv(
        output / "excluded_taxa.csv", index=False
    )

    if insufficient:
        result = {
            "status": "sampling_frame_insufficient_no_cohort_drawn",
            "protocol_fingerprint": fingerprint,
            "insufficient_islands": insufficient,
            "islands_audited": int(len(cells)),
            "taxa_drawn": 0,
            "occurrence_coordinates_fetched": False,
            "outcomes_inspected": False,
        }
        (output / "cohort_manifest.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
        return result

    # Only after every frame passed the availability audit do any random draws occur.
    seeds = np.random.SeedSequence(int(cohort["seed"])).spawn(len(cells) * n_strata)
    seed_index = 0
    used: set[str] = set()
    selections = []
    pair_id = 1
    for cell in cells:
        island = str(cell["island_id"])
        frame = frames[island]
        for stratum in range(n_strata):
            rng = np.random.default_rng(seeds[seed_index])
            seed_index += 1
            pool = frame.loc[
                frame["record_count_stratum"].eq(stratum)
                & ~frame["scientific_name"].astype(str).isin(used)
            ].copy()
            pool = pool.sort_values(
                ["scientific_name", "speciesKey"], kind="mergesort"
            ).reset_index(drop=True)
            if pool.empty:
                raise RuntimeError(
                    f"global uniqueness exhausted {island} stratum {stratum} after frame audit"
                )
            chosen = pool.iloc[int(rng.integers(0, len(pool)))]
            name = str(chosen.scientific_name).strip()
            used.add(name)
            selections.append(
                {
                    "pair_id": pair_id,
                    "status": "predeclared",
                    "taxon_group": "plant",
                    "kingdomKey": TAXON_GROUPS["plant"],
                    "island_id": island,
                    "west": float(cell["west"]),
                    "south": float(cell["south"]),
                    "east": float(cell["east"]),
                    "north": float(cell["north"]),
                    "speciesKey": int(chosen.speciesKey),
                    "scientific_name": name,
                    "coordinate_records": int(chosen.coordinate_records),
                    "record_count_stratum": int(stratum),
                }
            )
            pair_id += 1

    declared = pd.DataFrame(selections)
    if len(declared) != expected_pairs:
        raise RuntimeError(f"declared {len(declared)} pairs, expected {expected_pairs}")
    if declared["scientific_name"].duplicated().any():
        raise RuntimeError("duplicate taxon selected")
    if set(declared["scientific_name"]) & excluded:
        raise RuntimeError("new island cohort overlaps exclusion set")
    if any(prefix_excluded(value, prefixes) for value in declared["scientific_name"]):
        raise RuntimeError("new island cohort overlaps explicit prefix exclusion")

    declared.to_csv(output / "predeclared_taxon_island_pairs.csv", index=False)
    result = {
        "status": "ready_frozen_before_occurrence_retrieval",
        "protocol_fingerprint": fingerprint,
        "declared_pairs": int(len(declared)),
        "unique_taxa": int(declared["scientific_name"].nunique()),
        "islands": int(declared["island_id"].nunique()),
        "pairs_per_island": {
            str(key): int(value)
            for key, value in declared["island_id"].value_counts().sort_index().items()
        },
        "record_stratum_counts": {
            str(key): int(value)
            for key, value in declared["record_count_stratum"].value_counts().sort_index().items()
        },
        "occurrence_coordinates_fetched": False,
        "support_envelopes_built": False,
        "heldout_recovery_inspected": False,
        "taxon_replacement_after_declaration_allowed": False,
    }
    (output / "cohort_manifest.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--protocol", type=Path, default=PROTOCOL_PATH)
    command.add_argument(
        "--output",
        type=Path,
        default=Path("robust_support_island_cohort_20260815"),
    )
    return command


if __name__ == "__main__":
    args = parser().parse_args()
    print(json.dumps(run(args.protocol, args.output), indent=2))
