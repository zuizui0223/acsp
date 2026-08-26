#!/usr/bin/env python3
"""Freeze a genuinely fresh 48-taxon country-framed confirmation cohort.

This stage is identity-only. It may use fixed Japanese discovery cells, GBIF
species facets/metadata, historical 1900-2020 country facets, and pinned
country-geometry metadata. It must not fetch 2021-2025 occurrence rows,
generate candidate patches, compute robust worlds, or inspect lift outcomes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Callable, Sequence

import pandas as pd

from benchmark_general_random_taxa_regions import REGION_CELLS, TAXON_GROUPS, taxon_frame
from geographic_framing_country_registry_v3 import HISTORICAL_YEARS, fetch_country_facet_counts
from geoboundaries_v6_provider import (
    GEOBOUNDARIES_RELEASE_COMMIT,
    GEOBOUNDARIES_SOURCE_ID,
    fetch_geoboundaries_country_geometry,
)
from predeclare_country_framed_integration_development_v1 import (
    _geometry_digest_from_source_version,
    choose_historical_country,
)

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "validation" / "acsp_country_framed_fresh_heterogeneity_confirmation_v1.json"
EXPECTED_PROTOCOL_FINGERPRINT = "2ef792a09309008e0091cd9df70678b0719674352db95880c521d1f641a24520"
GROUP_ORDER = ("plant", "animal")


def protocol() -> dict[str, object]:
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    stored = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if stored != EXPECTED_PROTOCOL_FINGERPRINT or calculated != EXPECTED_PROTOCOL_FINGERPRINT:
        raise ValueError("fresh heterogeneity confirmation protocol fingerprint mismatch")
    if payload["method"]["scientific_method_changed"] is not False:
        raise ValueError("fresh confirmation may not change the authoritative scientific method")
    if payload["cohort"]["no_replacement_after_freeze"] is not True:
        raise ValueError("fresh confirmation replacement rule drift")
    payload["protocol_fingerprint"] = stored
    return payload


def target_strata(region_cell_index: int) -> tuple[int, int]:
    r = int(region_cell_index)
    return ((r - 1) % 4, (r + 1) % 4)


def _column(frame: pd.DataFrame, candidates: Sequence[str]) -> str | None:
    lowered = {str(c).lower(): str(c) for c in frame.columns}
    for candidate in candidates:
        hit = lowered.get(candidate.lower())
        if hit is not None:
            return hit
    return None


def exclusion_sets(cfg: dict[str, object]) -> tuple[set[int], set[str]]:
    paths = [cfg["v4_96"], cfg["framing_confirmation"], *cfg["upstream"]]
    keys: set[int] = set()
    names: set[str] = set()
    for relative in paths:
        path = ROOT / str(relative)
        if not path.is_file():
            raise FileNotFoundError(f"required exclusion file missing: {relative}")
        frame = pd.read_csv(path)
        key_col = _column(frame, ("speciesKey", "species_key"))
        name_col = _column(frame, ("scientific_name", "scientificName"))
        if key_col is not None:
            vals = pd.to_numeric(frame[key_col], errors="coerce").dropna().astype(int)
            keys.update(vals.tolist())
        if name_col is not None:
            names.update(frame[name_col].dropna().astype(str).str.strip().tolist())
    return keys, names


def identity_hash(seed: int, region: int, group: str, stratum: int, species_key: int) -> str:
    token = f"{int(seed)}|{int(region)}|{group}|{int(stratum)}|{int(species_key)}".encode("utf-8")
    return hashlib.sha256(token).hexdigest()


def select_hash_min(
    pool: pd.DataFrame, *, seed: int, region: int, group: str, stratum: int
) -> pd.Series:
    if pool.empty:
        raise ValueError(f"no fresh taxon for region={region}, group={group}, stratum={stratum}")
    work = pool.copy()
    work["_identity_hash"] = [
        identity_hash(seed, region, group, stratum, int(key))
        for key in pd.to_numeric(work["speciesKey"], errors="raise").astype(int)
    ]
    work = work.sort_values(["_identity_hash", "speciesKey", "scientific_name"], kind="mergesort")
    return work.iloc[0]


def freeze_fresh_taxa(
    frame_provider: Callable[[tuple[float, float, float, float], int, int, int], pd.DataFrame] = taxon_frame,
) -> pd.DataFrame:
    cfg = protocol()
    cohort_cfg = cfg["cohort"]
    exclusion_cfg = cfg["exclusions"]
    excluded_keys, excluded_names = exclusion_sets(exclusion_cfg)
    prefixes = tuple(str(x) for x in exclusion_cfg["explicit_prefixes"])
    used_keys: set[int] = set()
    used_names: set[str] = set()
    rows: list[dict[str, object]] = []
    seed = int(cohort_cfg["selection_seed"])
    facet_limit = int(cohort_cfg["facet_limit"])
    minimum_records = int(cohort_cfg["minimum_records"])

    if len(REGION_CELLS) != int(cohort_cfg["regions"]):
        raise ValueError("fixed region-cell count drift")

    for region_index, cell in enumerate(REGION_CELLS, start=1):
        geographic_stratum, region_name, west, south, east, north = cell
        bounds = (float(west), float(south), float(east), float(north))
        for group in GROUP_ORDER:
            frame = frame_provider(bounds, int(TAXON_GROUPS[group]), facet_limit, minimum_records).copy()
            required = {"speciesKey", "scientific_name", "coordinate_records"}
            missing = required - set(frame.columns)
            if missing:
                raise ValueError(f"fresh frame missing columns: {sorted(missing)}")
            frame["speciesKey"] = pd.to_numeric(frame["speciesKey"], errors="raise").astype(int)
            frame["scientific_name"] = frame["scientific_name"].astype(str).str.strip()
            frame["coordinate_records"] = pd.to_numeric(frame["coordinate_records"], errors="raise").astype(int)
            frame = frame.drop_duplicates(["speciesKey", "scientific_name"]).copy()
            frame = frame[
                ~frame["speciesKey"].isin(excluded_keys)
                & ~frame["scientific_name"].isin(excluded_names)
                & ~frame["scientific_name"].str.startswith(prefixes)
            ].copy()
            if len(frame) < 4:
                raise ValueError(f"fewer than four eligible fresh taxa for region={region_index}, group={group}")
            frame["record_count_stratum"] = pd.qcut(
                frame["coordinate_records"].rank(method="first"), 4, labels=False
            ).astype(int)

            for stratum in target_strata(region_index):
                pool = frame[
                    frame["record_count_stratum"].eq(int(stratum))
                    & ~frame["speciesKey"].isin(used_keys)
                    & ~frame["scientific_name"].isin(used_names)
                ].copy()
                chosen = select_hash_min(
                    pool, seed=seed, region=region_index, group=group, stratum=int(stratum)
                )
                key = int(chosen["speciesKey"])
                name = str(chosen["scientific_name"])
                used_keys.add(key)
                used_names.add(name)
                rows.append(
                    {
                        "fresh_pair_id": len(rows) + 1,
                        "status": "identity_predeclared",
                        "taxon_group": group,
                        "kingdomKey": int(TAXON_GROUPS[group]),
                        "geographic_stratum": str(geographic_stratum),
                        "region_name": str(region_name),
                        "region_cell_index": int(region_index),
                        "west": bounds[0],
                        "south": bounds[1],
                        "east": bounds[2],
                        "north": bounds[3],
                        "speciesKey": key,
                        "scientific_name": name,
                        "coordinate_records": int(chosen["coordinate_records"]),
                        "record_count_stratum": int(stratum),
                        "identity_selection_hash": str(chosen["_identity_hash"]),
                    }
                )

    out = pd.DataFrame(rows)
    if len(out) != 48 or out["speciesKey"].nunique() != 48 or out["scientific_name"].nunique() != 48:
        raise ValueError("fresh cohort is not exactly 48 unique taxa")
    if out["taxon_group"].value_counts().to_dict() != {"plant": 24, "animal": 24}:
        raise ValueError("fresh cohort taxon-group balance drift")
    for group in GROUP_ORDER:
        counts = (
            out[out["taxon_group"].eq(group)]["record_count_stratum"]
            .astype(int).value_counts().sort_index().to_dict()
        )
        if counts != {0: 6, 1: 6, 2: 6, 3: 6}:
            raise ValueError(f"fresh cohort record-stratum balance drift for {group}: {counts}")
    overlap_keys = set(out["speciesKey"].astype(int)) & excluded_keys
    overlap_names = set(out["scientific_name"].astype(str)) & excluded_names
    if overlap_keys or overlap_names:
        raise ValueError("fresh cohort overlaps a prior consumed taxon")
    return out


def freeze_country_declarations(taxa: pd.DataFrame) -> pd.DataFrame:
    cfg = protocol()
    method = cfg["method"]
    minimum = int(method["historical_country_min_count"])
    seed = int(method["country_selection_seed"])
    if list(HISTORICAL_YEARS) != list(method["historical_years"]):
        raise ValueError("historical year range drift")

    rows: list[dict[str, object]] = []
    for item in taxa.itertuples(index=False):
        base = item._asdict()
        key = int(base["speciesKey"])
        status = "country_declaration_failed"
        code = basis = source_id = source_version = digest = reason = ""
        count = 0
        counts_json = "{}"
        try:
            counts = dict(
                sorted((str(k).upper(), int(v)) for k, v in fetch_country_facet_counts(key, HISTORICAL_YEARS).items())
            )
            counts_json = json.dumps(counts, sort_keys=True, separators=(",", ":"))
            chosen, basis = choose_historical_country(
                counts, species_key=key, minimum_count=minimum, seed=seed
            )
            if chosen is None:
                reason = "no historical country satisfied frozen minimum-count rule"
            else:
                code = chosen
                count = int(counts[code])
                geom = fetch_geoboundaries_country_geometry(code)
                digest = _geometry_digest_from_source_version(geom.source_version)
                source_id = str(geom.source_id)
                source_version = str(geom.source_version)
                status = "declared"
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
        rows.append(
            {
                **base,
                "declaration_status": status,
                "selected_country_code": code,
                "country_selection_basis": basis,
                "historical_selected_country_count": count,
                "historical_country_counts_json": counts_json,
                "geometry_source_id": source_id,
                "geometry_source_version": source_version,
                "geometry_canonical_sha256": digest,
                "declaration_failure_reason": reason,
            }
        )
    return pd.DataFrame(rows)


def freeze(output: Path) -> dict[str, object]:
    protocol()
    output.mkdir(parents=True, exist_ok=True)
    taxa = freeze_fresh_taxa()
    declarations = freeze_country_declarations(taxa)
    identity_path = output / "predeclared_fresh_taxon_country_pairs.csv"
    declarations.to_csv(identity_path, index=False)
    manifest = {
        "status": "fresh_heterogeneity_confirmation_identities_frozen_before_candidates_or_heldout_outcomes",
        "protocol_fingerprint": EXPECTED_PROTOCOL_FINGERPRINT,
        "issue": 155,
        "declared_taxa": int(len(declarations)),
        "unique_species_keys": int(declarations["speciesKey"].nunique()),
        "taxon_group_counts": {
            str(k): int(v) for k, v in declarations["taxon_group"].value_counts().sort_index().items()
        },
        "record_count_stratum_counts_by_group": {
            group: {
                str(int(k)): int(v)
                for k, v in declarations[declarations["taxon_group"].eq(group)]["record_count_stratum"]
                .astype(int).value_counts().sort_index().items()
            }
            for group in GROUP_ORDER
        },
        "successful_country_declarations": int(declarations["declaration_status"].eq("declared").sum()),
        "failed_country_declarations": int(declarations["declaration_status"].ne("declared").sum()),
        "selected_country_counts": {
            str(k): int(v)
            for k, v in declarations.loc[declarations["declaration_status"].eq("declared"), "selected_country_code"]
            .value_counts().sort_index().items()
        },
        "ru_pair_ids": [
            int(x) for x in declarations.loc[declarations["selected_country_code"].eq("RU"), "fresh_pair_id"].tolist()
        ],
        "identity_csv_sha256": hashlib.sha256(identity_path.read_bytes()).hexdigest(),
        "provider_source_id": GEOBOUNDARIES_SOURCE_ID,
        "provider_release_commit": GEOBOUNDARIES_RELEASE_COMMIT,
        "recent_outcomes_opened": False,
        "candidate_generation_run": False,
        "robust_support_run": False,
        "random_baseline_run": False,
        "replacement_after_freeze_allowed": False,
        "scientific_method_changed": False,
    }
    (output / "cohort_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(freeze(args.output), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
