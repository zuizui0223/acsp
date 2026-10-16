#!/usr/bin/env python3
"""Preflight frozen Cirsium structural whole-population holdout eligibility.

This stage does not build structural layers, rank candidates, or select heldout
populations. It only asks whether each frozen Cirsium structural-family unit has
at least three strict public population clusters inside each of the twelve fixed
Japanese validation regions. All 13 x 12 = 156 pairs remain in the artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

from acsp.taxon_patches import VALIDATED_JAPAN_REGIONS
from benchmark_public_japan_cirsium_temporal_anchor_v1 import (
    deterministic_complete_link_greedy,
    fetch_gbif_species,
)

CONTRACT_PATH = ROOT / "validation" / "cirsium_structural_population_holdout_preflight_v1.json"
COHORT_PATH = ROOT / "validation" / "cirsium_aza3_prospective_validation_cohort_v1.csv"
BASELINE_FAMILY = "GENERAL_SPATIAL_BASELINE_ONLY"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def region_registry() -> list[dict[str, Any]]:
    return [
        {
            "region_id": str(region_id),
            "region_name": str(region_name),
            "geographic_stratum": str(stratum),
            "west": float(west),
            "south": float(south),
            "east": float(east),
            "north": float(north),
        }
        for region_id, region_name, stratum, west, south, east, north in VALIDATED_JAPAN_REGIONS
    ]


def inside_region(frame: pd.DataFrame, bounds: tuple[float, float, float, float]) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    west, south, east, north = (float(value) for value in bounds)
    return frame.loc[
        pd.to_numeric(frame["longitude"], errors="coerce").between(west, east, inclusive="both")
        & pd.to_numeric(frame["latitude"], errors="coerce").between(south, north, inclusive="both")
    ].copy().reset_index(drop=True)


def dedupe_exact_coordinates(frame: pd.DataFrame) -> pd.DataFrame:
    """Deterministically retain one record per exact coordinate over 2000-2025."""
    if frame.empty:
        return frame.copy()
    required = {"latitude", "longitude", "year", "gbif_key"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"occurrence frame missing required columns: {missing}")
    work = frame.copy()
    work["latitude"] = pd.to_numeric(work["latitude"], errors="coerce")
    work["longitude"] = pd.to_numeric(work["longitude"], errors="coerce")
    work["year"] = pd.to_numeric(work["year"], errors="coerce")
    work = work.dropna(subset=["latitude", "longitude", "year"])
    work = work.loc[work["year"].between(2000, 2025, inclusive="both")].copy()
    return (
        work.sort_values(["latitude", "longitude", "year", "gbif_key"], kind="mergesort")
        .drop_duplicates(subset=["latitude", "longitude"], keep="first")
        .reset_index(drop=True)
    )


def population_cluster_count(frame: pd.DataFrame, radius_km: float = 0.5) -> int:
    if frame.empty:
        return 0
    return int(len(deterministic_complete_link_greedy(frame, radius_km=float(radius_km))))


def classify_pair(
    *,
    family: str,
    population_clusters: int,
    minimum_clusters: int,
    provider_failure: bool = False,
) -> str:
    if provider_failure:
        return "PROVIDER_FAILURE"
    if str(family) == BASELINE_FAMILY:
        return "BASELINE_ONLY_NO_STRUCTURAL_FAMILY"
    if int(population_clusters) >= int(minimum_clusters):
        return "SPATIAL_HOLDOUT_ELIGIBLE"
    return "BELOW_MIN_POPULATIONS"


def _validate_contract_and_cohort(contract: dict[str, Any], cohort: pd.DataFrame) -> pd.DataFrame:
    if contract.get("status") != "FROZEN_BEFORE_STRUCTURAL_POPULATION_HOLDOUT_PREFLIGHT_EXECUTION":
        raise ValueError("structural population-holdout preflight contract is not frozen")
    if contract.get("selector_run") is not False:
        raise ValueError("preflight contract must keep selector_run=false")
    if git_blob_sha1(COHORT_PATH) != str(contract["source_cohort_git_blob_sha1"]):
        raise RuntimeError("SOURCE_COHORT_GIT_BLOB_DRIFT")

    cohort_cfg = contract["cohort"]
    unit_col = str(cohort_cfg["unit_id_column"])
    species_col = str(cohort_cfg["species_column"])
    family_col = str(cohort_cfg["structural_family_column"])
    required = {unit_col, species_col, family_col}
    missing = sorted(required.difference(cohort.columns))
    if missing:
        raise ValueError(f"source cohort missing required columns: {missing}")

    work = cohort[[unit_col, species_col, family_col]].copy()
    work.columns = ["cohort_unit_id", "species_binomial", "structural_feature_family"]
    work = work.fillna("")
    if len(work) != int(cohort_cfg["expected_unit_count"]):
        raise ValueError("frozen Cirsium cohort unit count drift")
    if work["cohort_unit_id"].nunique() != int(cohort_cfg["expected_unit_count"]):
        raise ValueError("Cirsium cohort unit IDs are not unique")
    if work["species_binomial"].nunique() != int(cohort_cfg["expected_unique_species"]):
        raise ValueError("Cirsium cohort species identities are not unique")

    regions = region_registry()
    region_ids = [row["region_id"] for row in regions]
    if region_ids != [str(value) for value in contract["pair_frame"]["fixed_region_ids"]]:
        raise RuntimeError("VALIDATED_JAPAN_REGIONS_IDENTITY_DRIFT")
    declared = int(contract["pair_frame"]["declared_pair_count"])
    if len(work) * len(regions) != declared:
        raise RuntimeError("DECLARED_PAIR_COUNT_DRIFT")

    allowed = set(str(value) for value in contract["structural_family_semantics"]["allowed_structural_families"])
    allowed.add(BASELINE_FAMILY)
    observed = set(work["structural_feature_family"].astype(str))
    unknown = sorted(observed.difference(allowed))
    if unknown:
        raise ValueError(f"unknown frozen structural families: {unknown}")
    return work


def _pair_row(
    unit: pd.Series,
    region: dict[str, Any],
    *,
    strict_unique_coordinates: int,
    population_clusters: int,
    minimum_clusters: int,
    species_audit: dict[str, Any] | None,
    provider_failure: str | None = None,
) -> dict[str, Any]:
    family = str(unit.structural_feature_family)
    failure = provider_failure is not None
    status = classify_pair(
        family=family,
        population_clusters=population_clusters,
        minimum_clusters=minimum_clusters,
        provider_failure=failure,
    )
    return {
        "pair_id": f"{unit.cohort_unit_id}__{region['region_id']}",
        "cohort_unit_id": str(unit.cohort_unit_id),
        "species_binomial": str(unit.species_binomial),
        "structural_feature_family": family,
        "region_id": str(region["region_id"]),
        "region_name": str(region["region_name"]),
        "geographic_stratum": str(region["geographic_stratum"]),
        "strict_unique_coordinates": int(strict_unique_coordinates),
        "population_clusters": int(population_clusters),
        "minimum_population_clusters": int(minimum_clusters),
        "population_eligible_for_holdout": bool(int(population_clusters) >= int(minimum_clusters)),
        "structural_selector_eligible_family": bool(family != BASELINE_FAMILY),
        "status": status,
        "provider_failure": "" if provider_failure is None else str(provider_failure),
        "species_raw_api_records_seen": "" if species_audit is None else int(species_audit.get("raw_api_records_seen", 0)),
        "species_strict_eligible_records_countrywide": "" if species_audit is None else int(species_audit.get("eligible_records", 0)),
    }


def summarize_pairs(pairs: pd.DataFrame, *, contract: dict[str, Any]) -> dict[str, Any]:
    eligible = pairs.loc[pairs["status"].eq("SPATIAL_HOLDOUT_ELIGIBLE")].copy()
    family_counts = {
        str(family): int(count)
        for family, count in eligible.groupby("structural_feature_family").size().sort_index().items()
    }
    family_species = {
        str(family): int(count)
        for family, count in eligible.groupby("structural_feature_family")["species_binomial"].nunique().sort_index().items()
    }
    return {
        "schema_version": "cirsium-structural-population-holdout-preflight-result-v1",
        "status": "STRUCTURAL_POPULATION_HOLDOUT_PREFLIGHT_COMPLETE",
        "source_contract": str(CONTRACT_PATH.relative_to(ROOT)),
        "source_cohort": str(COHORT_PATH.relative_to(ROOT)),
        "source_cohort_git_blob_sha1": git_blob_sha1(COHORT_PATH),
        "validated_product_changed": False,
        "automatic_global_adapter_changed": False,
        "new_confirmation_claim": False,
        "selector_run": False,
        "candidate_surface_built": False,
        "raw_structural_layers_built": False,
        "heldout_population_selected": False,
        "declared_units": int(pairs["cohort_unit_id"].nunique()),
        "declared_regions": int(pairs["region_id"].nunique()),
        "declared_pairs": int(len(pairs)),
        "expected_declared_pairs": int(contract["pair_frame"]["declared_pair_count"]),
        "spatial_holdout_eligible_pairs": int(len(eligible)),
        "spatial_holdout_eligible_unique_species": int(eligible["species_binomial"].nunique()),
        "eligible_pairs_by_structural_family": family_counts,
        "eligible_species_by_structural_family": family_species,
        "structural_families_with_any_eligible_pair": int(len(family_counts)),
        "baseline_only_pairs": int(pairs["status"].eq("BASELINE_ONLY_NO_STRUCTURAL_FAMILY").sum()),
        "below_min_population_pairs": int(pairs["status"].eq("BELOW_MIN_POPULATIONS").sum()),
        "provider_failure_pairs": int(pairs["status"].eq("PROVIDER_FAILURE").sum()),
        "provider_failure_species": int(pairs.loc[pairs["status"].eq("PROVIDER_FAILURE"), "species_binomial"].nunique()),
        "population_eligible_pairs_including_baseline": int(pairs["population_eligible_for_holdout"].astype(bool).sum()),
        "development_interpretation_boundary": "Preflight evidence adequacy only. No structural selector, candidate surface, hidden-population score, confirmation, occupancy, field-efficiency, route, access, time, budget, or stopping claim is evaluated here."
    }


def run(contract_path: Path = CONTRACT_PATH, cohort_path: Path = COHORT_PATH) -> tuple[pd.DataFrame, dict[str, Any]]:
    global CONTRACT_PATH, COHORT_PATH
    # Keep path overrides explicit for testing while preserving default frozen paths.
    original_contract, original_cohort = CONTRACT_PATH, COHORT_PATH
    CONTRACT_PATH, COHORT_PATH = Path(contract_path), Path(cohort_path)
    try:
        contract = _load_json(CONTRACT_PATH)
        cohort = pd.read_csv(COHORT_PATH, dtype=str).fillna("")
        units = _validate_contract_and_cohort(contract, cohort)
        regions = region_registry()
        minimum_clusters = int(contract["population_definition"]["minimum_clusters_for_whole_population_holdout"])
        radius_km = float(contract["population_definition"]["maximum_within_cluster_distance_km"])
        maximum_records = int(contract["occurrence_evidence"]["maximum_records_per_species"])

        pair_rows: list[dict[str, Any]] = []
        for unit in units.itertuples(index=False):
            try:
                records, audit = fetch_gbif_species(
                    str(unit.species_binomial),
                    maximum_records=maximum_records,
                )
                strict = dedupe_exact_coordinates(records)
            except Exception as exc:
                failure = f"{type(exc).__name__}:{exc}"
                for region in regions:
                    pair_rows.append(
                        _pair_row(
                            unit,
                            region,
                            strict_unique_coordinates=0,
                            population_clusters=0,
                            minimum_clusters=minimum_clusters,
                            species_audit=None,
                            provider_failure=failure,
                        )
                    )
                continue

            for region in regions:
                bounds = (region["west"], region["south"], region["east"], region["north"])
                subset = inside_region(strict, bounds)
                clusters = population_cluster_count(subset, radius_km=radius_km)
                pair_rows.append(
                    _pair_row(
                        unit,
                        region,
                        strict_unique_coordinates=int(len(subset)),
                        population_clusters=clusters,
                        minimum_clusters=minimum_clusters,
                        species_audit=audit,
                    )
                )

        pairs = pd.DataFrame(pair_rows)
        expected = int(contract["pair_frame"]["declared_pair_count"])
        if len(pairs) != expected or pairs["pair_id"].nunique() != expected:
            raise RuntimeError("PAIR_FRAME_COMPLETENESS_FAILURE")
        summary = summarize_pairs(pairs, contract=contract)
        return pairs, summary
    finally:
        CONTRACT_PATH, COHORT_PATH = original_contract, original_cohort


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    parser.add_argument("--cohort", type=Path, default=COHORT_PATH)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    pairs, summary = run(args.contract, args.cohort)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    pairs.to_csv(args.out_dir / "structural_population_holdout_preflight_pairs.csv", index=False)
    (args.out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
