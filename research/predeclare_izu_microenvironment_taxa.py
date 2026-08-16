#!/usr/bin/env python3
"""Predeclare unseen Izu plant taxa before microenvironment outcome recovery."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time
from typing import Any

import numpy as np
import pandas as pd
import requests

GBIF_SEARCH = "https://api.gbif.org/v1/occurrence/search"
GBIF_SPECIES = "https://api.gbif.org/v1/species"
ISLAND_BOUNDS = {
    "oshima": (139.30, 34.64, 139.47, 34.82),
    "toshima": (139.24, 34.49, 139.31, 34.55),
    "niijima": (139.20, 34.33, 139.31, 34.44),
    "shikinejima": (139.18, 34.30, 139.24, 34.35),
    "kozushima": (139.09, 34.17, 139.18, 34.26),
}


def polygon(bounds):
    w, s, e, n = bounds
    return [[w, s], [e, s], [e, n], [w, n], [w, s]]


def polygon_wkt(bounds) -> str:
    coordinates = ",".join(f"{lon} {lat}" for lon, lat in polygon(bounds))
    return f"POLYGON(({coordinates}))"


def get_json(url: str, params: dict[str, Any] | None = None, timeout: int = 60, attempts: int = 4):
    last = None
    for attempt in range(attempts):
        try:
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(0.5 * 2**attempt)
    raise RuntimeError(f"GBIF request failed: {last}")


def load_excluded(paths: list[Path], prefixes: list[str]) -> tuple[set[str], list[str]]:
    excluded: set[str] = set()
    for path in paths:
        frame = pd.read_csv(path)
        if "scientific_name" not in frame.columns:
            raise ValueError(f"{path} lacks scientific_name")
        excluded.update(frame["scientific_name"].dropna().astype(str).str.strip())
    return excluded, [value.casefold() for value in prefixes]


def taxon_sampling_frame(facet_limit: int, minimum_records: int) -> pd.DataFrame:
    """Build the five-island facet frame without fetching focal occurrence rows.

    GBIF's occurrence facet endpoint rejects the five-island MULTIPOLYGON used by
    the former one-shot query. Query each island as a simple POLYGON, sum counts
    by speciesKey, then apply the same five-island minimum-record threshold.
    """
    totals: dict[int, int] = {}
    island_counts: dict[int, dict[str, int]] = {}
    for island, bounds in ISLAND_BOUNDS.items():
        payload = get_json(
            GBIF_SEARCH,
            {
                "kingdomKey": 6,
                "geometry": polygon_wkt(bounds),
                "hasCoordinate": "true",
                "hasGeospatialIssue": "false",
                "occurrenceStatus": "PRESENT",
                "limit": 0,
                "facet": "speciesKey",
                "facetLimit": int(facet_limit),
                "facetMincount": 1,
            },
        )
        counts = payload.get("facets", [{}])[0].get("counts", [])
        for item in counts:
            key = int(item["name"])
            count = int(item["count"])
            totals[key] = totals.get(key, 0) + count
            island_counts.setdefault(key, {})[island] = count

    eligible = [
        {"speciesKey": key, "coordinate_records": count}
        for key, count in totals.items()
        if count >= int(minimum_records)
    ]

    def resolve(item):
        key = int(item["speciesKey"])
        try:
            metadata = get_json(f"{GBIF_SPECIES}/{key}", timeout=30)
        except Exception:
            return None
        if metadata.get("rank") != "SPECIES" or not metadata.get("scientificName"):
            return None
        row = {
            "speciesKey": key,
            "scientific_name": str(metadata["scientificName"]),
            "coordinate_records": int(item["coordinate_records"]),
        }
        for island in ISLAND_BOUNDS:
            row[f"records_{island}"] = int(island_counts.get(key, {}).get(island, 0))
        return row

    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(resolve, eligible))
    return pd.DataFrame([row for row in rows if row is not None])


def choose_taxa(frame: pd.DataFrame, *, n_taxa: int, strata: int, seed: int, excluded: set[str], prefixes: list[str]) -> pd.DataFrame:
    work = frame.copy()
    work = work[~work["scientific_name"].isin(excluded)].copy()
    work = work[~work["scientific_name"].str.casefold().apply(lambda name: any(name.startswith(prefix) for prefix in prefixes))].copy()
    work = work.sort_values(["coordinate_records", "scientific_name"], kind="mergesort").reset_index(drop=True)
    if len(work) < n_taxa:
        raise RuntimeError(f"Only {len(work)} unused taxa remain; need {n_taxa}")
    if n_taxa % strata:
        raise ValueError("n_taxa must be divisible by strata")
    per = n_taxa // strata
    work["record_stratum"] = pd.qcut(work.index + 1, q=strata, labels=False, duplicates="raise")
    rng = np.random.default_rng(seed)
    selected = []
    for stratum in range(strata):
        group = work[work["record_stratum"].eq(stratum)]
        if len(group) < per:
            raise RuntimeError(f"record stratum {stratum} has only {len(group)} taxa")
        indices = rng.choice(group.index.to_numpy(), size=per, replace=False)
        selected.append(work.loc[indices])
    sample = pd.concat(selected).sort_values(["record_stratum", "coordinate_records", "scientific_name"], kind="mergesort").reset_index(drop=True)
    sample.insert(0, "sample_id", np.arange(1, len(sample) + 1))
    sample.insert(1, "status", "predeclared")
    return sample


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--excluded", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    protocol = json.loads(args.protocol.read_text())
    sampling = protocol["sampling"]
    excluded, prefixes = load_excluded(args.excluded, sampling["exclude_prefix"])
    frame = taxon_sampling_frame(sampling["facet_limit"], sampling["minimum_coordinate_records"])
    sample = choose_taxa(
        frame,
        n_taxa=sampling["taxa"],
        strata=sampling["record_strata"],
        seed=sampling["seed"],
        excluded=excluded,
        prefixes=prefixes,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.out / "taxon_sampling_frame.csv", index=False)
    sample.to_csv(args.out / "predeclared_taxa.csv", index=False)
    manifest = {
        "protocol_id": protocol["protocol_id"],
        "protocol_fingerprint": protocol["fingerprint"],
        "declared_taxa": int(len(sample)),
        "sampling_geometry": "five independent GBIF POLYGON facets; speciesKey counts summed before thresholding",
        "record_strata": {str(int(k)): int(v) for k, v in sample.groupby("record_stratum").size().items()},
        "outcomes_inspected": False,
        "focal_occurrence_rows_fetched": False,
        "candidate_generation_run": False,
        "heldout_recovery_run": False,
        "taxon_replacement_after_declaration": False,
    }
    (args.out / "cohort_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
