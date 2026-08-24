#!/usr/bin/env python3
"""Run country-framed robust integration development v1 after identity freeze.

This stage accepts only the already-frozen stage-1 taxon-country declarations.
It refetches and verifies the pinned country geometry, builds the fixed 800-point
country surface, runs the unchanged validated 2.5% robust candidate-patch core,
and only then evaluates 2021--2025 occurrences at the predeclared 10 km radius.

Failed declarations, provider failures, candidate-generation failures, and zero
recent outcomes remain in the 24-taxon denominator and are never replaced.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from acsp.benchmarking import get_json
from acsp.taxon_patches import GBIF_SEARCH, ROBUST_TERRAIN_FEATURES
from acsp.validated_robust import (
    VALIDATED_ROBUST_PRIMARY_RADIUS_KM,
    VALIDATED_ROBUST_SUPPORT_FRACTION,
    validated_robust_candidate_patches,
)
from country_framed_robust_integration import country_terrain_inputs, fetch_country_occurrences
from geoboundaries_v6_provider import fetch_geoboundaries_country_geometry

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "validation" / "acsp_country_framed_robust_integration_development_v1.json"
EXPECTED_PROTOCOL_FINGERPRINT = "b35b1fee5dd899e800d2449d966266b15df8f4b8987fe3ddcf49c6e7884b092a"
EARTH_RADIUS_KM = 6371.0088


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


def _geometry_digest_from_source_version(source_version: str) -> str:
    marker = "canonical_geojson_sha256="
    for part in str(source_version).split(";"):
        if part.startswith(marker):
            digest = part[len(marker):].strip().lower()
            if len(digest) == 64 and all(ch in "0123456789abcdef" for ch in digest):
                return digest
    raise ValueError("provider source_version lacks canonical_geojson_sha256 provenance")


def fetch_recent_country_occurrences(
    taxon_key: int,
    country_code: str,
    *,
    years: tuple[int, int] = (2021, 2025),
    cap: int = 300,
) -> pd.DataFrame:
    """Fetch held-out recent coordinates with the frozen quality filters.

    Unlike the historical training helper, one recent record is enough to make
    the temporal outcome evaluable; the five-record minimum is a training-data
    requirement, not a held-out-outcome requirement.
    """
    from gbif_fieldmap_builder_app import clean_occurrences, detect_occurrence_columns, gbif_record_to_species_row

    code = str(country_code).strip().upper()
    start, end = map(int, years)
    payload = get_json(
        GBIF_SEARCH,
        {
            "taxonKey": int(taxon_key),
            "country": code,
            "year": f"{start},{end}",
            "hasCoordinate": "true",
            "hasGeospatialIssue": "false",
            "occurrenceStatus": "PRESENT",
            "limit": min(300, int(cap)),
            "offset": 0,
        },
    )
    records = payload.get("results", [])
    if not records:
        return pd.DataFrame(columns=["latitude", "longitude"])
    raw = pd.DataFrame([gbif_record_to_species_row(record) for record in records])
    if raw.empty:
        return pd.DataFrame(columns=["latitude", "longitude"])
    cleaned = clean_occurrences(raw, detect_occurrence_columns(raw)).copy().reset_index(drop=True)
    latitude_col = next((c for c in ("latitude", "_latitude", "decimalLatitude", "lat") if c in cleaned.columns), None)
    longitude_col = next((c for c in ("longitude", "_longitude", "decimalLongitude", "lon") if c in cleaned.columns), None)
    if latitude_col is None or longitude_col is None:
        raise ValueError("recent occurrence rows do not contain recognizable coordinates")
    return pd.DataFrame(
        {
            "latitude": pd.to_numeric(cleaned[latitude_col], errors="coerce"),
            "longitude": pd.to_numeric(cleaned[longitude_col], errors="coerce"),
        }
    ).dropna().drop_duplicates().reset_index(drop=True)


def _minimum_haversine_km(points: pd.DataFrame, candidates: pd.DataFrame) -> np.ndarray:
    if points.empty:
        return np.empty(0, dtype=float)
    if candidates.empty:
        return np.full(len(points), np.inf, dtype=float)
    lat1 = np.radians(points["latitude"].to_numpy(float))[:, None]
    lon1 = np.radians(points["longitude"].to_numpy(float))[:, None]
    lat2 = np.radians(candidates["latitude"].to_numpy(float))[None, :]
    lon2 = np.radians(candidates["longitude"].to_numpy(float))[None, :]
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    distance = 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
    return distance.min(axis=1)


def recovery_fraction(points: pd.DataFrame, candidates: pd.DataFrame, radius_km: float) -> float:
    if points.empty:
        return float("nan")
    return float(np.mean(_minimum_haversine_km(points, candidates) <= float(radius_km)))


def _random_seed(base_seed: int, species_key: int, country_code: str) -> int:
    token = f"{int(base_seed)}|{int(species_key)}|{str(country_code).upper()}".encode("utf-8")
    return int(hashlib.sha256(token).hexdigest()[:16], 16) % (2**32 - 1)


def same_size_random_recovery(
    recent: pd.DataFrame,
    surface: pd.DataFrame,
    *,
    selected_count: int,
    radius_km: float,
    repetitions: int,
    seed: int,
) -> tuple[float, float, float]:
    """Return mean, q2.5, q97.5 random recall on the exact candidate surface."""
    if recent.empty or selected_count <= 0:
        return float("nan"), float("nan"), float("nan")
    if selected_count > len(surface):
        raise ValueError("random baseline selected_count exceeds candidate surface")
    rng = np.random.default_rng(int(seed))
    values = np.empty(int(repetitions), dtype=float)
    for i in range(int(repetitions)):
        chosen = rng.choice(len(surface), size=int(selected_count), replace=False)
        values[i] = recovery_fraction(recent, surface.iloc[chosen], radius_km)
    return float(values.mean()), float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))


def taxon_bootstrap_mean_ci(values: np.ndarray, *, repetitions: int, seed: int) -> tuple[float, float, float]:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(int(seed))
    means = np.empty(int(repetitions), dtype=float)
    for i in range(int(repetitions)):
        means[i] = rng.choice(values, size=len(values), replace=True).mean()
    return float(values.mean()), float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def _finite_mean(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").to_numpy(float)
    values = values[np.isfinite(values)]
    return float(values.mean()) if values.size else float("nan")


def evaluate_frozen_declarations(declarations: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    protocol = _protocol()
    expected_taxa = int(protocol["development_gate"]["required_declared_taxa"])
    if len(declarations) != expected_taxa or declarations["speciesKey"].nunique() != expected_taxa:
        raise ValueError(f"stage-1 artifact must contain exactly {expected_taxa} unique taxa")

    outcome_cfg = protocol["outcome_evaluation"]
    radius_km = float(outcome_cfg["primary_recovery_radius_km"])
    if radius_km != float(VALIDATED_ROBUST_PRIMARY_RADIUS_KM) or radius_km != 10.0:
        raise ValueError("integration primary recovery radius drifted from frozen 10 km endpoint")
    repetitions = int(outcome_cfg["random_baseline_repetitions"])
    recent_years = tuple(int(x) for x in outcome_cfg["heldout_year_range"])
    recent_cap = int(outcome_cfg["heldout_max_coordinate_records_per_taxon_country"])
    random_seed_base = int(outcome_cfg["random_seed"])

    result_rows: list[dict[str, object]] = []
    patch_frames: list[pd.DataFrame] = []

    for row in declarations.itertuples(index=False):
        base = row._asdict()
        species_key = int(base["speciesKey"])
        country_code = str(base.get("selected_country_code") or "").upper()
        declaration_status = str(base.get("declaration_status") or "")
        candidate_status = "not_attempted_declaration_failed"
        candidate_failure_reason = ""
        temporal_status = "not_attempted_no_declared_country"
        temporal_failure_reason = ""
        occurrence_rows = recent_rows = surface_points = prototype_rows = candidate_patch_count = 0
        support_audit_json = "{}"
        robust_recall = random_mean = random_q025 = random_q975 = lift = float("nan")
        verified_geometry_sha = ""
        surface = pd.DataFrame()
        patches = pd.DataFrame()
        recent = pd.DataFrame(columns=["latitude", "longitude"])

        if declaration_status == "declared" and country_code:
            # Candidate generation is completed first, before any recent held-out
            # occurrence is requested. This ordering is deliberate even though
            # the algorithm is already frozen, so the execution trace cannot
            # be mistaken for outcome-informed candidate construction.
            try:
                geometry = fetch_geoboundaries_country_geometry(country_code)
                verified_geometry_sha = _geometry_digest_from_source_version(geometry.source_version)
                expected_geometry_sha = str(base.get("geometry_canonical_sha256") or "").lower()
                if verified_geometry_sha != expected_geometry_sha:
                    raise ValueError(
                        f"country geometry digest mismatch: declared={expected_geometry_sha}, refetched={verified_geometry_sha}"
                    )
                occurrences = fetch_country_occurrences(species_key, country_code)
                occurrence_rows = int(len(occurrences))
                surface, prototypes, _surface_seed = country_terrain_inputs(occurrences, geometry)
                surface_points = int(len(surface))
                prototype_rows = int(len(prototypes))
                if surface_points != 800:
                    raise ValueError(
                        f"frozen integration requires exactly 800 complete country surface points; got {surface_points}"
                    )
                patches, support_audit = validated_robust_candidate_patches(
                    surface,
                    prototypes,
                    feature_columns=ROBUST_TERRAIN_FEATURES,
                    area_col="survey_area_id",
                )
                candidate_patch_count = int(len(patches))
                support_audit_json = json.dumps(support_audit.as_dict(), sort_keys=True, separators=(",", ":"))
                if candidate_patch_count <= 0:
                    raise ValueError("frozen robust core returned zero candidate patches")
                candidate_status = "generated"
                patches = patches.copy()
                patches["integration_pair_id"] = int(base["integration_pair_id"])
                patches["speciesKey"] = species_key
                patches["scientific_name"] = str(base["scientific_name"])
                patches["taxon_group"] = str(base["taxon_group"])
                patches["framing_country_code"] = country_code
                patch_frames.append(patches)
            except Exception as exc:
                candidate_status = "candidate_generation_failed"
                candidate_failure_reason = f"{type(exc).__name__}: {exc}"

            # Temporal evaluability is measured independently after candidate
            # construction has either succeeded or failed. Candidate failures do
            # not suppress recent-outcome accounting for the frozen country.
            try:
                recent = fetch_recent_country_occurrences(
                    species_key,
                    country_code,
                    years=recent_years,
                    cap=recent_cap,
                )
                recent_rows = int(len(recent))
                temporal_status = "evaluated" if recent_rows > 0 else "zero_recent_country_records"
            except Exception as exc:
                temporal_status = "recent_provider_failed"
                temporal_failure_reason = f"{type(exc).__name__}: {exc}"

            if candidate_status == "generated" and temporal_status == "evaluated":
                robust_recall = recovery_fraction(recent, patches, radius_km)
                seed = _random_seed(random_seed_base, species_key, country_code)
                random_mean, random_q025, random_q975 = same_size_random_recovery(
                    recent,
                    surface,
                    selected_count=candidate_patch_count,
                    radius_km=radius_km,
                    repetitions=repetitions,
                    seed=seed,
                )
                lift = float(robust_recall - random_mean)

        result_rows.append(
            {
                **base,
                "candidate_generation_status": candidate_status,
                "candidate_generation_failure_reason": candidate_failure_reason,
                "temporal_status": temporal_status,
                "temporal_failure_reason": temporal_failure_reason,
                "historical_training_occurrence_rows": occurrence_rows,
                "recent_heldout_occurrence_rows": recent_rows,
                "country_surface_points": surface_points,
                "prototype_rows": prototype_rows,
                "candidate_patch_count": candidate_patch_count,
                "verified_geometry_canonical_sha256": verified_geometry_sha,
                "primary_radius_km": radius_km,
                "robust_recall": robust_recall,
                "random_recall_mean": random_mean,
                "random_recall_q025": random_q025,
                "random_recall_q975": random_q975,
                "robust_minus_random_recall": lift,
                "support_audit_json": support_audit_json,
            }
        )

    results = pd.DataFrame(result_rows)
    all_patches = pd.concat(patch_frames, ignore_index=True) if patch_frames else pd.DataFrame()

    candidate_success = results["candidate_generation_status"].eq("generated")
    temporal_evaluable = results["temporal_status"].eq("evaluated")
    integrated = candidate_success & temporal_evaluable & pd.to_numeric(
        results["robust_minus_random_recall"], errors="coerce"
    ).notna()
    lifts = pd.to_numeric(results.loc[integrated, "robust_minus_random_recall"], errors="coerce").to_numpy(float)
    gate_cfg = protocol["development_gate"]
    mean_lift, ci_low, ci_high = taxon_bootstrap_mean_ci(
        lifts,
        repetitions=int(gate_cfg["bootstrap_repetitions"]),
        seed=int(gate_cfg["bootstrap_seed"]),
    )
    plant_mean = _finite_mean(results.loc[integrated & results["taxon_group"].eq("plant"), "robust_minus_random_recall"])
    animal_mean = _finite_mean(results.loc[integrated & results["taxon_group"].eq("animal"), "robust_minus_random_recall"])
    candidate_rate = float(candidate_success.mean())
    temporal_rate = float(temporal_evaluable.mean())

    gate_checks = {
        "declared_taxa": int(len(results)) == int(gate_cfg["required_declared_taxa"]),
        "candidate_generation_success_rate": candidate_rate >= float(gate_cfg["candidate_generation_success_rate_min"]),
        "temporal_evaluability_rate": temporal_rate >= float(gate_cfg["temporal_evaluability_rate_min"]),
        "mean_lift_positive": bool(np.isfinite(mean_lift) and mean_lift > 0.0),
        "bootstrap_lower_positive": bool(np.isfinite(ci_low) and ci_low > 0.0),
        "plant_mean_nonnegative": bool(np.isfinite(plant_mean) and plant_mean >= float(gate_cfg["plant_mean_lift_min"])),
        "animal_mean_nonnegative": bool(np.isfinite(animal_mean) and animal_mean >= float(gate_cfg["animal_mean_lift_min"])),
    }
    summary: dict[str, object] = {
        "status": "country_framed_robust_integration_development_v1_complete",
        "protocol_fingerprint": EXPECTED_PROTOCOL_FINGERPRINT,
        "declared_taxa": int(len(results)),
        "candidate_generation_success_taxa": int(candidate_success.sum()),
        "candidate_generation_success_rate": candidate_rate,
        "temporally_evaluable_taxa": int(temporal_evaluable.sum()),
        "temporal_evaluability_rate": temporal_rate,
        "integrated_evaluable_taxa": int(integrated.sum()),
        "primary_support_fraction": float(VALIDATED_ROBUST_SUPPORT_FRACTION),
        "primary_radius_km": radius_km,
        "random_baseline_repetitions": repetitions,
        "mean_robust_minus_random_recall": mean_lift,
        "taxon_bootstrap_95pct_ci": [ci_low, ci_high],
        "plant_mean_robust_minus_random_recall": plant_mean,
        "animal_mean_robust_minus_random_recall": animal_mean,
        "gate_checks": gate_checks,
        "development_gate_passed": bool(all(gate_checks.values())),
        "candidate_generation_preceded_recent_outcome_fetch": True,
        "retuned_after_outcome_opening": False,
        "country_representation_changed": False,
        "country_geometry_provider_changed": False,
        "robust_core_changed": False,
        "confirmation_v1_taxa_consumed": False,
        "development_only": True,
        "global_candidate_generation_validated": False,
    }
    return results, all_patches, summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--declarations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    declarations = pd.read_csv(args.declarations)
    results, patches, summary = evaluate_frozen_declarations(declarations)
    results.to_csv(args.output / "taxon_country_results.csv", index=False)
    patches.to_csv(args.output / "integrated_candidate_patches.csv", index=False)
    (args.output / "development_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
