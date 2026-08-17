#!/usr/bin/env python3
"""Predeclare the new operational-budget development cohort without outcomes."""
from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from benchmark_general_random_taxa_regions import TAXON_GROUPS, _species_metadata, taxon_frame

EXPECTED = "00916d8eb5755c4bea19a415615c9b46fdb69804b22e97146f03565692d73b79"


def canonical_protocol(path: Path) -> tuple[dict, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    if expected != calculated or calculated != EXPECTED:
        raise ValueError(f"protocol fingerprint mismatch: file={expected} calculated={calculated} expected={EXPECTED}")
    payload["protocol_fingerprint"] = expected
    return payload, calculated


def read_names(path: Path) -> set[str]:
    frame = pd.read_csv(path)
    if "scientific_name" not in frame.columns:
        raise ValueError(f"{path} lacks scientific_name")
    return set(frame["scientific_name"].dropna().astype(str).str.strip())


def prefix_excluded(name: str, prefixes: tuple[str, ...]) -> bool:
    text = str(name).strip().casefold()
    return any(text.startswith(prefix.casefold()) for prefix in prefixes)


def enrich_required_taxonomy(frame: pd.DataFrame, phylum: str, rank: str) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    keys = frame["speciesKey"].astype(int).tolist()
    def keep(key: int):
        meta = _species_metadata(int(key))
        if meta is None:
            return None
        if str(meta.get("rank") or "").upper() != rank.upper():
            return None
        if str(meta.get("phylum") or "") != phylum:
            return None
        return {"speciesKey": int(key), "phylum": str(meta.get("phylum") or ""), "class": str(meta.get("class") or "")}
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = [row for row in pool.map(keep, keys) if row is not None]
    if not rows:
        return frame.iloc[0:0].copy()
    return frame.merge(pd.DataFrame(rows), on="speciesKey", how="inner")


def n_strata(frame: pd.DataFrame, n: int) -> pd.DataFrame:
    if frame.empty:
        return frame.assign(record_count_stratum=pd.Series(dtype="Int64"))
    work = frame.sort_values(["coordinate_records", "scientific_name", "speciesKey"], kind="mergesort").reset_index(drop=True)
    if len(work) < n or work["coordinate_records"].nunique() < n:
        return work.assign(record_count_stratum=pd.Series([pd.NA] * len(work), dtype="Int64"))
    rank = work["coordinate_records"].rank(method="first")
    work["record_count_stratum"] = pd.qcut(rank, q=n, labels=False, duplicates="raise").astype(int)
    return work


def run(protocol_path: Path, output: Path) -> dict:
    protocol, fingerprint = canonical_protocol(protocol_path)
    cohort = protocol["cohort"]
    cells = list(protocol["scope"]["island_cells"])
    n = int(cohort["within_island_record_count_strata"])
    per_island = int(cohort["taxa_per_island"])
    if n != per_island:
        raise ValueError("sampler expects one taxon per record-count stratum")
    if len(cells) * per_island != int(cohort["pair_count"]):
        raise ValueError("island design does not match pair_count")

    excluded: set[str] = set()
    for raw in protocol["exclusions"]["files"]:
        excluded.update(read_names(Path(raw)))
    prefixes = tuple(map(str, protocol["exclusions"].get("explicit_prefixes", [])))

    frames: dict[str, pd.DataFrame] = {}
    audits = []
    insufficient = []
    for cell in cells:
        island = str(cell["island_id"])
        bounds = tuple(float(cell[key]) for key in ("west", "south", "east", "north"))
        raw = taxon_frame(
            bounds,
            TAXON_GROUPS["plant"],
            int(cohort["facet_limit"]),
            int(cohort["minimum_coordinate_records_in_cell"]),
        )
        vascular = enrich_required_taxonomy(raw, str(cohort["required_phylum"]), str(cohort["required_rank"]))
        filtered = vascular.drop_duplicates("scientific_name").copy() if "scientific_name" in vascular else vascular.copy()
        if not filtered.empty:
            filtered = filtered[~filtered["scientific_name"].astype(str).isin(excluded)].copy()
            filtered = filtered[~filtered["scientific_name"].map(lambda x: prefix_excluded(x, prefixes))].copy()
        stratified = n_strata(filtered, n)
        frames[island] = stratified
        counts = stratified["record_count_stratum"].value_counts().to_dict() if "record_count_stratum" in stratified else {}
        sufficient = all(int(counts.get(i, 0)) >= 1 for i in range(n))
        audits.append({
            "island_id": island,
            "raw_species_frame": int(len(raw)),
            "vascular_frame": int(len(vascular)),
            "post_exclusion_frame": int(len(filtered)),
            **{f"stratum_{i}": int(counts.get(i, 0)) for i in range(n)},
            "sufficient": bool(sufficient),
        })
        if not sufficient:
            insufficient.append(island)

    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(audits).to_csv(output / "sampling_frame_audit.csv", index=False)
    if insufficient:
        manifest = {
            "status": "sampling_frame_insufficient_no_cohort_drawn",
            "protocol_fingerprint": fingerprint,
            "insufficient_islands": insufficient,
            "declared_pairs": 0,
            "selected_taxon_occurrence_coordinates_fetched": False,
            "heldout_outcomes_inspected": False,
        }
        (output / "cohort_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        return manifest

    seeds = np.random.SeedSequence(int(cohort["seed"])).spawn(len(cells) * n)
    seed_i = 0
    pair_id = 1
    used: set[str] = set()
    rows = []
    for cell in cells:
        island = str(cell["island_id"])
        frame = frames[island]
        for stratum in range(n):
            rng = np.random.default_rng(seeds[seed_i]); seed_i += 1
            pool = frame[
                frame["record_count_stratum"].eq(stratum)
                & ~frame["scientific_name"].astype(str).isin(used)
            ].sort_values(["scientific_name", "speciesKey"], kind="mergesort").reset_index(drop=True)
            if pool.empty:
                raise RuntimeError(f"global uniqueness exhausted {island} stratum {stratum}")
            chosen = pool.iloc[int(rng.integers(0, len(pool)))]
            name = str(chosen.scientific_name).strip()
            used.add(name)
            rows.append({
                "pair_id": pair_id,
                "status": "predeclared_development",
                "island_id": island,
                "west": float(cell["west"]), "south": float(cell["south"]),
                "east": float(cell["east"]), "north": float(cell["north"]),
                "speciesKey": int(chosen.speciesKey),
                "scientific_name": name,
                "phylum": str(chosen.phylum),
                "class": str(chosen["class"]),
                "coordinate_records": int(chosen.coordinate_records),
                "record_count_stratum": int(stratum),
            })
            pair_id += 1

    declared = pd.DataFrame(rows)
    if len(declared) != int(cohort["pair_count"]) or declared["scientific_name"].duplicated().any():
        raise RuntimeError("declared cohort violates count or uniqueness contract")
    declared.to_csv(output / "predeclared_taxon_island_pairs.csv", index=False)
    manifest = {
        "status": "development_cohort_frozen_before_occurrence_retrieval",
        "protocol_fingerprint": fingerprint,
        "declared_pairs": int(len(declared)),
        "unique_taxa": int(declared["scientific_name"].nunique()),
        "islands": int(declared["island_id"].nunique()),
        "selected_taxon_occurrence_coordinates_fetched": False,
        "heldout_outcomes_inspected": False,
        "failed_confirmation_24_reused": False,
        "frozen_192_consumed": False,
    }
    (output / "cohort_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.protocol, args.output), indent=2))


if __name__ == "__main__":
    main()
