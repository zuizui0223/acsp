#!/usr/bin/env python3
"""Predeclare a new post-freeze cross-island vascular-plant confirmation cohort.

Sampling uses only GBIF species facets and species metadata. It does not fetch
selected-taxon occurrence coordinates, build support surfaces, or inspect any
held-out recovery outcome.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from benchmark_general_random_taxa_regions import GBIF_SPECIES, TAXON_GROUPS, _species_metadata, taxon_frame

EXPECTED = "b54ddec24993e107a722c1fd345e9e1592c44c87ae9892439756c7da81c2bd6f"


def canonical_protocol(path: Path) -> tuple[dict, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
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
    meta = pd.DataFrame(rows)
    return frame.merge(meta, on="speciesKey", how="inner")


def two_strata(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.sort_values(["coordinate_records", "scientific_name", "speciesKey"], kind="mergesort").reset_index(drop=True)
    if len(work) < 2 or work["coordinate_records"].nunique() < 2:
        raise ValueError("cannot form two record-count strata")
    rank = work["coordinate_records"].rank(method="first")
    work["record_count_stratum"] = pd.qcut(rank, q=2, labels=False, duplicates="raise").astype(int)
    return work


def run(protocol_path: Path, output: Path) -> dict:
    protocol, fingerprint = canonical_protocol(protocol_path)
    cohort = protocol["cohort"]
    cells = protocol["scope"]["island_cells"]
    excluded: set[str] = set()
    for raw in protocol["exclusions"]["files"]:
        excluded.update(read_names(Path(raw)))
    prefixes = tuple(map(str, protocol["exclusions"].get("explicit_prefixes", [])))

    frames = {}
    audits = []
    insufficient = []
    for cell in cells:
        island = str(cell["island_id"])
        bounds = tuple(float(cell[k]) for k in ("west", "south", "east", "north"))
        raw = taxon_frame(bounds, TAXON_GROUPS["plant"], int(cohort["facet_limit"]), int(cohort["minimum_coordinate_records_in_cell"]))
        vascular = enrich_required_taxonomy(raw, str(cohort["required_phylum"]), str(cohort["required_rank"]))
        filtered = vascular.drop_duplicates("scientific_name").copy()
        filtered = filtered[~filtered["scientific_name"].astype(str).isin(excluded)].copy()
        filtered = filtered[~filtered["scientific_name"].map(lambda x: prefix_excluded(x, prefixes))].copy()
        try:
            stratified = two_strata(filtered)
        except ValueError:
            stratified = filtered.assign(record_count_stratum=pd.Series(dtype="Int64"))
        frames[island] = stratified
        counts = stratified["record_count_stratum"].value_counts().to_dict() if "record_count_stratum" in stratified else {}
        sufficient = counts.get(0, 0) >= 1 and counts.get(1, 0) >= 1
        audits.append({"island_id": island, "raw_species_frame": len(raw), "vascular_frame": len(vascular), "post_exclusion_frame": len(filtered), "stratum_0": int(counts.get(0,0)), "stratum_1": int(counts.get(1,0)), "sufficient": bool(sufficient)})
        if not sufficient:
            insufficient.append(island)

    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(audits).to_csv(output / "sampling_frame_audit.csv", index=False)
    if insufficient:
        manifest = {"status":"sampling_frame_insufficient_no_cohort_drawn","protocol_fingerprint":fingerprint,"insufficient_islands":insufficient,"taxa_drawn":0,"occurrence_coordinates_fetched":False,"support_built":False,"heldout_outcomes_inspected":False}
        (output / "cohort_manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
        return manifest

    seeds = np.random.SeedSequence(int(cohort["seed"])).spawn(len(cells)*2)
    used: set[str] = set()
    rows=[]; seed_i=0; pair_id=1
    for cell in cells:
        island=str(cell["island_id"]); frame=frames[island]
        for stratum in (0,1):
            rng=np.random.default_rng(seeds[seed_i]); seed_i+=1
            pool=frame[frame["record_count_stratum"].eq(stratum) & ~frame["scientific_name"].astype(str).isin(used)].sort_values(["scientific_name","speciesKey"],kind="mergesort").reset_index(drop=True)
            if pool.empty:
                raise RuntimeError(f"global uniqueness exhausted {island} stratum {stratum}")
            chosen=pool.iloc[int(rng.integers(0,len(pool)))]; name=str(chosen.scientific_name).strip(); used.add(name)
            rows.append({"pair_id":pair_id,"status":"predeclared","island_id":island,"west":float(cell["west"]),"south":float(cell["south"]),"east":float(cell["east"]),"north":float(cell["north"]),"speciesKey":int(chosen.speciesKey),"scientific_name":name,"phylum":str(chosen.phylum),"class":str(chosen["class"]),"coordinate_records":int(chosen.coordinate_records),"record_count_stratum":stratum}); pair_id+=1
    declared=pd.DataFrame(rows)
    if len(declared)!=int(cohort["pair_count"]) or declared["scientific_name"].duplicated().any():
        raise RuntimeError("declared cohort violates pair-count or uniqueness contract")
    declared.to_csv(output / "predeclared_taxon_island_pairs.csv", index=False)
    manifest={"status":"ready_frozen_before_occurrence_retrieval","protocol_fingerprint":fingerprint,"method_freeze_fingerprint":protocol["method_freeze"]["fingerprint"],"declared_pairs":len(declared),"unique_taxa":declared.scientific_name.nunique(),"islands":declared.island_id.nunique(),"occurrence_coordinates_fetched":False,"support_built":False,"heldout_outcomes_inspected":False,"taxon_replacement_after_declaration_allowed":False}
    (output / "cohort_manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    return manifest


def main():
    p=argparse.ArgumentParser(); p.add_argument("--protocol",type=Path,required=True); p.add_argument("--output",type=Path,required=True); a=p.parse_args(); print(json.dumps(run(a.protocol,a.output),indent=2))

if __name__=="__main__": main()
