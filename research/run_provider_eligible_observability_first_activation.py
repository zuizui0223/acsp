#!/usr/bin/env python3
"""Execute the frozen issue #169 first activation as five explicit pre-heldout stages.

This module is inert on import. Network providers are called only by stage1,
stage2, or stage4 when the dedicated main-marker workflow invokes them.
No 2021--2025 occurrence/facet endpoint, candidate patch, robust world, random
baseline, recall, or lift code is imported or executed here.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import shutil
from typing import Any, Sequence

import pandas as pd

from benchmark_general_random_taxa_regions import REGION_CELLS, TAXON_GROUPS, taxon_frame
from geographic_framing_country_registry_v3 import HISTORICAL_YEARS, fetch_country_facet_counts
from geoboundaries_v6_coverage_contract import require_supported_alpha2
from geoboundaries_v6_provider import (
    GEOBOUNDARIES_RELEASE_COMMIT,
    GEOBOUNDARIES_SOURCE_ID,
    fetch_geoboundaries_country_geometry,
)
from predeclare_country_framed_integration_development_v1 import (
    _geometry_digest_from_source_version,
    choose_historical_country,
)
import predeclare_provider_eligible_observability_confirmation as prereg


GROUP_ORDER = ("plant", "animal")
STAGE1_CSV = "candidate_snapshot.csv"
STAGE1_MANIFEST = "stage1_manifest.json"
STAGE2_CSV = "eligibility_snapshot.csv"
STAGE2_PARTIAL_CSV = "eligibility_snapshot_partial.csv"
STAGE2_MANIFEST = "stage2_manifest.json"
STAGE3_CSV = "final_selection.csv"
STAGE3_MANIFEST = "stage3_manifest.json"
STAGE4_CSV = "frozen_frames.csv"
STAGE4_PARTIAL_CSV = "frozen_frames_partial.csv"
STAGE4_MANIFEST = "stage4_manifest.json"
FINAL_FRAMES_CSV = "predeclared_observability_frames.csv"
FINAL_AUDIT_CSV = "pre_freeze_declaration_attempts.csv"
FINAL_CANDIDATES_CSV = "candidate_snapshot.csv"
FINAL_MANIFEST = "cohort_manifest.json"
EXPECTED_PREREG_MERGE_COMMIT = "91ff432e3da7cf3b26efa16a5c60219715feff89"
HISTORICAL_WORKERS = 16
GEOMETRY_WORKERS = 8


class FirstActivationAborted(RuntimeError):
    """Frozen first activation ended before a complete authoritative cohort existed."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _base_manifest(stage: int, status: str) -> dict[str, Any]:
    cfg = prereg.protocol()
    execution = prereg.execution_contract()
    exclusions = prereg.exclusion_provenance()
    return {
        "stage": int(stage),
        "status": str(status),
        "parent_issue": 169,
        "protocol_fingerprint": cfg["protocol_fingerprint"],
        "execution_contract_fingerprint": execution["execution_contract_fingerprint"],
        "coverage_contract_fingerprint": prereg.EXPECTED_COVERAGE_FINGERPRINT,
        "exclusion_provenance_fingerprint": exclusions["exclusion_provenance_fingerprint"],
        "preregistration_merge_commit": EXPECTED_PREREG_MERGE_COMMIT,
        "heldout_2021_2025_opened": False,
        "candidate_generation_run": False,
        "robust_support_run": False,
        "random_baseline_run": False,
        "recall_or_lift_read": False,
        "score_cutoff_selected": False,
        "outcome_driven_tuning": False,
    }


def _normalize_identity_frame(path: Path) -> tuple[set[int], set[str]]:
    frame = pd.read_csv(path)
    lower = {str(column).lower(): str(column) for column in frame.columns}
    key_col = lower.get("specieskey") or lower.get("species_key")
    name_col = lower.get("scientific_name") or lower.get("scientificname")
    keys: set[int] = set()
    names: set[str] = set()
    if key_col:
        values = pd.to_numeric(frame[key_col], errors="coerce").dropna()
        keys.update(int(x) for x in values.astype(int))
    if name_col:
        names.update(
            value
            for value in frame[name_col].astype(str).str.strip()
            if value and value.lower() != "nan"
        )
    return keys, names


def consumed_exclusion_sets() -> tuple[set[int], set[str]]:
    """Load identities only from the 12 byte-pinned consumed sources."""
    manifest = prereg.exclusion_provenance()
    keys: set[int] = set()
    names: set[str] = set()
    for item in manifest["files"]:
        path = prereg.ROOT / str(item["path"])
        file_keys, file_names = _normalize_identity_frame(path)
        keys.update(file_keys)
        names.update(file_names)
    return keys, names


def _normalize_discovery_frame(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"speciesKey", "scientific_name", "coordinate_records"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"fresh discovery frame missing columns: {sorted(missing)}")
    work = frame.copy()
    work["speciesKey"] = pd.to_numeric(work["speciesKey"], errors="raise").astype(int)
    work["scientific_name"] = work["scientific_name"].astype(str).str.strip()
    work["coordinate_records"] = pd.to_numeric(
        work["coordinate_records"], errors="raise"
    ).astype(int)
    return work.drop_duplicates(["speciesKey", "scientific_name"]).copy()


def build_candidate_snapshot(frame_provider=taxon_frame) -> pd.DataFrame:
    """Stage 1: discover and stratify all candidates without focal historical queries."""
    cfg = prereg.protocol()
    cohort = cfg["cohort"]
    if len(REGION_CELLS) != int(cohort["regions"]):
        raise ValueError("fixed discovery-region count drift")
    excluded_keys, excluded_names = consumed_exclusion_sets()
    prefixes = tuple(str(x) for x in cfg["exclusions"]["explicit_prefixes"])
    rows: list[dict[str, Any]] = []

    for region_index, cell in enumerate(REGION_CELLS, start=1):
        geographic_stratum, region_name, west, south, east, north = cell
        bounds = (float(west), float(south), float(east), float(north))
        for group in GROUP_ORDER:
            raw = frame_provider(
                bounds,
                int(TAXON_GROUPS[group]),
                int(cohort["facet_limit"]),
                int(cohort["minimum_records"]),
            )
            frame = _normalize_discovery_frame(raw)
            frame = frame[
                ~frame["speciesKey"].isin(excluded_keys)
                & ~frame["scientific_name"].isin(excluded_names)
                & ~frame["scientific_name"].str.startswith(prefixes)
            ].copy()
            if len(frame) < 4:
                raise FirstActivationAborted(
                    f"stage1 fewer than four exclusion-filtered candidates "
                    f"for region={region_index}, group={group}"
                )
            frame["record_count_stratum"] = pd.qcut(
                frame["coordinate_records"].rank(method="first"),
                4,
                labels=False,
            ).astype(int)
            for row in frame.itertuples(index=False):
                rows.append(
                    {
                        "region_cell_index": int(region_index),
                        "geographic_stratum": str(geographic_stratum),
                        "region_name": str(region_name),
                        "west": float(west),
                        "south": float(south),
                        "east": float(east),
                        "north": float(north),
                        "taxon_group": str(group),
                        "record_count_stratum": int(row.record_count_stratum),
                        "speciesKey": int(row.speciesKey),
                        "scientific_name": str(row.scientific_name),
                        "coordinate_records": int(row.coordinate_records),
                    }
                )
    snapshot = pd.DataFrame(rows)
    if snapshot.empty:
        raise FirstActivationAborted("stage1 candidate snapshot is empty")
    for region in range(1, 13):
        for group in GROUP_ORDER:
            sub = snapshot[
                snapshot["region_cell_index"].eq(region)
                & snapshot["taxon_group"].eq(group)
            ]
            if set(sub["record_count_stratum"].astype(int)) != {0, 1, 2, 3}:
                raise FirstActivationAborted(
                    f"stage1 missing required stratum for region={region}, group={group}"
                )
    snapshot["_group_order"] = snapshot["taxon_group"].map({"plant": 0, "animal": 1})
    snapshot = snapshot.sort_values(
        ["region_cell_index", "_group_order", "record_count_stratum", "speciesKey", "scientific_name"],
        kind="mergesort",
    ).drop(columns=["_group_order"])
    return snapshot.reset_index(drop=True)


def run_stage1(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        snapshot = build_candidate_snapshot()
    except Exception as exc:
        manifest = _base_manifest(1, "abort_not_evaluable")
        manifest["abort_reason"] = f"{type(exc).__name__}: {exc}"
        manifest["fresh_candidate_identities_opened"] = True
        manifest["focal_species_historical_facets_opened"] = False
        _write_json(output_dir / STAGE1_MANIFEST, manifest)
        raise FirstActivationAborted(str(exc)) from exc

    path = output_dir / STAGE1_CSV
    snapshot.to_csv(path, index=False)
    manifest = _base_manifest(1, "complete_candidate_discovery_snapshot")
    manifest.update(
        {
            "candidate_rows": int(len(snapshot)),
            "unique_species_keys": int(snapshot["speciesKey"].nunique()),
            "candidate_snapshot_sha256": _sha256_file(path),
            "fresh_candidate_identities_opened": True,
            "focal_species_historical_facets_opened": False,
            "selection_occurs": False,
        }
    )
    _write_json(output_dir / STAGE1_MANIFEST, manifest)
    return manifest


def _verify_stage1(stage1_dir: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    manifest = _read_json(stage1_dir / STAGE1_MANIFEST)
    if manifest.get("status") != "complete_candidate_discovery_snapshot":
        raise FirstActivationAborted("stage1 is not complete")
    if manifest.get("protocol_fingerprint") != prereg.EXPECTED_PROTOCOL_FINGERPRINT:
        raise FirstActivationAborted("stage1 protocol fingerprint drift")
    if manifest.get("execution_contract_fingerprint") != prereg.EXPECTED_EXECUTION_FINGERPRINT:
        raise FirstActivationAborted("stage1 execution fingerprint drift")
    if manifest.get("coverage_contract_fingerprint") != prereg.EXPECTED_COVERAGE_FINGERPRINT:
        raise FirstActivationAborted("stage1 coverage fingerprint drift")
    if manifest.get("exclusion_provenance_fingerprint") != prereg.EXPECTED_EXCLUSION_FINGERPRINT:
        raise FirstActivationAborted("stage1 exclusion fingerprint drift")
    path = stage1_dir / STAGE1_CSV
    if _sha256_file(path) != manifest.get("candidate_snapshot_sha256"):
        raise FirstActivationAborted("stage1 candidate snapshot byte hash drift")
    frame = pd.read_csv(path)
    if len(frame) != int(manifest["candidate_rows"]):
        raise FirstActivationAborted("stage1 candidate row-count drift")
    return frame, manifest


def _historical_query_result(species_key: int) -> dict[str, Any]:
    try:
        counts = dict(
            sorted(
                (str(code).upper(), int(count))
                for code, count in fetch_country_facet_counts(
                    int(species_key), HISTORICAL_YEARS
                ).items()
            )
        )
        return {"speciesKey": int(species_key), "counts": counts, "error": ""}
    except Exception as exc:
        return {
            "speciesKey": int(species_key),
            "counts": {},
            "error": f"{type(exc).__name__}: {exc}",
        }


def build_eligibility_snapshot(
    candidate_snapshot: pd.DataFrame,
    historical_results: dict[int, dict[str, Any]],
) -> pd.DataFrame:
    """Pure expansion of historical results into a complete candidate audit."""
    cfg = prereg.protocol()
    minimum = int(cfg["country_declaration"]["historical_country_min_count"])
    country_seed = int(cfg["country_declaration"]["country_selection_seed"])
    rows: list[dict[str, Any]] = []

    for raw in candidate_snapshot.to_dict(orient="records"):
        row = dict(raw)
        key = int(row["speciesKey"])
        result = historical_results[key]
        error = str(result.get("error", ""))
        if error:
            rows.append(
                {
                    **row,
                    "selected_country_code": "",
                    "selected_country_alpha3": "",
                    "country_selection_basis": "",
                    "historical_selected_country_count": 0,
                    "country_frame_observability_score": math.nan,
                    "provider_eligible": False,
                    "eligibility_status": "historical_provider_error_abort",
                    "historical_country_counts_json": "{}",
                    "failure_reason": error,
                }
            )
            continue

        counts = {
            str(code).upper(): int(count)
            for code, count in dict(result["counts"]).items()
        }
        country, basis = choose_historical_country(
            counts,
            species_key=key,
            minimum_count=minimum,
            seed=country_seed,
        )
        counts_json = json.dumps(counts, sort_keys=True, separators=(",", ":"))
        if country is None:
            rows.append(
                {
                    **row,
                    "selected_country_code": "",
                    "selected_country_alpha3": "",
                    "country_selection_basis": str(basis),
                    "historical_selected_country_count": 0,
                    "country_frame_observability_score": math.nan,
                    "provider_eligible": False,
                    "eligibility_status": "preselection_ineligible_no_historical_country",
                    "historical_country_counts_json": counts_json,
                    "failure_reason": "",
                }
            )
            continue

        count = int(counts[country])
        eligible, alpha3, status = prereg.provider_eligibility(country)
        rows.append(
            {
                **row,
                "selected_country_code": str(country),
                "selected_country_alpha3": str(alpha3 or ""),
                "country_selection_basis": str(basis),
                "historical_selected_country_count": count,
                "country_frame_observability_score": prereg.observability_score(count),
                "provider_eligible": bool(eligible),
                "eligibility_status": str(status),
                "historical_country_counts_json": counts_json,
                "failure_reason": "",
            }
        )
    return pd.DataFrame(rows)


def run_stage2(stage1_dir: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates, stage1_manifest = _verify_stage1(stage1_dir)
    keys = sorted(set(pd.to_numeric(candidates["speciesKey"], errors="raise").astype(int)))
    with ThreadPoolExecutor(max_workers=HISTORICAL_WORKERS) as executor:
        results_list = list(executor.map(_historical_query_result, keys))
    results = {int(item["speciesKey"]): item for item in results_list}
    audit = build_eligibility_snapshot(candidates, results)
    errors = [item for item in results_list if item["error"]]
    path = output_dir / (STAGE2_PARTIAL_CSV if errors else STAGE2_CSV)
    audit.to_csv(path, index=False)

    if errors:
        manifest = _base_manifest(2, "abort_not_evaluable")
        manifest.update(
            {
                "stage1_candidate_snapshot_sha256": stage1_manifest["candidate_snapshot_sha256"],
                "eligibility_audit_file": path.name,
                "eligibility_audit_sha256": _sha256_file(path),
                "candidate_rows": int(len(audit)),
                "historical_unique_species_queries": int(len(keys)),
                "historical_provider_error_count": int(len(errors)),
                "failure_species_keys": [int(item["speciesKey"]) for item in errors],
                "focal_species_historical_facets_opened": True,
                "selection_occurs": False,
                "abort_reason": "one or more historical provider queries failed",
            }
        )
        _write_json(output_dir / STAGE2_MANIFEST, manifest)
        raise FirstActivationAborted("stage2 historical provider error; activation aborted")

    manifest = _base_manifest(2, "complete_historical_provider_eligibility_snapshot")
    manifest.update(
        {
            "stage1_candidate_snapshot_sha256": stage1_manifest["candidate_snapshot_sha256"],
            "eligibility_snapshot_sha256": _sha256_file(path),
            "candidate_rows": int(len(audit)),
            "historical_unique_species_queries": int(len(keys)),
            "provider_eligible_rows": int(audit["provider_eligible"].astype(bool).sum()),
            "no_historical_country_rows": int(
                audit["eligibility_status"]
                .eq("preselection_ineligible_no_historical_country")
                .sum()
            ),
            "provider_ineligible_rows": int(
                audit["eligibility_status"]
                .eq("preselection_ineligible_provider_coverage")
                .sum()
            ),
            "focal_species_historical_facets_opened": True,
            "selection_occurs": False,
        }
    )
    _write_json(output_dir / STAGE2_MANIFEST, manifest)
    return manifest


def _verify_stage2(stage2_dir: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    manifest = _read_json(stage2_dir / STAGE2_MANIFEST)
    if manifest.get("status") != "complete_historical_provider_eligibility_snapshot":
        raise FirstActivationAborted("stage2 is not complete")
    path = stage2_dir / STAGE2_CSV
    if _sha256_file(path) != manifest.get("eligibility_snapshot_sha256"):
        raise FirstActivationAborted("stage2 eligibility snapshot byte hash drift")
    frame = pd.read_csv(path)
    if len(frame) != int(manifest["candidate_rows"]):
        raise FirstActivationAborted("stage2 candidate row-count drift")
    if frame["eligibility_status"].eq("historical_provider_error_abort").any():
        raise FirstActivationAborted("stage2 contains historical provider error rows")
    return frame, manifest


def select_final_96(eligibility_snapshot: pd.DataFrame) -> pd.DataFrame:
    records = eligibility_snapshot.to_dict(orient="records")
    selected: list[dict[str, Any]] = []
    for region in range(1, 13):
        for group in GROUP_ORDER:
            for stratum in range(4):
                chosen = prereg.select_final_eligible(
                    records,
                    region=region,
                    group=group,
                    stratum=stratum,
                )
                selected.append(dict(chosen))
    frame = pd.DataFrame(selected)
    if len(frame) != 96:
        raise FirstActivationAborted("stage3 did not select exactly 96 frames")
    if frame["speciesKey"].nunique() != 96 or frame["scientific_name"].nunique() != 96:
        raise FirstActivationAborted(
            "stage3 hash-min selections are not 96 unique identities; no collision repair is allowed"
        )
    if frame["taxon_group"].value_counts().to_dict() != {"plant": 48, "animal": 48}:
        raise FirstActivationAborted("stage3 plant/animal balance drift")
    for group in GROUP_ORDER:
        counts = (
            frame.loc[frame["taxon_group"].eq(group), "record_count_stratum"]
            .astype(int)
            .value_counts()
            .sort_index()
            .to_dict()
        )
        if counts != {0: 12, 1: 12, 2: 12, 3: 12}:
            raise FirstActivationAborted(f"stage3 stratum balance drift for {group}")
    per_cell = frame.groupby(["region_cell_index", "taxon_group"]).size()
    if len(per_cell) != 24 or not bool((per_cell == 4).all()):
        raise FirstActivationAborted("stage3 region-group cell balance drift")
    if not bool(frame["provider_eligible"].astype(bool).all()):
        raise FirstActivationAborted("stage3 selected an ineligible candidate")
    return frame.reset_index(drop=True)


def run_stage3(stage2_dir: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    eligibility, stage2_manifest = _verify_stage2(stage2_dir)
    try:
        selected = select_final_96(eligibility)
    except Exception as exc:
        manifest = _base_manifest(3, "abort_not_evaluable")
        manifest.update(
            {
                "stage2_eligibility_snapshot_sha256": stage2_manifest[
                    "eligibility_snapshot_sha256"
                ],
                "network_allowed": False,
                "post_selection_replacement_allowed": False,
                "abort_reason": f"{type(exc).__name__}: {exc}",
            }
        )
        _write_json(output_dir / STAGE3_MANIFEST, manifest)
        raise FirstActivationAborted(str(exc)) from exc

    path = output_dir / STAGE3_CSV
    selected.to_csv(path, index=False)
    manifest = _base_manifest(3, "complete_final_96_offline_selection")
    manifest.update(
        {
            "stage2_eligibility_snapshot_sha256": stage2_manifest[
                "eligibility_snapshot_sha256"
            ],
            "final_selection_sha256": _sha256_file(path),
            "selected_frames": 96,
            "unique_species_keys": 96,
            "network_allowed": False,
            "post_selection_replacement_allowed": False,
            "historical_count_used_for_ranking": False,
            "score_used_for_ranking": False,
        }
    )
    _write_json(output_dir / STAGE3_MANIFEST, manifest)
    return manifest


def _verify_stage3(stage3_dir: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    manifest = _read_json(stage3_dir / STAGE3_MANIFEST)
    if manifest.get("status") != "complete_final_96_offline_selection":
        raise FirstActivationAborted("stage3 is not complete")
    path = stage3_dir / STAGE3_CSV
    if _sha256_file(path) != manifest.get("final_selection_sha256"):
        raise FirstActivationAborted("stage3 final-selection byte hash drift")
    frame = pd.read_csv(path)
    if len(frame) != 96 or frame["speciesKey"].nunique() != 96:
        raise FirstActivationAborted("stage3 final-selection structure drift")
    return frame, manifest


def _geometry_query(country_code: str) -> dict[str, Any]:
    code = str(country_code).upper()
    try:
        alpha3 = require_supported_alpha2(code)
        geom = fetch_geoboundaries_country_geometry(code)
        if str(geom.country_code).upper() != code:
            raise ValueError("geometry country code drift")
        if geom.source_id != GEOBOUNDARIES_SOURCE_ID:
            raise ValueError("geometry source id drift")
        if GEOBOUNDARIES_RELEASE_COMMIT not in str(geom.source_version):
            raise ValueError("geometry release commit drift")
        if f"iso3={alpha3}" not in str(geom.source_version):
            raise ValueError("geometry source-version alpha3 drift")
        digest = _geometry_digest_from_source_version(str(geom.source_version))
        return {
            "country_code": code,
            "alpha3": alpha3,
            "source_id": str(geom.source_id),
            "source_version": str(geom.source_version),
            "canonical_sha256": str(digest),
            "error": "",
        }
    except Exception as exc:
        return {
            "country_code": code,
            "alpha3": "",
            "source_id": "",
            "source_version": "",
            "canonical_sha256": "",
            "error": f"{type(exc).__name__}: {exc}",
        }


def attach_geometry(
    final_selection: pd.DataFrame,
    geometry_results: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for raw in final_selection.to_dict(orient="records"):
        row = dict(raw)
        country = str(row["selected_country_code"]).upper()
        result = geometry_results[country]
        row.update(
            {
                "geometry_source_id": str(result.get("source_id", "")),
                "geometry_source_version": str(result.get("source_version", "")),
                "geometry_canonical_sha256": str(result.get("canonical_sha256", "")),
                "geometry_failure_reason": str(result.get("error", "")),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def run_stage4(stage3_dir: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    selected, stage3_manifest = _verify_stage3(stage3_dir)
    countries = sorted(set(selected["selected_country_code"].astype(str).str.upper()))
    with ThreadPoolExecutor(max_workers=GEOMETRY_WORKERS) as executor:
        results_list = list(executor.map(_geometry_query, countries))
    results = {str(item["country_code"]): item for item in results_list}
    frozen = attach_geometry(selected, results)
    errors = [item for item in results_list if item["error"]]
    path = output_dir / (STAGE4_PARTIAL_CSV if errors else STAGE4_CSV)
    frozen.to_csv(path, index=False)

    if errors:
        manifest = _base_manifest(4, "abort_not_evaluable")
        manifest.update(
            {
                "stage3_final_selection_sha256": stage3_manifest["final_selection_sha256"],
                "frozen_frames_file": path.name,
                "frozen_frames_sha256": _sha256_file(path),
                "geometry_country_queries": int(len(countries)),
                "geometry_provider_error_count": int(len(errors)),
                "failure_country_codes": [str(item["country_code"]) for item in errors],
                "country_substitution_allowed": False,
                "alternate_provider_allowed": False,
                "post_selection_replacement_allowed": False,
                "abort_reason": "one or more pinned geometry fetches failed",
            }
        )
        _write_json(output_dir / STAGE4_MANIFEST, manifest)
        raise FirstActivationAborted("stage4 pinned geometry failure; activation aborted")

    if frozen["geometry_failure_reason"].astype(str).str.len().gt(0).any():
        raise FirstActivationAborted("stage4 unexpected geometry failure row")
    manifest = _base_manifest(4, "complete_pinned_geometry_freeze")
    manifest.update(
        {
            "stage3_final_selection_sha256": stage3_manifest["final_selection_sha256"],
            "frozen_frames_sha256": _sha256_file(path),
            "frozen_frames": 96,
            "geometry_country_queries": int(len(countries)),
            "geometry_provider_release_commit": GEOBOUNDARIES_RELEASE_COMMIT,
            "geometry_provider_source_id": GEOBOUNDARIES_SOURCE_ID,
            "country_substitution_allowed": False,
            "alternate_provider_allowed": False,
            "post_selection_replacement_allowed": False,
        }
    )
    _write_json(output_dir / STAGE4_MANIFEST, manifest)
    return manifest


def _verify_stage4(stage4_dir: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    manifest = _read_json(stage4_dir / STAGE4_MANIFEST)
    if manifest.get("status") != "complete_pinned_geometry_freeze":
        raise FirstActivationAborted("stage4 is not complete")
    path = stage4_dir / STAGE4_CSV
    if _sha256_file(path) != manifest.get("frozen_frames_sha256"):
        raise FirstActivationAborted("stage4 frozen-frame byte hash drift")
    frame = pd.read_csv(path)
    if len(frame) != 96 or frame["speciesKey"].nunique() != 96:
        raise FirstActivationAborted("stage4 frozen-frame structure drift")
    return frame, manifest


def run_stage5(
    stage1_dir: Path,
    stage2_dir: Path,
    stage3_dir: Path,
    stage4_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates, m1 = _verify_stage1(stage1_dir)
    eligibility, m2 = _verify_stage2(stage2_dir)
    _, m3 = _verify_stage3(stage3_dir)
    frozen, m4 = _verify_stage4(stage4_dir)

    if m2["stage1_candidate_snapshot_sha256"] != m1["candidate_snapshot_sha256"]:
        raise FirstActivationAborted("stage1 -> stage2 byte binding drift")
    if m3["stage2_eligibility_snapshot_sha256"] != m2["eligibility_snapshot_sha256"]:
        raise FirstActivationAborted("stage2 -> stage3 byte binding drift")
    if m4["stage3_final_selection_sha256"] != m3["final_selection_sha256"]:
        raise FirstActivationAborted("stage3 -> stage4 byte binding drift")

    final_frames = output_dir / FINAL_FRAMES_CSV
    final_audit = output_dir / FINAL_AUDIT_CSV
    final_candidates = output_dir / FINAL_CANDIDATES_CSV
    frozen.to_csv(final_frames, index=False)
    eligibility.to_csv(final_audit, index=False)
    candidates.to_csv(final_candidates, index=False)
    shutil.copy2(stage1_dir / STAGE1_MANIFEST, output_dir / STAGE1_MANIFEST)
    shutil.copy2(stage2_dir / STAGE2_MANIFEST, output_dir / STAGE2_MANIFEST)
    shutil.copy2(stage3_dir / STAGE3_MANIFEST, output_dir / STAGE3_MANIFEST)
    shutil.copy2(stage4_dir / STAGE4_MANIFEST, output_dir / STAGE4_MANIFEST)

    cfg = prereg.protocol()
    manifest = _base_manifest(
        5, "provider_eligible_observability_96_frames_frozen_before_heldout"
    )
    manifest.update(
        {
            "frozen_frames": 96,
            "unique_species_keys": 96,
            "plant_frames": 48,
            "animal_frames": 48,
            "selection_seed": int(cfg["cohort"]["selection_seed"]),
            "score_formula": str(cfg["country_declaration"]["score_formula"]),
            "frames_csv_sha256": _sha256_file(final_frames),
            "candidate_snapshot_sha256": _sha256_file(final_candidates),
            "eligibility_audit_sha256": _sha256_file(final_audit),
            "stage1_manifest_sha256": _sha256_file(output_dir / STAGE1_MANIFEST),
            "stage2_manifest_sha256": _sha256_file(output_dir / STAGE2_MANIFEST),
            "stage3_manifest_sha256": _sha256_file(output_dir / STAGE3_MANIFEST),
            "stage4_manifest_sha256": _sha256_file(output_dir / STAGE4_MANIFEST),
            "heldout_opened": False,
            "second_activation_allowed_only_if_success": True,
            "replacement_after_final_selection_allowed": False,
            "country_substitution_allowed": False,
            "alternate_geometry_provider_allowed": False,
        }
    )
    _write_json(output_dir / FINAL_MANIFEST, manifest)
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="stage", required=True)

    one = sub.add_parser("stage1")
    one.add_argument("--output-dir", type=Path, required=True)

    two = sub.add_parser("stage2")
    two.add_argument("--stage1-dir", type=Path, required=True)
    two.add_argument("--output-dir", type=Path, required=True)

    three = sub.add_parser("stage3")
    three.add_argument("--stage2-dir", type=Path, required=True)
    three.add_argument("--output-dir", type=Path, required=True)

    four = sub.add_parser("stage4")
    four.add_argument("--stage3-dir", type=Path, required=True)
    four.add_argument("--output-dir", type=Path, required=True)

    five = sub.add_parser("stage5")
    five.add_argument("--stage1-dir", type=Path, required=True)
    five.add_argument("--stage2-dir", type=Path, required=True)
    five.add_argument("--stage3-dir", type=Path, required=True)
    five.add_argument("--stage4-dir", type=Path, required=True)
    five.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.stage == "stage1":
            result = run_stage1(args.output_dir)
        elif args.stage == "stage2":
            result = run_stage2(args.stage1_dir, args.output_dir)
        elif args.stage == "stage3":
            result = run_stage3(args.stage2_dir, args.output_dir)
        elif args.stage == "stage4":
            result = run_stage4(args.stage3_dir, args.output_dir)
        elif args.stage == "stage5":
            result = run_stage5(
                args.stage1_dir,
                args.stage2_dir,
                args.stage3_dir,
                args.stage4_dir,
                args.output_dir,
            )
        else:
            raise AssertionError(args.stage)
    except FirstActivationAborted as exc:
        print(
            json.dumps(
                {
                    "status": "abort_not_evaluable",
                    "stage": args.stage,
                    "reason": str(exc),
                    "heldout_2021_2025_opened": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
