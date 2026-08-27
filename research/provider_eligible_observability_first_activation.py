#!/usr/bin/env python3
"""First pre-heldout activation runner for the provider-eligible confirmation.

The scientific contract was frozen in PR #171 before any new candidate identity.
This module implements the frozen stage separation. Importing it performs no
network access. Live GBIF/geoBoundaries calls occur only when the explicit
stage CLI is invoked by the dedicated one-shot activation workflow.

No function in this module fetches or evaluates 2021--2025 data.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import pandas as pd

from acsp.benchmarking import get_json
from benchmark_general_random_taxa_regions import (
    GBIF_SEARCH,
    GBIF_SPECIES,
    REGION_CELLS,
    TAXON_GROUPS,
    rectangle_wkt,
)
from geographic_framing_country_registry_v3 import HISTORICAL_YEARS, fetch_country_facet_counts
from geoboundaries_v6_coverage_contract import load_contract as load_coverage_contract, load_iso_mapping
from geoboundaries_v6_provider import (
    GEOBOUNDARIES_RELEASE_COMMIT,
    GEOBOUNDARIES_RELEASE_TAG,
    GEOBOUNDARIES_SOURCE_ID,
    fetch_geoboundaries_country_geometry,
)
from predeclare_country_framed_integration_development_v1 import (
    _geometry_digest_from_source_version,
    choose_historical_country,
)
from predeclare_provider_eligible_observability_confirmation import (
    EXPECTED_COVERAGE_FINGERPRINT,
    EXPECTED_EXECUTION_FINGERPRINT,
    EXPECTED_EXCLUSION_FINGERPRINT,
    EXPECTED_PROTOCOL_FINGERPRINT,
    exclusion_provenance,
    identity_hash,
    observability_score,
    protocol,
    validate_static_preregistration,
)

ROOT = Path(__file__).resolve().parents[1]
GROUP_ORDER = ("plant", "animal")
PREREGISTRATION_MERGE_COMMIT = "91ff432e3da7cf3b26efa16a5c60219715feff89"
FIRST_ACTIVATION_MARKER = (
    ROOT / "validation" / "activate_provider_eligible_observability_confirmation_first.marker"
)
STAGE1_CSV = "stage1_candidate_snapshot.csv"
STAGE1_MANIFEST = "stage1_candidate_snapshot_manifest.json"
STAGE2_CSV = "stage2_historical_provider_eligibility_snapshot.csv"
STAGE2_MANIFEST = "stage2_historical_provider_eligibility_manifest.json"
STAGE3_CSV = "stage3_final_96_pregeometry.csv"
STAGE3_AUDIT = "stage3_offline_selection_audit.csv"
STAGE3_MANIFEST = "stage3_final_96_pregeometry_manifest.json"
FINAL_CSV = "predeclared_provider_eligible_observability_frames.csv"
GEOMETRY_AUDIT = "stage4_geometry_audit.csv"
FINAL_MANIFEST = "cohort_manifest.json"
ABORT_MANIFEST = "abort_manifest.json"


class FirstActivationAborted(RuntimeError):
    """Pre-heldout first activation stopped before an authoritative cohort."""

    def __init__(
        self,
        stage: int,
        message: str,
        *,
        partial_frame: pd.DataFrame | None = None,
        audit_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = int(stage)
        self.partial_frame = None if partial_frame is None else partial_frame.copy()
        self.audit_rows = [dict(row) for row in (audit_rows or [])]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    frame.to_csv(path, index=False, lineterminator="\n")


def _fingerprint_fields() -> dict[str, str]:
    return {
        "protocol_fingerprint": EXPECTED_PROTOCOL_FINGERPRINT,
        "execution_contract_fingerprint": EXPECTED_EXECUTION_FINGERPRINT,
        "coverage_contract_fingerprint": EXPECTED_COVERAGE_FINGERPRINT,
        "exclusion_provenance_fingerprint": EXPECTED_EXCLUSION_FINGERPRINT,
        "preregistration_merge_commit": PREREGISTRATION_MERGE_COMMIT,
    }


def _safety_fields() -> dict[str, object]:
    return {
        "heldout_2021_2025_opened": False,
        "candidate_generation_run": False,
        "robust_support_run": False,
        "random_baseline_run": False,
        "recall_or_lift_read": False,
        "score_cutoff_selected": False,
        "outcome_driven_tuning": False,
        "country_substitution_allowed": False,
        "alternate_geometry_provider_allowed": False,
        "post_final_selection_replacement_allowed": False,
    }


def write_abort_manifest(output_dir: Path, stage: int, exc: BaseException) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "status": "provider_eligible_observability_first_activation_aborted_not_evaluable",
        "stage": int(stage),
        "failure_type": type(exc).__name__,
        "failure_reason": str(exc),
        "second_activation_allowed": False,
        "new_seed_or_refreeze_allowed": False,
        **_fingerprint_fields(),
        **_safety_fields(),
    }
    _write_json(output_dir / ABORT_MANIFEST, payload)
    return payload


def _identity_columns(path: Path) -> tuple[str, str]:
    columns = list(pd.read_csv(path, nrows=0).columns)
    lowered = {str(column).lower(): str(column) for column in columns}
    key = lowered.get("specieskey") or lowered.get("species_key")
    name = lowered.get("scientific_name") or lowered.get("scientificname")
    if key is None or name is None:
        raise ValueError(f"identity-only exclusion columns missing from {path}")
    return key, name


def consumed_exclusion_sets() -> tuple[set[int], set[str]]:
    """Load only identity columns from the byte-pinned consumed-source manifest."""
    manifest = exclusion_provenance()
    keys: set[int] = set()
    names: set[str] = set()
    for item in manifest["files"]:
        path = ROOT / str(item["path"])
        key_col, name_col = _identity_columns(path)
        frame = pd.read_csv(path, usecols=[key_col, name_col])
        key_values = pd.to_numeric(frame[key_col], errors="coerce").dropna().astype(int)
        name_values = frame[name_col].dropna().astype(str).str.strip()
        keys.update(key_values.tolist())
        names.update(name_values.tolist())
    return keys, names


def _strict_species_metadata(species_key: int) -> dict[str, Any]:
    payload = get_json(f"{GBIF_SPECIES}/{int(species_key)}", timeout=45)
    if payload.get("rank") != "SPECIES" or not payload.get("scientificName"):
        raise ValueError(f"GBIF species metadata is not a named SPECIES for {species_key}")
    return payload


def _historical_species_facet_search(params: dict[str, object]) -> dict[str, Any]:
    return get_json(GBIF_SEARCH, params, timeout=60)


def historical_taxon_frame(
    bounds: tuple[float, float, float, float],
    kingdom_key: int,
    facet_limit: int,
    minimum_records: int,
    *,
    search_fetcher: Callable[[dict[str, object]], dict[str, Any]] = _historical_species_facet_search,
    metadata_provider: Callable[[int], dict[str, Any]] = _strict_species_metadata,
    metadata_workers: int = 8,
) -> pd.DataFrame:
    """Build one discovery frame from historical 1900--2020 species facets only."""
    start, end = (int(HISTORICAL_YEARS[0]), int(HISTORICAL_YEARS[1]))
    params: dict[str, object] = {
        "kingdomKey": int(kingdom_key),
        "geometry": rectangle_wkt(bounds),
        "year": f"{start},{end}",
        "hasCoordinate": "true",
        "hasGeospatialIssue": "false",
        "occurrenceStatus": "PRESENT",
        "limit": 0,
        "facet": "speciesKey",
        "facetLimit": int(facet_limit),
        "facetMincount": int(minimum_records),
    }
    payload = search_fetcher(params)
    facet_counts: list[dict[str, Any]] | None = None
    for facet in payload.get("facets") or []:
        field = str(facet.get("field") or "").replace("_", "").upper()
        if field == "SPECIESKEY":
            facet_counts = list(facet.get("counts") or [])
            break
    if facet_counts is None:
        facets = payload.get("facets") or []
        if len(facets) == 1:
            facet_counts = list(facets[0].get("counts") or [])
    if facet_counts is None:
        raise ValueError("historical discovery response lacks the requested speciesKey facet")

    def resolve(item: dict[str, Any]) -> dict[str, Any]:
        key = int(item["name"])
        count = int(item["count"])
        metadata = metadata_provider(key)
        if metadata.get("rank") != "SPECIES" or not metadata.get("scientificName"):
            raise ValueError(f"GBIF species metadata drift for {key}")
        return {
            "speciesKey": key,
            "scientific_name": str(metadata["scientificName"]).strip(),
            "coordinate_records": count,
        }

    with ThreadPoolExecutor(max_workers=max(1, int(metadata_workers))) as executor:
        rows = list(executor.map(resolve, facet_counts))
    return pd.DataFrame(rows, columns=["speciesKey", "scientific_name", "coordinate_records"])


def _normalize_discovery_frame(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"speciesKey", "scientific_name", "coordinate_records"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"discovery frame missing columns: {sorted(missing)}")
    work = frame.copy()
    work["speciesKey"] = pd.to_numeric(work["speciesKey"], errors="raise").astype(int)
    work["scientific_name"] = work["scientific_name"].astype(str).str.strip()
    work["coordinate_records"] = pd.to_numeric(
        work["coordinate_records"], errors="raise"
    ).astype(int)
    if work["speciesKey"].duplicated().any() or work["scientific_name"].duplicated().any():
        work = work.drop_duplicates(["speciesKey", "scientific_name"], keep="first").copy()
    return work.reset_index(drop=True)


def build_candidate_snapshot(
    frame_provider: Callable[[tuple[float, float, float, float], int, int, int], pd.DataFrame] = historical_taxon_frame,
    *,
    excluded_keys: set[int] | None = None,
    excluded_names: set[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Stage 1: freeze every exclusion-filtered historical discovery candidate."""
    cfg = protocol()
    validate_static_preregistration()
    if tuple(int(x) for x in cfg["country_declaration"]["historical_years"]) != tuple(
        int(x) for x in HISTORICAL_YEARS
    ):
        raise ValueError("historical year range drift")
    if excluded_keys is None or excluded_names is None:
        frozen_keys, frozen_names = consumed_exclusion_sets()
        if excluded_keys is None:
            excluded_keys = frozen_keys
        if excluded_names is None:
            excluded_names = frozen_names
    excluded_keys = set(int(value) for value in excluded_keys)
    excluded_names = set(str(value).strip() for value in excluded_names)
    prefixes = tuple(str(value) for value in cfg["exclusions"]["explicit_prefixes"])
    facet_limit = int(cfg["cohort"]["facet_limit"])
    minimum_records = int(cfg["cohort"]["minimum_records"])
    seed = int(cfg["cohort"]["selection_seed"])

    rows: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    candidate_id = 0
    for region_index, cell in enumerate(REGION_CELLS, start=1):
        geographic_stratum, region_name, west, south, east, north = cell
        bounds = (float(west), float(south), float(east), float(north))
        for group in GROUP_ORDER:
            try:
                raw = frame_provider(
                    bounds,
                    int(TAXON_GROUPS[group]),
                    facet_limit,
                    minimum_records,
                )
                frame = _normalize_discovery_frame(raw)
            except Exception as exc:
                raise FirstActivationAborted(
                    1,
                    f"discovery provider error for region={region_index}, group={group}: "
                    f"{type(exc).__name__}: {exc}",
                    partial_frame=pd.DataFrame(rows),
                    audit_rows=audit,
                ) from exc

            before = len(frame)
            frame = frame[
                ~frame["speciesKey"].isin(excluded_keys)
                & ~frame["scientific_name"].isin(excluded_names)
                & ~frame["scientific_name"].str.startswith(prefixes)
            ].copy()
            if len(frame) < 4:
                raise FirstActivationAborted(
                    1,
                    f"fewer than four exclusion-filtered candidates for "
                    f"region={region_index}, group={group}",
                    partial_frame=pd.DataFrame(rows),
                    audit_rows=audit,
                )
            frame["record_count_stratum"] = pd.qcut(
                frame["coordinate_records"].rank(method="first"),
                4,
                labels=False,
            ).astype(int)
            stratum_counts = (
                frame["record_count_stratum"].value_counts().sort_index().to_dict()
            )
            if set(stratum_counts) != {0, 1, 2, 3}:
                raise FirstActivationAborted(
                    1,
                    f"record-count strata incomplete for region={region_index}, group={group}: "
                    f"{stratum_counts}",
                    partial_frame=pd.DataFrame(rows),
                    audit_rows=audit,
                )

            audit.append(
                {
                    "region_cell_index": region_index,
                    "taxon_group": group,
                    "raw_candidate_rows": int(before),
                    "eligible_identity_rows_after_exclusions": int(len(frame)),
                    "stratum_0": int(stratum_counts.get(0, 0)),
                    "stratum_1": int(stratum_counts.get(1, 0)),
                    "stratum_2": int(stratum_counts.get(2, 0)),
                    "stratum_3": int(stratum_counts.get(3, 0)),
                    "status": "complete_candidate_frame",
                }
            )
            for row in frame.itertuples(index=False):
                candidate_id += 1
                stratum = int(row.record_count_stratum)
                key = int(row.speciesKey)
                rows.append(
                    {
                        "candidate_id": candidate_id,
                        "status": "candidate_snapshot_frozen_before_historical_country_query",
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
                        "scientific_name": str(row.scientific_name),
                        "coordinate_records": int(row.coordinate_records),
                        "record_count_stratum": stratum,
                        "identity_selection_hash": identity_hash(
                            seed, region_index, group, stratum, key
                        ),
                        "discovery_year_start": int(HISTORICAL_YEARS[0]),
                        "discovery_year_end": int(HISTORICAL_YEARS[1]),
                    }
                )

    snapshot = pd.DataFrame(rows)
    audit_frame = pd.DataFrame(audit)
    if len(audit_frame) != 24 or not audit_frame["status"].eq(
        "complete_candidate_frame"
    ).all():
        raise FirstActivationAborted(
            1,
            "candidate snapshot lacks one or more complete region-group frames",
            partial_frame=snapshot,
            audit_rows=audit,
        )
    if snapshot.empty:
        raise FirstActivationAborted(1, "candidate snapshot is empty")
    return snapshot, audit_frame


def stage1_to_dir(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        snapshot, audit = build_candidate_snapshot()
    except FirstActivationAborted as exc:
        if exc.partial_frame is not None:
            _write_csv(output_dir / "stage1_partial_candidate_snapshot.csv", exc.partial_frame)
        if exc.audit_rows:
            _write_csv(output_dir / "stage1_region_group_audit.csv", pd.DataFrame(exc.audit_rows))
        write_abort_manifest(output_dir, 1, exc)
        raise
    snapshot_path = output_dir / STAGE1_CSV
    audit_path = output_dir / "stage1_region_group_audit.csv"
    _write_csv(snapshot_path, snapshot)
    _write_csv(audit_path, audit)
    payload: dict[str, object] = {
        "status": "stage1_candidate_snapshot_complete_before_focal_historical_facets",
        "candidate_rows": int(len(snapshot)),
        "unique_species_keys": int(snapshot["speciesKey"].nunique()),
        "region_group_frames": 24,
        "discovery_species_facet_years": list(HISTORICAL_YEARS),
        "candidate_snapshot_sha256": _sha256_file(snapshot_path),
        "region_group_audit_sha256": _sha256_file(audit_path),
        **_fingerprint_fields(),
        **_safety_fields(),
    }
    _write_json(output_dir / STAGE1_MANIFEST, payload)
    return payload


def _canonical_country_counts(counts: dict[str, int]) -> dict[str, int]:
    return dict(
        sorted(
            (str(code).strip().upper(), int(count))
            for code, count in counts.items()
            if len(str(code).strip()) == 2 and int(count) > 0
        )
    )


def _query_historical_counts(
    keys: Sequence[int],
    facet_provider: Callable[[int, tuple[int, int]], dict[str, int]],
    *,
    workers: int,
) -> tuple[dict[int, dict[str, int]], list[dict[str, Any]]]:
    results: dict[int, dict[str, int]] = {}
    audit: list[dict[str, Any]] = []

    def one(key: int) -> tuple[int, dict[str, int]]:
        counts = facet_provider(int(key), HISTORICAL_YEARS)
        return int(key), _canonical_country_counts(counts)

    if int(workers) <= 1:
        iterator: Iterable[tuple[int, dict[str, int]]] = (one(key) for key in keys)
    else:
        executor = ThreadPoolExecutor(max_workers=int(workers))
        iterator = executor.map(one, keys)
    try:
        for key, counts in iterator:
            results[key] = counts
            audit.append(
                {
                    "speciesKey": key,
                    "status": "historical_country_facets_complete",
                    "country_count": len(counts),
                    "historical_record_count": int(sum(counts.values())),
                    "failure_reason": "",
                }
            )
    except Exception as exc:
        failed_key = int(keys[len(results)]) if len(results) < len(keys) else None
        audit.append(
            {
                "speciesKey": failed_key,
                "status": "historical_provider_error_abort",
                "country_count": 0,
                "historical_record_count": 0,
                "failure_reason": f"{type(exc).__name__}: {exc}",
            }
        )
        raise FirstActivationAborted(
            2,
            f"historical provider error for speciesKey={failed_key}: "
            f"{type(exc).__name__}: {exc}",
            partial_frame=pd.DataFrame(
                [
                    {
                        "speciesKey": key,
                        "historical_country_counts_json": json.dumps(
                            results[key], sort_keys=True, separators=(",", ":")
                        ),
                    }
                    for key in results
                ]
            ),
            audit_rows=audit,
        ) from exc
    finally:
        if int(workers) > 1:
            executor.shutdown(wait=True, cancel_futures=False)
    return results, audit


def build_historical_eligibility_snapshot(
    candidate_snapshot: pd.DataFrame,
    *,
    facet_provider: Callable[[int, tuple[int, int]], dict[str, int]] = fetch_country_facet_counts,
    workers: int = 4,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Stage 2: complete historical country/provider eligibility for every candidate."""
    cfg = protocol()
    validate_static_preregistration()
    required = {
        "candidate_id",
        "region_cell_index",
        "taxon_group",
        "record_count_stratum",
        "speciesKey",
        "scientific_name",
        "identity_selection_hash",
    }
    missing = required - set(candidate_snapshot.columns)
    if missing:
        raise FirstActivationAborted(2, f"stage1 candidate snapshot missing columns: {sorted(missing)}")
    work = candidate_snapshot.copy()
    work["candidate_id"] = pd.to_numeric(work["candidate_id"], errors="raise").astype(int)
    if work["candidate_id"].duplicated().any():
        raise FirstActivationAborted(2, "stage1 candidate ids are not unique")

    unique_keys = list(dict.fromkeys(work["speciesKey"].astype(int).tolist()))
    counts_by_key, provider_audit = _query_historical_counts(
        unique_keys, facet_provider, workers=workers
    )
    coverage = load_coverage_contract()
    mapping = load_iso_mapping()
    supported = set(coverage["coverage"]["supported_alpha3"])
    minimum_count = int(cfg["country_declaration"]["historical_country_min_count"])
    country_seed = int(cfg["country_declaration"]["country_selection_seed"])

    rows: list[dict[str, Any]] = []
    for row in work.to_dict(orient="records"):
        key = int(row["speciesKey"])
        counts = counts_by_key[key]
        country, basis = choose_historical_country(
            counts,
            species_key=key,
            minimum_count=minimum_count,
            seed=country_seed,
        )
        counts_json = json.dumps(counts, sort_keys=True, separators=(",", ":"))
        selected_count = int(counts[country]) if country is not None else 0
        if country is None:
            alpha3 = ""
            provider_eligible = False
            eligibility_status = str(cfg["cohort"]["legitimate_no_country_status"])
            score: float | None = None
        else:
            alpha3_value = mapping.get(str(country).upper())
            alpha3 = "" if alpha3_value is None else str(alpha3_value)
            provider_eligible = bool(alpha3 and alpha3 in supported)
            eligibility_status = (
                "provider_eligible_before_final_selection"
                if provider_eligible
                else str(cfg["cohort"]["provider_ineligible_candidate_status"])
            )
            score = observability_score(selected_count)
        rows.append(
            {
                **row,
                "historical_country_counts_json": counts_json,
                "selected_country_code": country or "",
                "selected_country_alpha3": alpha3,
                "country_selection_basis": basis,
                "historical_selected_country_count": selected_count,
                "country_frame_observability_score": score,
                "provider_eligible": provider_eligible,
                "eligibility_status": eligibility_status,
                "historical_year_start": int(HISTORICAL_YEARS[0]),
                "historical_year_end": int(HISTORICAL_YEARS[1]),
            }
        )
    result = pd.DataFrame(rows)
    if len(result) != len(work) or result["candidate_id"].tolist() != work["candidate_id"].tolist():
        raise FirstActivationAborted(2, "stage2 did not preserve every stage1 candidate row")
    return result, pd.DataFrame(provider_audit)


def stage2_to_dir(output_dir: Path, *, workers: int = 4) -> dict[str, object]:
    stage1_path = output_dir / STAGE1_CSV
    if not stage1_path.is_file() or not (output_dir / STAGE1_MANIFEST).is_file():
        exc = FirstActivationAborted(2, "complete stage1 artifact is required")
        write_abort_manifest(output_dir, 2, exc)
        raise exc
    stage1_manifest = json.loads((output_dir / STAGE1_MANIFEST).read_text(encoding="utf-8"))
    if stage1_manifest.get("candidate_snapshot_sha256") != _sha256_file(stage1_path):
        exc = FirstActivationAborted(2, "stage1 candidate snapshot byte hash mismatch")
        write_abort_manifest(output_dir, 2, exc)
        raise exc
    candidates = pd.read_csv(stage1_path)
    try:
        snapshot, provider_audit = build_historical_eligibility_snapshot(
            candidates, workers=workers
        )
    except FirstActivationAborted as exc:
        if exc.partial_frame is not None:
            _write_csv(output_dir / "stage2_partial_historical_results.csv", exc.partial_frame)
        if exc.audit_rows:
            _write_csv(
                output_dir / "stage2_historical_provider_audit.csv",
                pd.DataFrame(exc.audit_rows),
            )
        write_abort_manifest(output_dir, 2, exc)
        raise
    snapshot_path = output_dir / STAGE2_CSV
    audit_path = output_dir / "stage2_historical_provider_audit.csv"
    _write_csv(snapshot_path, snapshot)
    _write_csv(audit_path, provider_audit)
    payload: dict[str, object] = {
        "status": "stage2_historical_provider_eligibility_complete_before_final_selection",
        "input_candidate_snapshot_sha256": _sha256_file(stage1_path),
        "candidate_rows": int(len(snapshot)),
        "unique_species_keys_queried": int(snapshot["speciesKey"].nunique()),
        "provider_eligible_rows": int(snapshot["provider_eligible"].astype(bool).sum()),
        "provider_ineligible_rows": int(
            snapshot["eligibility_status"]
            .eq("preselection_ineligible_provider_coverage")
            .sum()
        ),
        "no_historical_country_rows": int(
            snapshot["eligibility_status"]
            .eq("preselection_ineligible_no_historical_country")
            .sum()
        ),
        "historical_years": list(HISTORICAL_YEARS),
        "historical_eligibility_snapshot_sha256": _sha256_file(snapshot_path),
        "historical_provider_audit_sha256": _sha256_file(audit_path),
        **_fingerprint_fields(),
        **_safety_fields(),
    }
    _write_json(output_dir / STAGE2_MANIFEST, payload)
    return payload


def _bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series
    return series.astype(str).str.strip().str.lower().eq("true")


def select_final_96_offline(
    eligibility_snapshot: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Stage 3: deterministic network-free selection of 96 unique final frames."""
    cfg = protocol()
    validate_static_preregistration()
    required = {
        "candidate_id",
        "region_cell_index",
        "taxon_group",
        "record_count_stratum",
        "speciesKey",
        "scientific_name",
        "identity_selection_hash",
        "provider_eligible",
        "eligibility_status",
        "selected_country_code",
        "selected_country_alpha3",
        "historical_selected_country_count",
        "country_frame_observability_score",
    }
    missing = required - set(eligibility_snapshot.columns)
    if missing:
        raise FirstActivationAborted(3, f"stage2 eligibility snapshot missing columns: {sorted(missing)}")
    work = eligibility_snapshot.copy()
    work["provider_eligible"] = _bool_series(work["provider_eligible"])
    seed = int(cfg["cohort"]["selection_seed"])
    used_keys: set[int] = set()
    used_names: set[str] = set()
    selected_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []

    for region_index in range(1, 13):
        for group in GROUP_ORDER:
            for stratum in range(4):
                cell = work[
                    pd.to_numeric(work["region_cell_index"], errors="raise").astype(int).eq(region_index)
                    & work["taxon_group"].astype(str).eq(group)
                    & pd.to_numeric(work["record_count_stratum"], errors="raise").astype(int).eq(stratum)
                ].copy()
                if cell.empty:
                    raise FirstActivationAborted(
                        3,
                        f"stage2 snapshot has no candidates for region={region_index}, "
                        f"group={group}, stratum={stratum}",
                        partial_frame=pd.DataFrame(selected_rows),
                        audit_rows=audit_rows,
                    )
                eligible = cell[
                    cell["provider_eligible"]
                    & cell["eligibility_status"].astype(str).eq(
                        "provider_eligible_before_final_selection"
                    )
                ].copy()
                if eligible.empty:
                    raise FirstActivationAborted(
                        3,
                        f"no provider-eligible candidate for region={region_index}, "
                        f"group={group}, stratum={stratum}",
                        partial_frame=pd.DataFrame(selected_rows),
                        audit_rows=audit_rows,
                    )
                for idx, row in eligible.iterrows():
                    expected_hash = identity_hash(
                        seed,
                        region_index,
                        group,
                        stratum,
                        int(row["speciesKey"]),
                    )
                    if str(row["identity_selection_hash"]) != expected_hash:
                        raise FirstActivationAborted(
                            3,
                            f"identity hash drift for candidate_id={row['candidate_id']}",
                            partial_frame=pd.DataFrame(selected_rows),
                            audit_rows=audit_rows,
                        )
                    eligible.at[idx, "_verified_identity_hash"] = expected_hash
                eligible = eligible.sort_values(
                    ["_verified_identity_hash", "speciesKey", "scientific_name"],
                    kind="mergesort",
                )
                chosen: dict[str, Any] | None = None
                chosen_candidate_id: int | None = None
                for rank, row in enumerate(eligible.to_dict(orient="records"), start=1):
                    key = int(row["speciesKey"])
                    name = str(row["scientific_name"])
                    if key in used_keys or name in used_names:
                        status = "eligible_rejected_global_identity_already_selected"
                    elif chosen is None:
                        status = "selected_identity_hash_min_eligible_unused"
                        chosen = dict(row)
                        chosen_candidate_id = int(row["candidate_id"])
                    else:
                        status = "eligible_not_selected_higher_identity_hash"
                    audit_rows.append(
                        {
                            "region_cell_index": region_index,
                            "taxon_group": group,
                            "record_count_stratum": stratum,
                            "candidate_id": int(row["candidate_id"]),
                            "speciesKey": key,
                            "scientific_name": name,
                            "eligible_identity_hash_rank": rank,
                            "identity_selection_hash": str(row["_verified_identity_hash"]),
                            "selection_status": status,
                        }
                    )
                if chosen is None:
                    raise FirstActivationAborted(
                        3,
                        f"all provider-eligible candidates duplicate earlier frozen identities for "
                        f"region={region_index}, group={group}, stratum={stratum}",
                        partial_frame=pd.DataFrame(selected_rows),
                        audit_rows=audit_rows,
                    )
                chosen.pop("_verified_identity_hash", None)
                chosen["observability_frame_id"] = len(selected_rows) + 1
                chosen["status"] = "final_identity_country_score_frozen_pregeometry_before_heldout"
                chosen["declaration_status"] = "declared_provider_eligible"
                chosen["offline_selection_candidate_id"] = chosen_candidate_id
                selected_rows.append(chosen)
                used_keys.add(int(chosen["speciesKey"]))
                used_names.add(str(chosen["scientific_name"]))

    selected = pd.DataFrame(selected_rows)
    audit = pd.DataFrame(audit_rows)
    if len(selected) != int(cfg["cohort"]["target_frames"]):
        raise FirstActivationAborted(3, f"final offline selection produced {len(selected)} rows")
    if selected["speciesKey"].nunique() != 96 or selected["scientific_name"].nunique() != 96:
        raise FirstActivationAborted(3, "final offline selection is not 96 unique identities")
    if selected["taxon_group"].value_counts().to_dict() != {"plant": 48, "animal": 48}:
        raise FirstActivationAborted(3, "final offline taxon-group balance drift")
    for group in GROUP_ORDER:
        counts = (
            selected.loc[selected["taxon_group"].eq(group), "record_count_stratum"]
            .astype(int)
            .value_counts()
            .sort_index()
            .to_dict()
        )
        if counts != {0: 12, 1: 12, 2: 12, 3: 12}:
            raise FirstActivationAborted(3, f"final stratum balance drift for {group}: {counts}")
    return selected, audit


def stage3_to_dir(output_dir: Path) -> dict[str, object]:
    stage1_path = output_dir / STAGE1_CSV
    stage2_path = output_dir / STAGE2_CSV
    if not stage1_path.is_file() or not stage2_path.is_file():
        exc = FirstActivationAborted(3, "complete stage1 and stage2 snapshots are required")
        write_abort_manifest(output_dir, 3, exc)
        raise exc
    stage2_manifest = json.loads((output_dir / STAGE2_MANIFEST).read_text(encoding="utf-8"))
    if stage2_manifest.get("input_candidate_snapshot_sha256") != _sha256_file(stage1_path):
        exc = FirstActivationAborted(3, "stage2 input binding to stage1 bytes drifted")
        write_abort_manifest(output_dir, 3, exc)
        raise exc
    if stage2_manifest.get("historical_eligibility_snapshot_sha256") != _sha256_file(stage2_path):
        exc = FirstActivationAborted(3, "stage2 snapshot byte hash mismatch")
        write_abort_manifest(output_dir, 3, exc)
        raise exc
    try:
        selected, audit = select_final_96_offline(pd.read_csv(stage2_path))
    except FirstActivationAborted as exc:
        if exc.partial_frame is not None:
            _write_csv(output_dir / "stage3_partial_final_selection.csv", exc.partial_frame)
        if exc.audit_rows:
            _write_csv(output_dir / STAGE3_AUDIT, pd.DataFrame(exc.audit_rows))
        write_abort_manifest(output_dir, 3, exc)
        raise
    selected_path = output_dir / STAGE3_CSV
    audit_path = output_dir / STAGE3_AUDIT
    _write_csv(selected_path, selected)
    _write_csv(audit_path, audit)
    payload: dict[str, object] = {
        "status": "stage3_final_96_selected_offline_before_geometry_and_heldout",
        "input_candidate_snapshot_sha256": _sha256_file(stage1_path),
        "input_historical_eligibility_snapshot_sha256": _sha256_file(stage2_path),
        "final_frames": int(len(selected)),
        "unique_species_keys": int(selected["speciesKey"].nunique()),
        "unique_scientific_names": int(selected["scientific_name"].nunique()),
        "network_used_for_selection": False,
        "score_used_for_selection_ranking": False,
        "historical_count_used_for_selection_ranking": False,
        "final_pregeometry_sha256": _sha256_file(selected_path),
        "offline_selection_audit_sha256": _sha256_file(audit_path),
        **_fingerprint_fields(),
        **_safety_fields(),
    }
    _write_json(output_dir / STAGE3_MANIFEST, payload)
    return payload


def freeze_pinned_geometry(
    selected: pd.DataFrame,
    *,
    geometry_provider: Callable[[str], object] = fetch_geoboundaries_country_geometry,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Stage 4: attach the commit-pinned geometry to the exact stage-3 cohort."""
    cfg = protocol()
    validate_static_preregistration()
    if GEOBOUNDARIES_RELEASE_COMMIT != str(
        cfg["country_declaration"]["geometry_provider_release_commit"]
    ):
        raise FirstActivationAborted(4, "geometry release commit drift")
    if GEOBOUNDARIES_SOURCE_ID != str(
        cfg["country_declaration"]["geometry_provider_source_id"]
    ):
        raise FirstActivationAborted(4, "geometry source id drift")
    if len(selected) != 96 or selected["speciesKey"].nunique() != 96:
        raise FirstActivationAborted(4, "stage4 requires the exact complete 96-frame stage3 cohort")

    rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    for base in selected.to_dict(orient="records"):
        country = str(base["selected_country_code"]).strip().upper()
        try:
            geometry = geometry_provider(country)
            if str(geometry.country_code).upper() != country:
                raise ValueError(
                    f"provider country mismatch: requested {country}, returned {geometry.country_code}"
                )
            source_id = str(geometry.source_id)
            source_version = str(geometry.source_version)
            if source_id != GEOBOUNDARIES_SOURCE_ID:
                raise ValueError(f"geometry source id mismatch: {source_id}")
            expected_prefix = f"{GEOBOUNDARIES_RELEASE_TAG}@{GEOBOUNDARIES_RELEASE_COMMIT};"
            if not source_version.startswith(expected_prefix):
                raise ValueError("geometry source version is not the exact pinned release commit")
            digest = _geometry_digest_from_source_version(source_version)
        except Exception as exc:
            audit_rows.append(
                {
                    "observability_frame_id": int(base["observability_frame_id"]),
                    "speciesKey": int(base["speciesKey"]),
                    "selected_country_code": country,
                    "status": "geometry_provider_error_abort",
                    "failure_reason": f"{type(exc).__name__}: {exc}",
                }
            )
            raise FirstActivationAborted(
                4,
                f"pinned geometry failure for speciesKey={base['speciesKey']}, "
                f"country={country}: {type(exc).__name__}: {exc}",
                partial_frame=pd.DataFrame(rows),
                audit_rows=audit_rows,
            ) from exc
        audit_rows.append(
            {
                "observability_frame_id": int(base["observability_frame_id"]),
                "speciesKey": int(base["speciesKey"]),
                "selected_country_code": country,
                "status": "pinned_geometry_frozen",
                "failure_reason": "",
            }
        )
        rows.append(
            {
                **base,
                "status": "provider_eligible_observability_frame_frozen_before_heldout",
                "geometry_source_id": source_id,
                "geometry_source_version": source_version,
                "geometry_canonical_sha256": digest,
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(audit_rows)


def _verify_final_frames(frame: pd.DataFrame) -> None:
    if len(frame) != 96 or frame["speciesKey"].nunique() != 96:
        raise FirstActivationAborted(4, "authoritative cohort is not exactly 96 unique species keys")
    if frame["scientific_name"].nunique() != 96:
        raise FirstActivationAborted(4, "authoritative cohort is not 96 unique scientific names")
    if frame["taxon_group"].value_counts().to_dict() != {"plant": 48, "animal": 48}:
        raise FirstActivationAborted(4, "authoritative taxon-group balance drift")
    if not _bool_series(frame["provider_eligible"]).all():
        raise FirstActivationAborted(4, "authoritative cohort contains provider-ineligible row")
    if not frame["eligibility_status"].eq("provider_eligible_before_final_selection").all():
        raise FirstActivationAborted(4, "authoritative eligibility status drift")
    if (frame["historical_selected_country_count"].astype(int) < 5).any():
        raise FirstActivationAborted(4, "authoritative cohort violates historical count minimum")
    for row in frame.itertuples(index=False):
        expected = observability_score(int(row.historical_selected_country_count))
        if not math.isclose(
            float(row.country_frame_observability_score),
            expected,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise FirstActivationAborted(4, "authoritative observability score drift")
    keys, names = consumed_exclusion_sets()
    if set(frame["speciesKey"].astype(int)) & keys:
        raise FirstActivationAborted(4, "authoritative cohort overlaps consumed speciesKey")
    if set(frame["scientific_name"].astype(str)) & names:
        raise FirstActivationAborted(4, "authoritative cohort overlaps consumed scientific name")
    forbidden_fragments = (
        "recent",
        "heldout_outcome",
        "candidate_patch",
        "robust_recall",
        "random_recall",
        "lift",
    )
    for column in frame.columns:
        if any(fragment in column.lower() for fragment in forbidden_fragments):
            raise FirstActivationAborted(
                4, f"heldout/outcome column forbidden in first activation: {column}"
            )
    per_cell = frame.groupby(["region_cell_index", "taxon_group"]).size()
    if len(per_cell) != 24 or not (per_cell == 4).all():
        raise FirstActivationAborted(4, "authoritative region-group balance drift")
    for group in GROUP_ORDER:
        counts = (
            frame.loc[frame["taxon_group"].eq(group), "record_count_stratum"]
            .astype(int)
            .value_counts()
            .sort_index()
            .to_dict()
        )
        if counts != {0: 12, 1: 12, 2: 12, 3: 12}:
            raise FirstActivationAborted(4, f"authoritative stratum balance drift for {group}")


def stage4_to_dir(
    output_dir: Path,
    *,
    activation_marker: Path = FIRST_ACTIVATION_MARKER,
) -> dict[str, object]:
    stage1_path = output_dir / STAGE1_CSV
    stage2_path = output_dir / STAGE2_CSV
    stage3_path = output_dir / STAGE3_CSV
    stage3_manifest_path = output_dir / STAGE3_MANIFEST
    if not all(path.is_file() for path in (stage1_path, stage2_path, stage3_path, stage3_manifest_path)):
        exc = FirstActivationAborted(4, "complete stage1-stage3 snapshots are required")
        write_abort_manifest(output_dir, 4, exc)
        raise exc
    stage3_manifest = json.loads(stage3_manifest_path.read_text(encoding="utf-8"))
    if stage3_manifest.get("final_pregeometry_sha256") != _sha256_file(stage3_path):
        exc = FirstActivationAborted(4, "stage3 final pregeometry byte hash mismatch")
        write_abort_manifest(output_dir, 4, exc)
        raise exc
    try:
        final, geometry_audit = freeze_pinned_geometry(pd.read_csv(stage3_path))
        _verify_final_frames(final)
    except FirstActivationAborted as exc:
        if exc.partial_frame is not None:
            _write_csv(output_dir / "stage4_partial_geometry_frames.csv", exc.partial_frame)
        if exc.audit_rows:
            _write_csv(output_dir / GEOMETRY_AUDIT, pd.DataFrame(exc.audit_rows))
        write_abort_manifest(output_dir, 4, exc)
        raise

    final_path = output_dir / FINAL_CSV
    geometry_audit_path = output_dir / GEOMETRY_AUDIT
    _write_csv(final_path, final)
    _write_csv(geometry_audit_path, geometry_audit)
    marker_sha256 = _sha256_file(activation_marker) if activation_marker.is_file() else ""
    cfg = protocol()
    payload: dict[str, object] = {
        "status": "provider_eligible_observability_96_frames_frozen_before_heldout",
        "first_activation_complete": True,
        "second_activation_allowed": True,
        "frozen_frames": 96,
        "unique_species_keys": 96,
        "unique_scientific_names": 96,
        "taxon_group_counts": {"animal": 48, "plant": 48},
        "discovery_species_facet_years": list(HISTORICAL_YEARS),
        "historical_country_facet_years": list(HISTORICAL_YEARS),
        "candidate_snapshot_sha256": _sha256_file(stage1_path),
        "historical_eligibility_snapshot_sha256": _sha256_file(stage2_path),
        "final_pregeometry_sha256": _sha256_file(stage3_path),
        "final_frames_sha256": _sha256_file(final_path),
        "geometry_audit_sha256": _sha256_file(geometry_audit_path),
        "activation_marker_path": str(activation_marker),
        "activation_marker_sha256": marker_sha256,
        "score_formula": str(cfg["country_declaration"]["score_formula"]),
        **_fingerprint_fields(),
        **_safety_fields(),
    }
    _write_json(output_dir / FINAL_MANIFEST, payload)
    return payload


def verify_authoritative_dir(output_dir: Path) -> dict[str, object]:
    final_path = output_dir / FINAL_CSV
    manifest_path = output_dir / FINAL_MANIFEST
    if not final_path.is_file() or not manifest_path.is_file():
        raise ValueError("authoritative final CSV and manifest are required")
    frame = pd.read_csv(final_path)
    _verify_final_frames(frame)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "provider_eligible_observability_96_frames_frozen_before_heldout":
        raise ValueError("authoritative first-activation status drift")
    if manifest.get("final_frames_sha256") != _sha256_file(final_path):
        raise ValueError("authoritative final frame byte hash drift")
    for key, value in _fingerprint_fields().items():
        if manifest.get(key) != value:
            raise ValueError(f"authoritative manifest fingerprint drift: {key}")
    if manifest.get("heldout_2021_2025_opened") is not False:
        raise ValueError("heldout opened during first activation")
    if manifest.get("second_activation_allowed") is not True:
        raise ValueError("complete first activation did not authorize second activation")
    return manifest


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("stage1", "stage2", "stage3", "stage4", "verify"):
        child = sub.add_parser(name)
        child.add_argument("--output-dir", type=Path, required=True)
        if name == "stage2":
            child.add_argument("--workers", type=int, default=4)
        if name == "stage4":
            child.add_argument("--activation-marker", type=Path, default=FIRST_ACTIVATION_MARKER)
    args = parser.parse_args(argv)
    try:
        if args.command == "stage1":
            payload = stage1_to_dir(args.output_dir)
        elif args.command == "stage2":
            payload = stage2_to_dir(args.output_dir, workers=args.workers)
        elif args.command == "stage3":
            payload = stage3_to_dir(args.output_dir)
        elif args.command == "stage4":
            payload = stage4_to_dir(
                args.output_dir,
                activation_marker=args.activation_marker,
            )
        else:
            payload = verify_authoritative_dir(args.output_dir)
    except FirstActivationAborted:
        return 2
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
