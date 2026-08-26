#!/usr/bin/env python3
"""Freeze a fresh 96-frame confirmation cohort for country-frame observability.

This stage is outcome-free. It may inspect fixed Japanese discovery cells,
species metadata/facets, historical 1900--2020 focal-species country facets,
pinned country geometry metadata, and identity-only exclusion files. It must
not query or inspect 2021--2025 records/facets, candidate patches, robust
worlds, random baselines, recall, or lift.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
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
from predeclare_country_framed_fresh_heterogeneity_confirmation import (
    exclusion_sets as base_exclusion_sets,
    protocol as base_fresh_protocol,
)
from predeclare_country_framed_integration_development_v1 import (
    _geometry_digest_from_source_version,
    choose_historical_country,
)

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "validation" / "acsp_country_frame_observability_confirmation_v1.json"
TERMINAL_FRESH_IDENTITY_PATH = (
    ROOT / "validation" / "acsp_country_framed_fresh_heterogeneity_confirmation_identities_v1.csv"
)
EXPECTED_PROTOCOL_FINGERPRINT = "f90f5f614bc370dd2fed40973ac11a3edcb3d88dfd6afebae8ce5de5a4bec547"
GROUP_ORDER = ("plant", "animal")


class FreezeAborted(RuntimeError):
    """Outcome-free freeze stopped before a complete 96-frame cohort existed."""

    def __init__(self, message: str, audit_rows: list[dict[str, object]]) -> None:
        super().__init__(message)
        self.audit_rows = [dict(row) for row in audit_rows]


def _git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("utf-8")
    return hashlib.sha1(header + data).hexdigest()


def protocol() -> dict[str, object]:
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    stored = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if stored != EXPECTED_PROTOCOL_FINGERPRINT or calculated != EXPECTED_PROTOCOL_FINGERPRINT:
        raise ValueError(
            "observability confirmation protocol fingerprint mismatch: "
            f"file={stored}, calculated={calculated}, expected={EXPECTED_PROTOCOL_FINGERPRINT}"
        )
    if payload["cohort"]["target_frames"] != 96:
        raise ValueError("observability confirmation target-frame drift")
    if payload["cohort"]["no_replacement_after_freeze"] is not True:
        raise ValueError("post-freeze replacement rule drift")
    if payload["execution"]["freeze_workflow_may_open_heldout"] is not False:
        raise ValueError("freeze workflow may not open heldout outcomes")
    if payload["decision"]["score_cutoff_creation_allowed"] is not False:
        raise ValueError("observability confirmation may not create a score cutoff")
    payload["protocol_fingerprint"] = stored
    return payload


def _terminal_fresh_identity_exclusions(
    path: Path = TERMINAL_FRESH_IDENTITY_PATH,
) -> tuple[set[int], set[str]]:
    cfg = protocol()["exclusions"]
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != str(cfg["terminal_fresh_identity_only_sha256"]):
        raise ValueError("terminal fresh identity-only exclusion SHA256 mismatch")
    if _git_blob_sha(data) != str(cfg["terminal_fresh_identity_only_git_blob_sha"]):
        raise ValueError("terminal fresh identity-only exclusion git-blob SHA mismatch")
    frame = pd.read_csv(path, usecols=["fresh_pair_id", "taxon_group", "speciesKey", "scientific_name"])
    if len(frame) != 48 or frame["speciesKey"].nunique() != 48 or frame["scientific_name"].nunique() != 48:
        raise ValueError("terminal fresh identity-only exclusion is not exactly 48 unique taxa")
    if frame["taxon_group"].value_counts().to_dict() != {"plant": 24, "animal": 24}:
        raise ValueError("terminal fresh identity-only exclusion group counts drift")
    return set(frame["speciesKey"].astype(int)), set(frame["scientific_name"].astype(str).str.strip())


def consumed_exclusion_sets() -> tuple[set[int], set[str]]:
    cfg = protocol()
    base = base_fresh_protocol()
    if base["protocol_fingerprint"] != cfg["exclusions"]["base_exclusion_protocol_fingerprint"]:
        raise ValueError("base fresh exclusion protocol fingerprint drift")
    keys, names = base_exclusion_sets(base["exclusions"])
    fresh_keys, fresh_names = _terminal_fresh_identity_exclusions()
    return set(keys) | fresh_keys, set(names) | fresh_names


def identity_hash(seed: int, region: int, group: str, stratum: int, species_key: int) -> str:
    token = f"{int(seed)}|{int(region)}|{group}|{int(stratum)}|{int(species_key)}".encode("utf-8")
    return hashlib.sha256(token).hexdigest()


def observability_score(historical_selected_country_count: int) -> float:
    count = int(historical_selected_country_count)
    if count < 0:
        raise ValueError("historical selected-country count must be nonnegative")
    return float(math.log1p(count))


def _normalize_discovery_frame(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"speciesKey", "scientific_name", "coordinate_records"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"fresh discovery frame missing columns: {sorted(missing)}")
    work = frame.copy()
    work["speciesKey"] = pd.to_numeric(work["speciesKey"], errors="raise").astype(int)
    work["scientific_name"] = work["scientific_name"].astype(str).str.strip()
    work["coordinate_records"] = pd.to_numeric(work["coordinate_records"], errors="raise").astype(int)
    return work.drop_duplicates(["speciesKey", "scientific_name"]).copy()


def _attempt_base(
    *,
    region_index: int,
    group: str,
    stratum: int,
    attempt_rank: int,
    identity_digest: str,
    row: pd.Series,
) -> dict[str, object]:
    return {
        "region_cell_index": int(region_index),
        "taxon_group": str(group),
        "record_count_stratum": int(stratum),
        "attempt_rank": int(attempt_rank),
        "identity_selection_hash": str(identity_digest),
        "speciesKey": int(row["speciesKey"]),
        "scientific_name": str(row["scientific_name"]),
        "coordinate_records": int(row["coordinate_records"]),
    }


def select_observability_frames(
    frame_provider: Callable[[tuple[float, float, float, float], int, int, int], pd.DataFrame] = taxon_frame,
    facet_provider: Callable[[int, tuple[int, int]], dict[str, int]] = fetch_country_facet_counts,
    geometry_provider: Callable[[str], object] = fetch_geoboundaries_country_geometry,
    *,
    excluded_keys: set[int] | None = None,
    excluded_names: set[str] | None = None,
    explicit_prefixes: tuple[str, ...] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Freeze 96 fresh declared frames using historical data only."""
    cfg = protocol()
    cohort_cfg = cfg["cohort"]
    country_cfg = cfg["country_declaration"]

    if list(HISTORICAL_YEARS) != list(country_cfg["historical_years"]):
        raise ValueError("historical-year range drift")
    if GEOBOUNDARIES_RELEASE_COMMIT != str(country_cfg["geometry_provider_release_commit"]):
        raise ValueError("geoBoundaries release commit drift")
    if GEOBOUNDARIES_SOURCE_ID != str(country_cfg["geometry_provider_source_id"]):
        raise ValueError("geoBoundaries source-id drift")
    if len(REGION_CELLS) != int(cohort_cfg["regions"]):
        raise ValueError("fixed discovery-region count drift")

    if excluded_keys is None or excluded_names is None:
        consumed_keys, consumed_names = consumed_exclusion_sets()
        if excluded_keys is None:
            excluded_keys = consumed_keys
        if excluded_names is None:
            excluded_names = consumed_names
    excluded_keys = set(int(x) for x in excluded_keys)
    excluded_names = set(str(x).strip() for x in excluded_names)

    if explicit_prefixes is None:
        explicit_prefixes = tuple(str(x) for x in cfg["exclusions"]["explicit_prefixes"])
    seed = int(cohort_cfg["selection_seed"])
    facet_limit = int(cohort_cfg["facet_limit"])
    minimum_records = int(cohort_cfg["minimum_records"])
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
                raw_frame = frame_provider(
                    bounds, int(TAXON_GROUPS[group]), facet_limit, minimum_records
                )
            except Exception as exc:
                audit_rows.append(
                    {
                        "region_cell_index": int(region_index),
                        "taxon_group": str(group),
                        "record_count_stratum": None,
                        "attempt_rank": 0,
                        "identity_selection_hash": "",
                        "speciesKey": None,
                        "scientific_name": "",
                        "coordinate_records": None,
                        "attempt_status": "discovery_provider_error_abort",
                        "selected": False,
                        "selected_country_code": "",
                        "country_selection_basis": "",
                        "historical_selected_country_count": 0,
                        "country_frame_observability_score": None,
                        "historical_country_counts_json": "{}",
                        "geometry_source_id": "",
                        "geometry_source_version": "",
                        "geometry_canonical_sha256": "",
                        "failure_reason": f"{type(exc).__name__}: {exc}",
                    }
                )
                raise FreezeAborted(
                    f"discovery provider error for region={region_index}, group={group}; freeze aborted",
                    audit_rows,
                ) from exc
            frame = _normalize_discovery_frame(raw_frame)
            frame = frame[
                ~frame["speciesKey"].isin(excluded_keys)
                & ~frame["scientific_name"].isin(excluded_names)
                & ~frame["scientific_name"].str.startswith(tuple(explicit_prefixes))
            ].copy()
            if len(frame) < 4:
                raise FreezeAborted(
                    f"fewer than four eligible fresh taxa for region={region_index}, group={group}",
                    audit_rows,
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
                        f"empty fresh pool for region={region_index}, group={group}, stratum={stratum}",
                        audit_rows,
                    )
                pool["_identity_hash"] = [
                    identity_hash(seed, region_index, group, stratum, key)
                    for key in pool["speciesKey"].astype(int)
                ]
                pool = pool.sort_values(
                    ["_identity_hash", "speciesKey", "scientific_name"], kind="mergesort"
                )

                chosen: dict[str, object] | None = None
                for attempt_rank, (_, row) in enumerate(pool.iterrows(), start=1):
                    key = int(row["speciesKey"])
                    name = str(row["scientific_name"])
                    digest = str(row["_identity_hash"])
                    attempt = _attempt_base(
                        region_index=region_index,
                        group=group,
                        stratum=stratum,
                        attempt_rank=attempt_rank,
                        identity_digest=digest,
                        row=row,
                    )
                    try:
                        counts = dict(
                            sorted(
                                (str(code).upper(), int(count))
                                for code, count in facet_provider(key, HISTORICAL_YEARS).items()
                            )
                        )
                    except Exception as exc:
                        audit_rows.append(
                            {
                                **attempt,
                                "attempt_status": "historical_provider_error_abort",
                                "selected": False,
                                "selected_country_code": "",
                                "country_selection_basis": "",
                                "historical_selected_country_count": 0,
                                "country_frame_observability_score": None,
                                "historical_country_counts_json": "{}",
                                "geometry_source_id": "",
                                "geometry_source_version": "",
                                "geometry_canonical_sha256": "",
                                "failure_reason": f"{type(exc).__name__}: {exc}",
                            }
                        )
                        raise FreezeAborted(
                            f"historical provider error for speciesKey={key}; freeze aborted",
                            audit_rows,
                        ) from exc

                    country, basis = choose_historical_country(
                        counts,
                        species_key=key,
                        minimum_count=minimum_country_count,
                        seed=country_seed,
                    )
                    counts_json = json.dumps(counts, sort_keys=True, separators=(",", ":"))
                    if country is None:
                        audit_rows.append(
                            {
                                **attempt,
                                "attempt_status": "no_eligible_historical_country",
                                "selected": False,
                                "selected_country_code": "",
                                "country_selection_basis": basis,
                                "historical_selected_country_count": 0,
                                "country_frame_observability_score": None,
                                "historical_country_counts_json": counts_json,
                                "geometry_source_id": "",
                                "geometry_source_version": "",
                                "geometry_canonical_sha256": "",
                                "failure_reason": "",
                            }
                        )
                        continue

                    selected_count = int(counts[country])
                    try:
                        geom = geometry_provider(country)
                        geometry_digest = _geometry_digest_from_source_version(geom.source_version)
                    except Exception as exc:
                        audit_rows.append(
                            {
                                **attempt,
                                "attempt_status": "geometry_provider_error_abort",
                                "selected": False,
                                "selected_country_code": country,
                                "country_selection_basis": basis,
                                "historical_selected_country_count": selected_count,
                                "country_frame_observability_score": observability_score(selected_count),
                                "historical_country_counts_json": counts_json,
                                "geometry_source_id": "",
                                "geometry_source_version": "",
                                "geometry_canonical_sha256": "",
                                "failure_reason": f"{type(exc).__name__}: {exc}",
                            }
                        )
                        raise FreezeAborted(
                            f"geometry provider error for speciesKey={key}, country={country}; freeze aborted",
                            audit_rows,
                        ) from exc

                    score = observability_score(selected_count)
                    audit_rows.append(
                        {
                            **attempt,
                            "attempt_status": "selected_declared_frame",
                            "selected": True,
                            "selected_country_code": country,
                            "country_selection_basis": basis,
                            "historical_selected_country_count": selected_count,
                            "country_frame_observability_score": score,
                            "historical_country_counts_json": counts_json,
                            "geometry_source_id": str(geom.source_id),
                            "geometry_source_version": str(geom.source_version),
                            "geometry_canonical_sha256": geometry_digest,
                            "failure_reason": "",
                        }
                    )
                    chosen = {
                        "observability_frame_id": len(selected_rows) + 1,
                        "status": "frozen_before_heldout",
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
                        "coordinate_records": int(row["coordinate_records"]),
                        "record_count_stratum": int(stratum),
                        "identity_selection_hash": digest,
                        "declaration_attempt_rank": int(attempt_rank),
                        "declaration_status": "declared",
                        "selected_country_code": country,
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
                        f"no declarable fresh taxon for region={region_index}, group={group}, stratum={stratum}",
                        audit_rows,
                    )
                selected_rows.append(chosen)
                used_keys.add(int(chosen["speciesKey"]))
                used_names.add(str(chosen["scientific_name"]))

    selected = pd.DataFrame(selected_rows)
    audit = pd.DataFrame(audit_rows)
    _validate_complete_freeze(selected, audit, excluded_keys, excluded_names)
    return selected, audit


def _validate_complete_freeze(
    selected: pd.DataFrame,
    audit: pd.DataFrame,
    excluded_keys: set[int],
    excluded_names: set[str],
) -> None:
    if len(selected) != 96 or selected["speciesKey"].nunique() != 96 or selected["scientific_name"].nunique() != 96:
        raise ValueError("observability confirmation cohort is not exactly 96 unique taxa")
    if selected["taxon_group"].value_counts().to_dict() != {"plant": 48, "animal": 48}:
        raise ValueError("observability confirmation taxon-group balance drift")
    for group in GROUP_ORDER:
        counts = (
            selected[selected["taxon_group"].eq(group)]["record_count_stratum"]
            .astype(int)
            .value_counts()
            .sort_index()
            .to_dict()
        )
        if counts != {0: 12, 1: 12, 2: 12, 3: 12}:
            raise ValueError(f"observability confirmation stratum balance drift for {group}: {counts}")
    per_cell = selected.groupby(["region_cell_index", "taxon_group"]).size()
    if len(per_cell) != 24 or not (per_cell == 4).all():
        raise ValueError("each region-group cell must contain exactly four frozen frames")
    if not selected["declaration_status"].eq("declared").all():
        raise ValueError("all 96 frozen frames must have successful country declarations")
    if (selected["historical_selected_country_count"].astype(int) < 5).any():
        raise ValueError("frozen frame violates historical country minimum")
    expected_scores = selected["historical_selected_country_count"].astype(int).map(observability_score)
    if not all(math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=1e-12) for a, b in zip(
        selected["country_frame_observability_score"], expected_scores
    )):
        raise ValueError("stored observability score does not equal frozen log1p definition")
    if set(selected["speciesKey"].astype(int)) & set(excluded_keys):
        raise ValueError("frozen observability cohort overlaps a consumed speciesKey")
    if set(selected["scientific_name"].astype(str)) & set(excluded_names):
        raise ValueError("frozen observability cohort overlaps a consumed scientific name")
    selected_audit = audit[audit["selected"].eq(True)]
    if len(selected_audit) != 96:
        raise ValueError("declaration-attempt audit must contain exactly 96 selected attempts")


def freeze(output: Path) -> dict[str, object]:
    cfg = protocol()
    output.mkdir(parents=True, exist_ok=True)
    try:
        selected, audit = select_observability_frames()
    except FreezeAborted as exc:
        audit = pd.DataFrame(exc.audit_rows)
        audit_path = output / "pre_freeze_declaration_attempts.csv"
        audit.to_csv(audit_path, index=False)
        manifest = {
            "status": "observability_confirmation_freeze_aborted_before_complete_cohort",
            "protocol_fingerprint": EXPECTED_PROTOCOL_FINGERPRINT,
            "issue": 163,
            "attempt_rows": int(len(audit)),
            "recent_outcomes_opened": False,
            "candidate_generation_run": False,
            "robust_support_run": False,
            "random_baseline_run": False,
            "replacement_after_freeze_allowed": False,
            "abort_reason": str(exc),
        }
        (output / "cohort_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        raise

    selected_path = output / "predeclared_observability_frames.csv"
    audit_path = output / "pre_freeze_declaration_attempts.csv"
    selected.to_csv(selected_path, index=False)
    audit.to_csv(audit_path, index=False)
    manifest = {
        "status": "observability_confirmation_96_frames_frozen_before_heldout",
        "protocol_fingerprint": EXPECTED_PROTOCOL_FINGERPRINT,
        "issue": 163,
        "frozen_frames": int(len(selected)),
        "unique_species_keys": int(selected["speciesKey"].nunique()),
        "taxon_group_counts": {
            str(k): int(v) for k, v in selected["taxon_group"].value_counts().sort_index().items()
        },
        "record_count_stratum_counts_by_group": {
            group: {
                str(int(k)): int(v)
                for k, v in selected[selected["taxon_group"].eq(group)]["record_count_stratum"]
                .astype(int)
                .value_counts()
                .sort_index()
                .items()
            }
            for group in GROUP_ORDER
        },
        "declaration_attempt_rows": int(len(audit)),
        "no_country_attempt_rows": int(audit["attempt_status"].eq("no_eligible_historical_country").sum()),
        "selected_country_counts": {
            str(k): int(v)
            for k, v in selected["selected_country_code"].value_counts().sort_index().items()
        },
        "score_formula": str(cfg["country_declaration"]["score_formula"]),
        "score_min": float(selected["country_frame_observability_score"].min()),
        "score_max": float(selected["country_frame_observability_score"].max()),
        "frames_csv_sha256": hashlib.sha256(selected_path.read_bytes()).hexdigest(),
        "attempt_audit_csv_sha256": hashlib.sha256(audit_path.read_bytes()).hexdigest(),
        "terminal_fresh_identity_only_sha256": str(
            cfg["exclusions"]["terminal_fresh_identity_only_sha256"]
        ),
        "recent_outcomes_opened": False,
        "candidate_generation_run": False,
        "robust_support_run": False,
        "random_baseline_run": False,
        "recall_or_lift_read": False,
        "replacement_after_freeze_allowed": False,
        "score_cutoff_selected": False,
        "scientific_candidate_method_changed": False,
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
