from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

import preflight_cirsium_structural_population_holdout_v1 as mod


def _records(rows: list[tuple[str, float, float, int]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "gbif_key": key,
                "latitude": lat,
                "longitude": lon,
                "year": year,
                "coordinate_uncertainty_m": 100.0,
            }
            for key, lat, lon, year in rows
        ]
    )


def test_inside_region_is_inclusive_and_does_not_leak_outside_points() -> None:
    frame = _records(
        [
            ("west-south", 32.7, 132.5, 2001),
            ("east-north", 34.5, 134.5, 2002),
            ("inside", 33.5, 133.5, 2003),
            ("outside", 34.6, 133.5, 2004),
        ]
    )
    got = mod.inside_region(frame, (132.5, 32.7, 134.5, 34.5))
    assert got["gbif_key"].tolist() == ["west-south", "east-north", "inside"]


def test_full_period_exact_coordinate_dedupe_is_deterministic() -> None:
    frame = _records(
        [
            ("later", 35.0, 139.0, 2024),
            ("earlier", 35.0, 139.0, 2004),
            ("other", 35.1, 139.1, 2010),
        ]
    )
    got = mod.dedupe_exact_coordinates(frame)
    assert len(got) == 2
    assert got.loc[(got["latitude"] == 35.0) & (got["longitude"] == 139.0), "gbif_key"].item() == "earlier"


def test_population_count_uses_complete_link_half_km_rule() -> None:
    frame = _records(
        [
            ("a1", 35.0000, 139.0000, 2001),
            ("a2", 35.0005, 139.0005, 2002),
            ("b", 35.0200, 139.0000, 2003),
            ("c", 35.0400, 139.0000, 2004),
        ]
    )
    assert mod.population_cluster_count(frame, radius_km=0.5) == 3


def test_pair_status_preserves_baseline_and_failures() -> None:
    assert mod.classify_pair(
        family="COASTAL_ISLAND_STRUCTURE", population_clusters=3, minimum_clusters=3
    ) == "SPATIAL_HOLDOUT_ELIGIBLE"
    assert mod.classify_pair(
        family="COASTAL_ISLAND_STRUCTURE", population_clusters=2, minimum_clusters=3
    ) == "BELOW_MIN_POPULATIONS"
    assert mod.classify_pair(
        family=mod.BASELINE_FAMILY, population_clusters=20, minimum_clusters=3
    ) == "BASELINE_ONLY_NO_STRUCTURAL_FAMILY"
    assert mod.classify_pair(
        family="ALPINE_TOPOGRAPHIC_STRUCTURE",
        population_clusters=20,
        minimum_clusters=3,
        provider_failure=True,
    ) == "PROVIDER_FAILURE"


def test_frozen_contract_declares_exact_13_by_12_cartesian_frame() -> None:
    contract = mod._load_json(mod.CONTRACT_PATH)
    cohort = pd.read_csv(mod.COHORT_PATH, dtype=str).fillna("")
    units = mod._validate_contract_and_cohort(contract, cohort)
    regions = mod.region_registry()
    assert len(units) == 13
    assert units["species_binomial"].nunique() == 13
    assert len(regions) == 12
    assert len(units) * len(regions) == 156
    assert contract["pair_frame"]["declared_pair_count"] == 156
    assert contract["selector_run"] is False


def test_summary_counts_only_explicit_structural_eligible_status() -> None:
    pairs = pd.DataFrame(
        [
            {
                "cohort_unit_id": "CIR01",
                "species_binomial": "Cirsium sieboldii",
                "structural_feature_family": "WETLAND_MOISTURE_STRUCTURE",
                "region_id": "shikoku",
                "status": "SPATIAL_HOLDOUT_ELIGIBLE",
                "population_eligible_for_holdout": True,
            },
            {
                "cohort_unit_id": "CIR11",
                "species_binomial": "Cirsium tamastoloniferum",
                "structural_feature_family": mod.BASELINE_FAMILY,
                "region_id": "kanto",
                "status": "BASELINE_ONLY_NO_STRUCTURAL_FAMILY",
                "population_eligible_for_holdout": True,
            },
            {
                "cohort_unit_id": "CIR04",
                "species_binomial": "Cirsium otayae",
                "structural_feature_family": "ALPINE_TOPOGRAPHIC_STRUCTURE",
                "region_id": "chubu-mountains",
                "status": "BELOW_MIN_POPULATIONS",
                "population_eligible_for_holdout": False,
            },
        ]
    )
    contract = mod._load_json(mod.CONTRACT_PATH)
    contract = {**contract, "pair_frame": {**contract["pair_frame"], "declared_pair_count": 3}}
    summary = mod.summarize_pairs(pairs, contract=contract)
    assert summary["spatial_holdout_eligible_pairs"] == 1
    assert summary["spatial_holdout_eligible_unique_species"] == 1
    assert summary["eligible_pairs_by_structural_family"] == {"WETLAND_MOISTURE_STRUCTURE": 1}
    assert summary["baseline_only_pairs"] == 1
    assert summary["below_min_population_pairs"] == 1
