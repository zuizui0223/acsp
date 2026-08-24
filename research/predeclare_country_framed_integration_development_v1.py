#!/usr/bin/env python3
"""Freeze the 24 taxon-country identities for integration development v1.

This is stage 1 only. It may inspect the already-opened v4 development identity
file, historical (1900--2020) focal-species country facets, and the already-
frozen geoBoundaries provider. It must not inspect 2021--2025 outcomes, generate
candidate patches, run robust support, replace failed taxa, or widen the country
frame.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from geographic_framing_country_registry_v3 import HISTORICAL_YEARS, fetch_country_facet_counts
from geoboundaries_v6_provider import (
    GEOBOUNDARIES_RELEASE_COMMIT,
    GEOBOUNDARIES_SOURCE_ID,
    fetch_geoboundaries_country_geometry,
)

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "validation" / "acsp_country_framed_robust_integration_development_v1.json"
SOURCE_COHORT_PATH = ROOT / "validation" / "geographic_framing_development_v4" / "predeclared_taxon_region_pairs.csv"
CONFIRMATION_TAXA_PATH = ROOT / "validation" / "geographic_framing_confirmation_v1" / "confirmation_taxa.csv"
EXPECTED_PROTOCOL_FINGERPRINT = "b35b1fee5dd899e800d2449d966266b15df8f4b8987fe3ddcf49c6e7884b092a"


def _protocol() -> dict[str, object]:
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    stored = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if stored != EXPECTED_PROTOCOL_FINGERPRINT or calculated != EXPECTED_PROTOCOL_FINGERPRINT:
        raise ValueError(
            f"integration development protocol fingerprint mismatch: file={stored}, calculated={calculated}, expected={EXPECTED_PROTOCOL_FINGERPRINT}"
        )
    payload["protocol_fingerprint"] = stored
    return payload


def select_development_taxa(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply the predeclared 12-region x 2-group x rotating-stratum rule."""
    required = {"region_cell_index", "taxon_group", "record_count_stratum", "speciesKey", "scientific_name"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"v4 cohort lacks required columns: {missing}")

    rows: list[pd.Series] = []
    for region_cell_index in range(1, 13):
        wanted_stratum = (region_cell_index - 1) % 4
        for taxon_group in ("plant", "animal"):
            matches = frame[
                (pd.to_numeric(frame["region_cell_index"], errors="coerce") == region_cell_index)
                & (frame["taxon_group"].astype(str) == taxon_group)
                & (pd.to_numeric(frame["record_count_stratum"], errors="coerce") == wanted_stratum)
            ]
            if len(matches) != 1:
                raise ValueError(
                    f"expected one v4 row for region_cell_index={region_cell_index}, taxon_group={taxon_group}, stratum={wanted_stratum}; found {len(matches)}"
                )
            rows.append(matches.iloc[0])

    selected = pd.DataFrame(rows).reset_index(drop=True)
    selected.insert(0, "integration_pair_id", range(1, len(selected) + 1))
    if len(selected) != 24 or selected["speciesKey"].nunique() != 24:
        raise ValueError("predeclared integration cohort is not 24 unique taxa")
    counts = selected["taxon_group"].value_counts().to_dict()
    if counts != {"plant": 12, "animal": 12}:
        raise ValueError(f"unexpected taxon-group counts: {counts}")
    strata = selected["record_count_stratum"].astype(int).value_counts().sort_index().to_dict()
    if strata != {0: 6, 1: 6, 2: 6, 3: 6}:
        raise ValueError(f"unexpected record-count-stratum counts: {strata}")
    return selected


def choose_historical_country(
    counts: dict[str, int],
    *,
    species_key: int,
    minimum_count: int,
    seed: int,
) -> tuple[str | None, str]:
    """Apply the frozen non-JP-preferred, hash-min country declaration rule."""
    eligible = {
        str(code).upper(): int(count)
        for code, count in counts.items()
        if len(str(code).strip()) == 2 and int(count) >= int(minimum_count)
    }
    non_jp = sorted(code for code in eligible if code != "JP")
    if non_jp:
        def key(code: str) -> str:
            token = f"{int(seed)}|{int(species_key)}|{code}".encode("utf-8")
            return hashlib.sha256(token).hexdigest()
        return min(non_jp, key=key), "non_jp_hash_min"
    if eligible.get("JP", 0) >= int(minimum_count):
        return "JP", "jp_fallback_no_eligible_non_jp"
    return None, "no_eligible_historical_country"


def _geometry_digest_from_source_version(source_version: str) -> str:
    marker = "canonical_geojson_sha256="
    for part in str(source_version).split(";"):
        if part.startswith(marker):
            digest = part[len(marker):].strip().lower()
            if len(digest) == 64 and all(ch in "0123456789abcdef" for ch in digest):
                return digest
    raise ValueError("provider source_version lacks canonical_geojson_sha256 provenance")


def freeze_declarations() -> tuple[pd.DataFrame, dict[str, object]]:
    protocol = _protocol()
    cohort = pd.read_csv(SOURCE_COHORT_PATH)
    selected = select_development_taxa(cohort)

    # Safety audit: the already-opened v4 development cohort must remain disjoint
    # from the fresh independent framing confirmation identities.
    if CONFIRMATION_TAXA_PATH.is_file():
        confirmation = pd.read_csv(CONFIRMATION_TAXA_PATH)
        overlap = set(selected["scientific_name"].astype(str)) & set(confirmation["scientific_name"].astype(str))
        if overlap:
            raise ValueError(f"integration development cohort overlaps fresh confirmation taxa: {sorted(overlap)[:5]}")

    country_cfg = protocol["country_selection"]
    minimum_count = int(country_cfg["historical_count_min"])
    seed = int(country_cfg["selection_seed"])
    output_rows: list[dict[str, object]] = []

    for row in selected.itertuples(index=False):
        base = row._asdict()
        species_key = int(base["speciesKey"])
        status = "country_declaration_failed"
        selected_country = ""
        selection_basis = ""
        historical_counts_json = "{}"
        historical_selected_country_count = 0
        geometry_source_id = ""
        geometry_source_version = ""
        geometry_canonical_sha256 = ""
        failure_reason = ""

        try:
            counts = fetch_country_facet_counts(species_key, HISTORICAL_YEARS)
            counts = dict(sorted((str(k).upper(), int(v)) for k, v in counts.items()))
            historical_counts_json = json.dumps(counts, sort_keys=True, separators=(",", ":"))
            selected_country, selection_basis = choose_historical_country(
                counts,
                species_key=species_key,
                minimum_count=minimum_count,
                seed=seed,
            )
            if selected_country is None:
                failure_reason = "no historical country satisfied the frozen minimum-count rule"
            else:
                historical_selected_country_count = int(counts[selected_country])
                geometry = fetch_geoboundaries_country_geometry(selected_country)
                if geometry.country_code != selected_country:
                    raise ValueError(
                        f"provider country mismatch: requested {selected_country}, returned {geometry.country_code}"
                    )
                geometry_source_id = str(geometry.source_id)
                geometry_source_version = str(geometry.source_version)
                geometry_canonical_sha256 = _geometry_digest_from_source_version(geometry.source_version)
                status = "declared"
        except Exception as exc:
            failure_reason = f"{type(exc).__name__}: {exc}"

        output_rows.append(
            {
                **base,
                "declaration_status": status,
                "selected_country_code": selected_country or "",
                "country_selection_basis": selection_basis,
                "historical_selected_country_count": historical_selected_country_count,
                "historical_country_counts_json": historical_counts_json,
                "geometry_source_id": geometry_source_id,
                "geometry_source_version": geometry_source_version,
                "geometry_canonical_sha256": geometry_canonical_sha256,
                "declaration_failure_reason": failure_reason,
            }
        )

    declarations = pd.DataFrame(output_rows)
    manifest: dict[str, object] = {
        "status": "country_framed_integration_development_v1_identities_frozen_before_outcomes",
        "protocol_fingerprint": EXPECTED_PROTOCOL_FINGERPRINT,
        "source_cohort_path": str(SOURCE_COHORT_PATH.relative_to(ROOT)),
        "declared_taxa": 24,
        "unique_declared_taxa": int(declarations["speciesKey"].nunique()),
        "taxon_group_counts": {
            key: int(value) for key, value in declarations["taxon_group"].value_counts().sort_index().items()
        },
        "record_count_stratum_counts": {
            str(int(key)): int(value)
            for key, value in declarations["record_count_stratum"].astype(int).value_counts().sort_index().items()
        },
        "successful_country_declarations": int(declarations["declaration_status"].eq("declared").sum()),
        "failed_country_declarations": int(declarations["declaration_status"].ne("declared").sum()),
        "historical_year_range": list(HISTORICAL_YEARS),
        "historical_country_min_count": minimum_count,
        "country_selection_seed": seed,
        "provider_source_id": GEOBOUNDARIES_SOURCE_ID,
        "provider_release_commit": GEOBOUNDARIES_RELEASE_COMMIT,
        "recent_outcomes_inspected": False,
        "recent_occurrence_rows_fetched": False,
        "candidate_generation_run": False,
        "robust_support_run": False,
        "random_baseline_run": False,
        "confirmation_v1_taxa_consumed": False,
        "replacement_after_declaration_allowed": False,
        "country_expansion_or_fallback_used": False,
    }
    return declarations, manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    declarations, manifest = freeze_declarations()
    declarations.to_csv(args.output / "predeclared_taxon_country_pairs.csv", index=False)
    identity_sha = hashlib.sha256((args.output / "predeclared_taxon_country_pairs.csv").read_bytes()).hexdigest()
    manifest["identity_csv_sha256"] = identity_sha
    (args.output / "cohort_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
