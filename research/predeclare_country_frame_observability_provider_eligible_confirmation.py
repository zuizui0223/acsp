#!/usr/bin/env python3
"""Freeze the new provider-eligible prospective observability cohort for issue #169.

This module is independent of aborted confirmation #163.  Before any candidate
identity is queried it verifies the new protocol and the frozen geoBoundaries
ADM0 coverage contract.  Candidate discovery and focal-species country facets
are historical-only (1900--2020).  The pre-existing country declaration rule is
applied first; a declaration outside frozen provider coverage is recorded as a
pre-freeze eligibility failure and the identity-hash traversal continues without
substituting another country.  Once a final frame is frozen, replacement is
forbidden.  This stage cannot open 2021--2025 outcomes.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable, Sequence

import pandas as pd

from acsp.benchmarking import get_json
from benchmark_general_random_taxa_regions import (
    GBIF_SEARCH,
    REGION_CELLS,
    TAXON_GROUPS,
    _species_metadata,
    rectangle_wkt,
)
from geographic_framing_country_registry_v3 import HISTORICAL_YEARS, fetch_country_facet_counts
from geoboundaries_v6_coverage_contract import (
    EXPECTED_CONTRACT_FINGERPRINT as EXPECTED_COVERAGE_FINGERPRINT,
    alpha2_to_alpha3_if_supported,
    load_contract as load_coverage_contract,
)
from geoboundaries_v6_provider import (
    GEOBOUNDARIES_RELEASE_COMMIT,
    GEOBOUNDARIES_SOURCE_ID,
    fetch_geoboundaries_country_geometry,
)
from predeclare_country_framed_fresh_heterogeneity_confirmation import (
    exclusion_sets as base_exclusion_sets,
    protocol as base_fresh_protocol,
)
from predeclare_country_framed_integration_development_v1 import (
    _geometry_digest_from_source_version,
    choose_historical_country,
)

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "validation" / "acsp_country_frame_observability_provider_eligible_confirmation_v1.json"
TERMINAL_FRESH_IDENTITY_PATH = ROOT / "validation" / "acsp_country_framed_fresh_heterogeneity_confirmation_identities_v1.csv"
EXPECTED_PROTOCOL_FINGERPRINT = "91b8143f38abb173c3cdabc198bfcc5f113632f33b3c674b99374aac1efdd644"
EXPECTED_BASE_EXCLUSION_PROTOCOL_FINGERPRINT = "65ba06f174f4bdc9a49c24e54e8f7c67958757ab527fc23e4ccf427bf2d91a01"
EXPECTED_TERMINAL_FRESH_IDENTITY_SHA256 = "4dfe23ff32c2e3c3fd601afefabf733feab09f2c95db1def246ed793cd347cb9"
EXPECTED_TERMINAL_FRESH_IDENTITY_GIT_BLOB_SHA = "b3519259d06a6d04ba05cae25975aed01fbe087c"
EXPECTED_REGION_CELLS_SHA256 = "09e74f1fbaa517316e7f18baa405fc77a495eda27c781051fa2e18efdbd20a24"
EXPECTED_IDENTITY_SEED_TOKEN = "acsp_country_frame_observability_confirmation_provider_eligible_v1|identity-order"
EXPECTED_IDENTITY_SEED_SHA256 = "298f467cd47b5297a5c8b6aaa39978b1b7abf555db9f161c9607327565f23ea1"
EXPECTED_IDENTITY_SEED = 664395665
GROUP_ORDER = ("plant", "animal")


class FreezeAborted(RuntimeError):
    def __init__(self, message: str, audit_rows: list[dict[str, object]]) -> None:
        super().__init__(message)
        self.audit_rows = [dict(row) for row in audit_rows]


def _canonical_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("utf-8") + data).hexdigest()


def _region_cells_digest() -> str:
    return hashlib.sha256(
        json.dumps(REGION_CELLS, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def protocol() -> dict[str, object]:
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    stored = str(payload.pop("protocol_fingerprint", ""))
    calculated = _canonical_sha256(payload)
    if stored != EXPECTED_PROTOCOL_FINGERPRINT or calculated != EXPECTED_PROTOCOL_FINGERPRINT:
        raise ValueError(
            "provider-eligible observability protocol fingerprint mismatch: "
            f"file={stored}, calculated={calculated}, expected={EXPECTED_PROTOCOL_FINGERPRINT}"
        )
    if payload["parent_issue"] != 169 or payload["scientific_position"]["independent_new_confirmation"] is not True:
        raise ValueError("provider-eligible observability scientific position drift")
    if payload["scientific_position"]["continuation_rescue_or_rerun_of_163"] is not False:
        raise ValueError("new confirmation may not continue #163")
    if payload["provider_eligibility"]["coverage_contract_fingerprint"] != EXPECTED_COVERAGE_FINGERPRINT:
        raise ValueError("provider coverage fingerprint drift")
    coverage = load_coverage_contract()
    if coverage["coverage_contract_fingerprint"] != EXPECTED_COVERAGE_FINGERPRINT:
        raise ValueError("loaded provider coverage contract drift")
    if coverage["policy"]["parent_confirmation_163_may_be_resumed"] is not False:
        raise ValueError("coverage policy no longer terminates #163")
    if coverage["policy"]["alternate_geometry_provider_fallback_allowed"] is not False:
        raise ValueError("coverage policy unexpectedly allows geometry fallback")
    if payload["cohort"]["target_frames"] != 96 or payload["cohort"]["no_replacement_after_freeze"] is not True:
        raise ValueError("provider-eligible cohort contract drift")
    if payload["cohort"]["region_cells_sha256"] != EXPECTED_REGION_CELLS_SHA256 or _region_cells_digest() != EXPECTED_REGION_CELLS_SHA256:
        raise ValueError("fixed discovery region cells drift")
    seed = payload["cohort"]["identity_seed_derivation"]
    digest = hashlib.sha256(str(seed["token"]).encode("utf-8")).hexdigest()
    derived = int(digest[:16], 16) % 2147483647
    if seed["token"] != EXPECTED_IDENTITY_SEED_TOKEN or digest != EXPECTED_IDENTITY_SEED_SHA256 or int(seed["selection_seed"]) != EXPECTED_IDENTITY_SEED or derived != EXPECTED_IDENTITY_SEED:
        raise ValueError("outcome-independent identity seed derivation drift")
    if list(payload["cohort"]["discovery_years"]) != [1900, 2020] or list(HISTORICAL_YEARS) != [1900, 2020]:
        raise ValueError("historical discovery/country year boundary drift")
    if payload["country_declaration"]["score_formula"] != "log1p(historical_selected_country_count)":
        raise ValueError("observability score formula drift")
    if payload["country_declaration"]["score_cutoff_selected"] is not False:
        raise ValueError("provider-eligible confirmation may not create a score cutoff")
    if payload["execution"]["freeze_activation_opens_heldout"] is not False:
        raise ValueError("freeze activation may not open heldout outcomes")
    payload["protocol_fingerprint"] = stored
    return payload


def _terminal_fresh_identity_exclusions(path: Path = TERMINAL_FRESH_IDENTITY_PATH) -> tuple[set[int], set[str]]:
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != EXPECTED_TERMINAL_FRESH_IDENTITY_SHA256:
        raise ValueError("terminal fresh identity-only SHA256 mismatch")
    if _git_blob_sha(data) != EXPECTED_TERMINAL_FRESH_IDENTITY_GIT_BLOB_SHA:
        raise ValueError("terminal fresh identity-only git-blob SHA mismatch")
    frame = pd.read_csv(path, usecols=["fresh_pair_id", "taxon_group", "speciesKey", "scientific_name"])
    if len(frame) != 48 or frame["speciesKey"].nunique() != 48 or frame["scientific_name"].nunique() != 48:
        raise ValueError("terminal fresh identity-only exclusion is not 48 unique taxa")
    if frame["taxon_group"].value_counts().to_dict() != {"plant": 24, "animal": 24}:
        raise ValueError("terminal fresh identity-only group balance drift")
    return set(frame["speciesKey"].astype(int)), set(frame["scientific_name"].astype(str).str.strip())


def consumed_exclusion_sets() -> tuple[set[int], set[str]]:
    cfg = protocol()
    base_cfg = base_fresh_protocol()
    if base_cfg["protocol_fingerprint"] != EXPECTED_BASE_EXCLUSION_PROTOCOL_FINGERPRINT:
        raise ValueError("base exclusion protocol fingerprint drift")
    if cfg["freshness"]["base_exclusion_protocol_fingerprint"] != EXPECTED_BASE_EXCLUSION_PROTOCOL_FINGERPRINT:
        raise ValueError("new protocol base exclusion binding drift")
    keys, names = base_exclusion_sets(base_cfg["exclusions"])
    terminal_keys, terminal_names = _terminal_fresh_identity_exclusions()
    return set(keys) | terminal_keys, set(names) | terminal_names


def identity_hash(seed: int, region: int, group: str, stratum: int, species_key: int) -> str:
    token = f"{int(seed)}|{int(region)}|{group}|{int(stratum)}|{int(species_key)}".encode("utf-8")
    return hashlib.sha256(token).hexdigest()


def observability_score(historical_selected_country_count: int) -> float:
    count = int(historical_selected_country_count)
    if count < 0:
        raise ValueError("historical selected-country count must be nonnegative")
    return float(math.log1p(count))


def historical_taxon_frame(bounds: tuple[float, float, float, float], kingdom_key: int, facet_limit: int, minimum_records: int) -> pd.DataFrame:
    start, end = (1900, 2020)
    payload = get_json(
        GBIF_SEARCH,
        {
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
        },
    )
    counts = payload.get("facets", [{}])[0].get("counts", [])

    def resolve(item: dict[str, Any]) -> dict[str, Any] | None:
        key = int(item["name"])
        metadata = _species_metadata(key)
        if metadata is None or metadata.get("rank") != "SPECIES" or not metadata.get("scientificName"):
            return None
        return {
            "speciesKey": key,
            "scientific_name": str(metadata["scientificName"]),
            "coordinate_records": int(item["count"]),
        }

    with ThreadPoolExecutor(max_workers=8) as executor:
        rows = list(executor.map(resolve, counts))
    return pd.DataFrame([row for row in rows if row is not None])


def _normalize_discovery_frame(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"speciesKey", "scientific_name", "coordinate_records"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"historical discovery frame missing columns: {sorted(missing)}")
    work = frame.copy()
    work["speciesKey"] = pd.to_numeric(work["speciesKey"], errors="raise").astype(int)
    work["scientific_name"] = work["scientific_name"].astype(str).str.strip()
    work["coordinate_records"] = pd.to_numeric(work["coordinate_records"], errors="raise").astype(int)
    return work.drop_duplicates(["speciesKey", "scientific_name"]).copy()


def _attempt_base(region_index: int, group: str, stratum: int, attempt_rank: int, digest: str, row: pd.Series) -> dict[str, object]:
    return {
        "region_cell_index": int(region_index),
        "taxon_group": str(group),
        "record_count_stratum": int(stratum),
        "attempt_rank": int(attempt_rank),
        "identity_selection_hash": str(digest),
        "speciesKey": int(row["speciesKey"]),
        "scientific_name": str(row["scientific_name"]),
        "coordinate_records": int(row["coordinate_records"]),
    }


def select_frames(
    frame_provider: Callable[[tuple[float, float, float, float], int, int, int], pd.DataFrame] = historical_taxon_frame,
    facet_provider: Callable[[int, tuple[int, int]], dict[str, int]] = fetch_country_facet_counts,
    geometry_provider: Callable[[str], object] = fetch_geoboundaries_country_geometry,
    *,
    excluded_keys: set[int] | None = None,
    excluded_names: set[str] | None = None,
    explicit_prefixes: tuple[str, ...] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    cfg = protocol()
    coverage = load_coverage_contract()
    if coverage["coverage_contract_fingerprint"] != cfg["provider_eligibility"]["coverage_contract_fingerprint"]:
        raise ValueError("provider eligibility contract is not the preregistered contract")
    if GEOBOUNDARIES_RELEASE_COMMIT != str(coverage["provider"]["release_commit"]):
        raise ValueError("geometry provider release commit drift")

    if excluded_keys is None or excluded_names is None:
        consumed_keys, consumed_names = consumed_exclusion_sets()
        excluded_keys = consumed_keys if excluded_keys is None else excluded_keys
        excluded_names = consumed_names if excluded_names is None else excluded_names
    excluded_keys = {int(x) for x in excluded_keys}
    excluded_names = {str(x).strip() for x in excluded_names}
    if explicit_prefixes is None:
        explicit_prefixes = tuple(str(x) for x in cfg["freshness"]["explicit_prefixes"])

    cohort = cfg["cohort"]
    country_cfg = cfg["country_declaration"]
    seed = int(cohort["identity_seed_derivation"]["selection_seed"])
    facet_limit = int(cohort["facet_limit"])
    minimum_records = int(cohort["minimum_records"])
    minimum_country_count = int(country_cfg["historical_country_min_count"])
    country_seed = int(country_cfg["country_selection_seed"])

    selected_rows: list[dict[str, object]] = []
    audit_rows: list[dict[str, object]] = []
    used_keys: set[int] = set()
    used_names: set[str] = set()

    for region_index, cell in enumerate(REGION_CELLS, start=1):
        geographic_stratum, region_name, west, south, east, north = cell
        bounds = (float(west), float(south), float(east), float(north))
        for group in GROUP_ORDER:
            try:
                frame = _normalize_discovery_frame(
                    frame_provider(bounds, int(TAXON_GROUPS[group]), facet_limit, minimum_records)
                )
            except Exception as exc:
                raise FreezeAborted(
                    f"historical discovery provider error for region={region_index}, group={group}; freeze aborted",
                    audit_rows,
                ) from exc
            frame = frame[
                ~frame["speciesKey"].isin(excluded_keys)
                & ~frame["scientific_name"].isin(excluded_names)
                & ~frame["scientific_name"].str.startswith(tuple(explicit_prefixes))
            ].copy()
            if len(frame) < 4:
                raise FreezeAborted(
                    f"fewer than four eligible fresh historical taxa for region={region_index}, group={group}", audit_rows
                )
            frame["record_count_stratum"] = pd.qcut(
                frame["coordinate_records"].rank(method="first"), 4, labels=False
            ).astype(int)

            for stratum in range(4):
                pool = frame[
                    frame["record_count_stratum"].eq(stratum)
                    & ~frame["speciesKey"].isin(used_keys)
                    & ~frame["scientific_name"].isin(used_names)
                ].copy()
                if pool.empty:
                    raise FreezeAborted(
                        f"empty fresh pool for region={region_index}, group={group}, stratum={stratum}", audit_rows
                    )
                pool["_identity_hash"] = [
                    identity_hash(seed, region_index, group, stratum, key)
                    for key in pool["speciesKey"].astype(int)
                ]
                pool = pool.sort_values(["_identity_hash", "speciesKey", "scientific_name"], kind="mergesort")

                chosen: dict[str, object] | None = None
                for attempt_rank, (_, row) in enumerate(pool.iterrows(), start=1):
                    key = int(row["speciesKey"])
                    name = str(row["scientific_name"])
                    attempt = _attempt_base(
                        region_index, group, stratum, attempt_rank, str(row["_identity_hash"]), row
                    )
                    try:
                        counts = dict(sorted((str(code).upper(), int(count)) for code, count in facet_provider(key, HISTORICAL_YEARS).items()))
                    except Exception as exc:
                        audit_rows.append({**attempt, "attempt_status": "historical_provider_error_abort", "selected": False, "selected_country_code": "", "selected_country_alpha3": "", "country_selection_basis": "", "historical_selected_country_count": 0, "country_frame_observability_score": None, "historical_country_counts_json": "{}", "geometry_source_id": "", "geometry_source_version": "", "geometry_canonical_sha256": "", "failure_reason": f"{type(exc).__name__}: {exc}"})
                        raise FreezeAborted(f"historical provider error for speciesKey={key}; freeze aborted", audit_rows) from exc

                    country, basis = choose_historical_country(
                        counts, species_key=key, minimum_count=minimum_country_count, seed=country_seed
                    )
                    counts_json = json.dumps(counts, sort_keys=True, separators=(",", ":"))
                    if country is None:
                        audit_rows.append({**attempt, "attempt_status": "no_eligible_historical_country", "selected": False, "selected_country_code": "", "selected_country_alpha3": "", "country_selection_basis": basis, "historical_selected_country_count": 0, "country_frame_observability_score": None, "historical_country_counts_json": counts_json, "geometry_source_id": "", "geometry_source_version": "", "geometry_canonical_sha256": "", "failure_reason": ""})
                        continue

                    selected_count = int(counts[country])
                    score = observability_score(selected_count)
                    alpha3 = alpha2_to_alpha3_if_supported(country)
                    if alpha3 is None:
                        audit_rows.append({**attempt, "attempt_status": "provider_ineligible_before_freeze", "selected": False, "selected_country_code": country, "selected_country_alpha3": "", "country_selection_basis": basis, "historical_selected_country_count": selected_count, "country_frame_observability_score": score, "historical_country_counts_json": counts_json, "geometry_source_id": "", "geometry_source_version": "", "geometry_canonical_sha256": "", "failure_reason": "frozen ADM0 coverage ineligible"})
                        continue

                    try:
                        geom = geometry_provider(country)
                        geometry_digest = _geometry_digest_from_source_version(geom.source_version)
                    except Exception as exc:
                        audit_rows.append({**attempt, "attempt_status": "supported_geometry_provider_error_abort", "selected": False, "selected_country_code": country, "selected_country_alpha3": alpha3, "country_selection_basis": basis, "historical_selected_country_count": selected_count, "country_frame_observability_score": score, "historical_country_counts_json": counts_json, "geometry_source_id": "", "geometry_source_version": "", "geometry_canonical_sha256": "", "failure_reason": f"{type(exc).__name__}: {exc}"})
                        raise FreezeAborted(
                            f"supported geometry provider error for speciesKey={key}, country={country}; freeze aborted",
                            audit_rows,
                        ) from exc
                    if str(geom.country_code).strip().upper() != country:
                        raise FreezeAborted(
                            f"geometry provider country identity drift for speciesKey={key}, country={country}", audit_rows
                        )
                    audit_rows.append({**attempt, "attempt_status": "selected_provider_eligible_frame", "selected": True, "selected_country_code": country, "selected_country_alpha3": alpha3, "country_selection_basis": basis, "historical_selected_country_count": selected_count, "country_frame_observability_score": score, "historical_country_counts_json": counts_json, "geometry_source_id": str(geom.source_id), "geometry_source_version": str(geom.source_version), "geometry_canonical_sha256": geometry_digest, "failure_reason": ""})
                    chosen = {
                        "observability_frame_id": len(selected_rows) + 1,
                        "status": "frozen_provider_eligible_before_heldout",
                        "taxon_group": group,
                        "kingdomKey": int(TAXON_GROUPS[group]),
                        "geographic_stratum": str(geographic_stratum),
                        "region_name": str(region_name),
                        "region_cell_index": int(region_index),
                        "west": bounds[0], "south": bounds[1], "east": bounds[2], "north": bounds[3],
                        "speciesKey": key,
                        "scientific_name": name,
                        "coordinate_records": int(row["coordinate_records"]),
                        "record_count_stratum": int(stratum),
                        "identity_selection_hash": str(row["_identity_hash"]),
                        "declaration_attempt_rank": int(attempt_rank),
                        "declaration_status": "declared_provider_eligible",
                        "selected_country_code": country,
                        "selected_country_alpha3": alpha3,
                        "country_selection_basis": basis,
                        "historical_selected_country_count": selected_count,
                        "country_frame_observability_score": score,
                        "historical_country_counts_json": counts_json,
                        "geometry_source_id": str(geom.source_id),
                        "geometry_source_version": str(geom.source_version),
                        "geometry_canonical_sha256": geometry_digest,
                    }
                    break
                if chosen is None:
                    raise FreezeAborted(
                        f"no provider-eligible declarable fresh taxon for region={region_index}, group={group}, stratum={stratum}",
                        audit_rows,
                    )
                selected_rows.append(chosen)
                used_keys.add(int(chosen["speciesKey"]))
                used_names.add(str(chosen["scientific_name"]))

    selected = pd.DataFrame(selected_rows)
    audit = pd.DataFrame(audit_rows)
    _validate_complete_freeze(selected, audit, excluded_keys, excluded_names)
    return selected, audit


def _validate_complete_freeze(selected: pd.DataFrame, audit: pd.DataFrame, excluded_keys: set[int], excluded_names: set[str]) -> None:
    if len(selected) != 96 or selected["speciesKey"].nunique() != 96 or selected["scientific_name"].nunique() != 96:
        raise ValueError("provider-eligible observability cohort is not exactly 96 unique taxa")
    if selected["taxon_group"].value_counts().to_dict() != {"plant": 48, "animal": 48}:
        raise ValueError("provider-eligible taxon-group balance drift")
    for group in GROUP_ORDER:
        counts = selected.loc[selected["taxon_group"].eq(group), "record_count_stratum"].astype(int).value_counts().sort_index().to_dict()
        if counts != {0: 12, 1: 12, 2: 12, 3: 12}:
            raise ValueError(f"provider-eligible stratum balance drift for {group}: {counts}")
    per_cell = selected.groupby(["region_cell_index", "taxon_group"]).size()
    if len(per_cell) != 24 or not (per_cell == 4).all():
        raise ValueError("each region-group cell must contain exactly four provider-eligible frozen frames")
    if not selected["declaration_status"].eq("declared_provider_eligible").all():
        raise ValueError("all final frames must be provider-eligible declarations")
    if (selected["historical_selected_country_count"].astype(int) < 5).any():
        raise ValueError("final frame violates historical country minimum")
    if selected["selected_country_alpha3"].astype(str).str.len().ne(3).any():
        raise ValueError("final frame lacks provider-supported alpha3")
    for row in selected.itertuples(index=False):
        if alpha2_to_alpha3_if_supported(str(row.selected_country_code)) != str(row.selected_country_alpha3):
            raise ValueError("final frame provider coverage eligibility drift")
        if not math.isclose(float(row.country_frame_observability_score), observability_score(int(row.historical_selected_country_count)), rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("stored observability score drift")
    if set(selected["speciesKey"].astype(int)) & set(excluded_keys):
        raise ValueError("final cohort overlaps consumed speciesKey")
    if set(selected["scientific_name"].astype(str)) & set(excluded_names):
        raise ValueError("final cohort overlaps consumed scientific name")
    if int(audit["selected"].astype(bool).sum()) != 96:
        raise ValueError("audit must contain exactly 96 selected final frames")


def freeze(output: Path) -> dict[str, object]:
    cfg = protocol()
    output.mkdir(parents=True, exist_ok=True)
    try:
        selected, audit = select_frames()
    except FreezeAborted as exc:
        audit = pd.DataFrame(exc.audit_rows)
        if not audit.empty:
            audit.to_csv(output / "pre_freeze_declaration_attempts.csv", index=False)
        manifest = {
            "status": "provider_eligible_observability_freeze_aborted_before_complete_cohort",
            "protocol_fingerprint": EXPECTED_PROTOCOL_FINGERPRINT,
            "coverage_contract_fingerprint": EXPECTED_COVERAGE_FINGERPRINT,
            "issue": 169,
            "attempt_rows": int(len(audit)),
            "recent_outcomes_opened": False,
            "candidate_generation_run": False,
            "robust_support_run": False,
            "random_baseline_run": False,
            "replacement_after_freeze_allowed": False,
            "abort_reason": str(exc),
        }
        (output / "cohort_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        raise

    selected_path = output / "predeclared_observability_frames.csv"
    audit_path = output / "pre_freeze_declaration_attempts.csv"
    selected.to_csv(selected_path, index=False)
    audit.to_csv(audit_path, index=False)
    manifest = {
        "status": "provider_eligible_observability_confirmation_96_frames_frozen_before_heldout",
        "protocol_fingerprint": EXPECTED_PROTOCOL_FINGERPRINT,
        "coverage_contract_fingerprint": EXPECTED_COVERAGE_FINGERPRINT,
        "issue": 169,
        "identity_selection_seed": EXPECTED_IDENTITY_SEED,
        "frozen_frames": int(len(selected)),
        "unique_species_keys": int(selected["speciesKey"].nunique()),
        "taxon_group_counts": {str(k): int(v) for k, v in selected["taxon_group"].value_counts().sort_index().items()},
        "record_count_stratum_counts_by_group": {
            group: {str(int(k)): int(v) for k, v in selected.loc[selected["taxon_group"].eq(group), "record_count_stratum"].astype(int).value_counts().sort_index().items()}
            for group in GROUP_ORDER
        },
        "declaration_attempt_rows": int(len(audit)),
        "no_country_attempt_rows": int(audit["attempt_status"].eq("no_eligible_historical_country").sum()),
        "provider_ineligible_attempt_rows": int(audit["attempt_status"].eq("provider_ineligible_before_freeze").sum()),
        "selected_country_counts": {str(k): int(v) for k, v in selected["selected_country_code"].value_counts().sort_index().items()},
        "score_formula": str(cfg["country_declaration"]["score_formula"]),
        "score_min": float(selected["country_frame_observability_score"].min()),
        "score_max": float(selected["country_frame_observability_score"].max()),
        "frames_csv_sha256": hashlib.sha256(selected_path.read_bytes()).hexdigest(),
        "attempt_audit_csv_sha256": hashlib.sha256(audit_path.read_bytes()).hexdigest(),
        "recent_outcomes_opened": False,
        "candidate_generation_run": False,
        "robust_support_run": False,
        "random_baseline_run": False,
        "recall_or_lift_read": False,
        "replacement_after_freeze_allowed": False,
        "score_cutoff_selected": False,
        "scientific_candidate_method_changed": False,
    }
    (output / "cohort_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(freeze(args.output), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
