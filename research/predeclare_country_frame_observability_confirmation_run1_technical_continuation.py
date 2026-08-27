#!/usr/bin/env python3
"""Continue the issue #163 run-1 freeze after a bound HK geometry provider abort.

This is not a new scientific cohort.  Before any selection beyond the source
abort point, the exact 77-attempt identity/country/score prefix from corrected
workflow run 33028727560 is reproduced and checked against a committed digest.
The same cached historical discovery and country-facet responses are then used
to continue the deterministic freeze.  The only recovery is the separately
frozen HK geometry adapter; taxa, selected countries, score, endpoint, identity
order, and 2021--2025 access boundary are unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Callable, Sequence

import pandas as pd

import geoboundaries_v6_provider as original_geometry
from geoboundaries_v6_hk_technical_recovery import (
    HK_COUNTRY_CODE,
    HK_RECOVERY_SOURCE_ID,
    fetch_country_geometry_with_hk_recovery,
)
import predeclare_country_frame_observability_confirmation_historical_discovery as corrected

ROOT = Path(__file__).resolve().parents[1]
PREFIX_BINDING_PATH = (
    ROOT / "validation" / "acsp_country_frame_observability_confirmation_run1_abort_prefix_v1.json"
)
GEOMETRY_RECOVERY_PATH = (
    ROOT / "validation" / "acsp_country_frame_observability_confirmation_hk_geometry_recovery_v1.json"
)
EXPECTED_PREFIX_BINDING_FINGERPRINT = "ca89763bca9b62abd77c39592a39160112ab32f76419fb9f5da12e6b276491ff"
EXPECTED_GEOMETRY_RECOVERY_FINGERPRINT = "f16ba90f1282ba2ed6fa8dd010ffda1f6a82b4bf8c2247efd35a640d5d9b6f4f"
SOURCE_RUN_ID = 33028727560
SOURCE_ABORT_ARTIFACT_ID = 9629491740
SOURCE_PREFIX_ROWS = 77
SOURCE_SELECTED_BEFORE_ABORT = 76
SOURCE_FAILURE_SPECIES_KEY = 5729409
SOURCE_FAILURE_COUNTRY = "HK"

_INT_CORE_COLUMNS = {
    "region_cell_index",
    "record_count_stratum",
    "attempt_rank",
    "speciesKey",
    "coordinate_records",
    "historical_selected_country_count",
}


class PrefixMismatch(RuntimeError):
    """The live historical providers no longer reproduce the bound run-1 prefix."""

    def __init__(self, message: str, audit: pd.DataFrame | None = None) -> None:
        super().__init__(message)
        self.audit = pd.DataFrame() if audit is None else audit.copy()


def _load_fingerprinted(path: Path, fingerprint_field: str, expected: str) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    stored = str(payload.pop(fingerprint_field, ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if stored != expected or calculated != expected:
        raise ValueError(
            f"{path.name} fingerprint mismatch: file={stored}, calculated={calculated}, expected={expected}"
        )
    payload[fingerprint_field] = stored
    return payload


def prefix_binding() -> dict[str, object]:
    payload = _load_fingerprinted(
        PREFIX_BINDING_PATH, "binding_fingerprint", EXPECTED_PREFIX_BINDING_FINGERPRINT
    )
    source = payload["source_workflow_run"]
    artifact = payload["source_abort_artifact"]
    prefix = payload["prefix_contract"]
    scope = payload["technical_continuation_scope"]
    if int(source["run_id"]) != SOURCE_RUN_ID or int(source["run_number"]) != 1:
        raise ValueError("run-1 prefix binding source run drift")
    if source["contract_passed"] is not True or source["freeze_completed"] is not False:
        raise ValueError("run-1 prefix binding source status drift")
    if source["heldout_outcomes_opened"] is not False:
        raise ValueError("source run opened heldout outcomes")
    if int(artifact["artifact_id"]) != SOURCE_ABORT_ARTIFACT_ID:
        raise ValueError("run-1 abort artifact id drift")
    if int(prefix["attempt_rows"]) != SOURCE_PREFIX_ROWS:
        raise ValueError("run-1 prefix row-count drift")
    if int(prefix["successful_selected_frames_before_failure"]) != SOURCE_SELECTED_BEFORE_ABORT:
        raise ValueError("run-1 selected-prefix count drift")
    if int(prefix["failure_row_speciesKey"]) != SOURCE_FAILURE_SPECIES_KEY:
        raise ValueError("run-1 failure speciesKey drift")
    if str(prefix["failure_row_selected_country_code"]) != SOURCE_FAILURE_COUNTRY:
        raise ValueError("run-1 failure country drift")
    if scope["may_change_identity_or_country"] is not False or scope["may_skip_failure_row"] is not False:
        raise ValueError("technical continuation identity/country boundary drift")
    if scope["may_open_2021_2025"] is not False or scope["may_change_score_or_endpoint"] is not False:
        raise ValueError("technical continuation scientific boundary drift")
    return payload


def geometry_recovery() -> dict[str, object]:
    payload = _load_fingerprinted(
        GEOMETRY_RECOVERY_PATH, "recovery_fingerprint", EXPECTED_GEOMETRY_RECOVERY_FINGERPRINT
    )
    if payload["parent_protocol_fingerprint"] != corrected.base.EXPECTED_PROTOCOL_FINGERPRINT:
        raise ValueError("HK geometry recovery parent protocol drift")
    if payload["boundary_correction_fingerprint"] != corrected.EXPECTED_CORRECTION_FINGERPRINT:
        raise ValueError("HK geometry recovery boundary correction drift")
    if payload["run1_abort_prefix_binding_fingerprint"] != EXPECTED_PREFIX_BINDING_FINGERPRINT:
        raise ValueError("HK geometry recovery run-1 binding drift")
    failure = payload["failure_frame"]
    recovery = payload["geometry_recovery"]
    invariants = payload["scientific_invariants"]
    if int(failure["speciesKey"]) != SOURCE_FAILURE_SPECIES_KEY:
        raise ValueError("HK geometry recovery failure species drift")
    if str(failure["selected_country_code"]) != SOURCE_FAILURE_COUNTRY:
        raise ValueError("HK geometry recovery failure country drift")
    if failure["identity_or_country_may_change"] is not False:
        raise ValueError("HK geometry recovery may not alter identity/country")
    if str(recovery["release_commit"]) != original_geometry.GEOBOUNDARIES_RELEASE_COMMIT:
        raise ValueError("HK geometry recovery release commit drift")
    if str(recovery["result_country_code"]) != HK_COUNTRY_CODE:
        raise ValueError("HK geometry recovery result country drift")
    for key in ("alternate_provider_allowed", "country_substitution_allowed", "taxon_replacement_allowed"):
        if recovery[key] is not False:
            raise ValueError(f"HK geometry recovery guard drift: {key}")
    for key in ("score_changed", "endpoint_changed", "country_declaration_rule_changed", "identity_hash_or_order_changed"):
        if invariants[key] is not False:
            raise ValueError(f"HK geometry recovery scientific invariant drift: {key}")
    if invariants["heldout_outcomes_opened"] is not False:
        raise ValueError("HK geometry recovery opened heldout outcomes")
    return payload


def _normalize_core_value(column: str, value: object) -> object:
    if column in _INT_CORE_COLUMNS:
        return None if pd.isna(value) or value == "" else int(value)
    if column == "country_frame_observability_score":
        return None if pd.isna(value) or value == "" else format(float(value), ".17g")
    if column == "historical_country_counts_json":
        if pd.isna(value) or value == "":
            return {}
        return json.loads(str(value))
    if pd.isna(value):
        return ""
    return str(value)


def selection_core_sha256(audit: pd.DataFrame, columns: Sequence[str]) -> str:
    rows: list[str] = []
    for _, row in audit.iterrows():
        payload = {column: _normalize_core_value(column, row[column]) for column in columns}
        rows.append(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    encoded = (("\n".join(rows) + "\n") if rows else "").encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify_source_prefix(audit: pd.DataFrame) -> str:
    binding = prefix_binding()
    prefix = binding["prefix_contract"]
    columns = [str(x) for x in prefix["selection_core_columns"]]
    if len(audit) < SOURCE_PREFIX_ROWS:
        raise PrefixMismatch(
            f"technical continuation reached only {len(audit)} attempts before source prefix length {SOURCE_PREFIX_ROWS}",
            audit,
        )
    source = audit.iloc[:SOURCE_PREFIX_ROWS].copy()
    digest = selection_core_sha256(source, columns)
    expected = str(prefix["selection_core_sha256"])
    if digest != expected:
        raise PrefixMismatch(
            f"run-1 selection prefix mismatch: calculated={digest}, expected={expected}", source
        )
    last = source.iloc[-1]
    if int(last["speciesKey"]) != SOURCE_FAILURE_SPECIES_KEY:
        raise PrefixMismatch("run-1 failure-row speciesKey mismatch", source)
    if str(last["selected_country_code"]) != SOURCE_FAILURE_COUNTRY:
        raise PrefixMismatch("run-1 failure-row country mismatch", source)
    return digest


class HistoricalProviderCache:
    """Reuse the exact preflight historical responses during continuation."""

    def __init__(self) -> None:
        self.frames: dict[tuple[object, ...], pd.DataFrame] = {}
        self.facets: dict[tuple[int, tuple[int, int]], dict[str, int]] = {}
        self.geometries: dict[str, object] = {}

    def frame(self, bounds, kingdom_key, facet_limit, minimum_records) -> pd.DataFrame:
        key = (tuple(float(x) for x in bounds), int(kingdom_key), int(facet_limit), int(minimum_records))
        if key not in self.frames:
            self.frames[key] = corrected.historical_taxon_frame(
                bounds, kingdom_key, facet_limit, minimum_records
            ).copy()
        return self.frames[key].copy()

    def facet(self, species_key: int, years: tuple[int, int]) -> dict[str, int]:
        key = (int(species_key), (int(years[0]), int(years[1])))
        if key not in self.facets:
            self.facets[key] = dict(corrected.base.fetch_country_facet_counts(species_key, years))
        return dict(self.facets[key])

    def source_prefix_geometry(self, country_code: str):
        code = str(country_code).strip().upper()
        if code == SOURCE_FAILURE_COUNTRY:
            raise RuntimeError("bound source-run HK geometry abort sentinel")
        if code not in self.geometries:
            self.geometries[code] = original_geometry.fetch_geoboundaries_country_geometry(code)
        return self.geometries[code]

    def continuation_geometry(self, country_code: str):
        code = str(country_code).strip().upper()
        if code == SOURCE_FAILURE_COUNTRY:
            return fetch_country_geometry_with_hk_recovery(code)
        if code not in self.geometries:
            self.geometries[code] = original_geometry.fetch_geoboundaries_country_geometry(code)
        return self.geometries[code]


def reproduce_source_prefix(cache: HistoricalProviderCache) -> pd.DataFrame:
    excluded_keys, excluded_names = corrected.corrected_exclusion_sets()
    try:
        corrected.base.select_observability_frames(
            frame_provider=cache.frame,
            facet_provider=cache.facet,
            geometry_provider=cache.source_prefix_geometry,
            excluded_keys=excluded_keys,
            excluded_names=excluded_names,
        )
    except corrected.base.FreezeAborted as exc:
        audit = pd.DataFrame(exc.audit_rows)
        digest = verify_source_prefix(audit)
        if len(audit) != SOURCE_PREFIX_ROWS:
            raise PrefixMismatch(
                f"source preflight did not stop exactly at row {SOURCE_PREFIX_ROWS}", audit
            )
        last = audit.iloc[-1]
        if str(last["attempt_status"]) != "geometry_provider_error_abort":
            raise PrefixMismatch("source preflight did not stop at the bound geometry abort", audit)
        if digest != prefix_binding()["prefix_contract"]["selection_core_sha256"]:
            raise PrefixMismatch("source prefix digest drift after verification", audit)
        return audit
    raise PrefixMismatch("source preflight unexpectedly completed instead of stopping at bound HK row")


def _continuation_manifest_fields() -> dict[str, object]:
    binding = prefix_binding()
    recovery = geometry_recovery()
    return {
        **corrected._boundary_manifest_fields(),
        "technical_continuation_of_run1": True,
        "new_scientific_cohort": False,
        "source_corrected_run_id": SOURCE_RUN_ID,
        "source_abort_artifact_id": SOURCE_ABORT_ARTIFACT_ID,
        "source_abort_artifact_digest": str(binding["source_abort_artifact"]["artifact_digest"]),
        "run1_abort_prefix_binding_fingerprint": EXPECTED_PREFIX_BINDING_FINGERPRINT,
        "source_prefix_attempt_rows": SOURCE_PREFIX_ROWS,
        "source_prefix_selected_frames": SOURCE_SELECTED_BEFORE_ABORT,
        "source_prefix_selection_core_sha256": str(binding["prefix_contract"]["selection_core_sha256"]),
        "source_prefix_reproduced_before_continuation": True,
        "hk_geometry_recovery_fingerprint": EXPECTED_GEOMETRY_RECOVERY_FINGERPRINT,
        "hk_geometry_recovery_country_code": HK_COUNTRY_CODE,
        "hk_geometry_recovery_source_id": HK_RECOVERY_SOURCE_ID,
        "hk_geometry_recovery_release_commit": str(recovery["geometry_recovery"]["release_commit"]),
        "identity_or_country_replaced_for_recovery": False,
    }


def _write_abort(output: Path, status: str, reason: str, audit: pd.DataFrame | None = None) -> None:
    audit = pd.DataFrame() if audit is None else audit.copy()
    if not audit.empty:
        audit.to_csv(output / "pre_freeze_declaration_attempts.csv", index=False)
    manifest = {
        "status": status,
        "protocol_fingerprint": corrected.base.EXPECTED_PROTOCOL_FINGERPRINT,
        "issue": 163,
        **_continuation_manifest_fields(),
        "attempt_rows": int(len(audit)),
        "recent_outcomes_opened": False,
        "candidate_generation_run": False,
        "robust_support_run": False,
        "random_baseline_run": False,
        "replacement_after_freeze_allowed": False,
        "abort_reason": str(reason),
    }
    (output / "cohort_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def freeze(output: Path) -> dict[str, object]:
    corrected.base.protocol()
    corrected.correction()
    corrected.exposure_binding()
    prefix_binding()
    geometry_recovery()
    output.mkdir(parents=True, exist_ok=True)

    cache = HistoricalProviderCache()
    try:
        reproduce_source_prefix(cache)
    except PrefixMismatch as exc:
        _write_abort(
            output,
            "observability_confirmation_run1_technical_continuation_prefix_mismatch",
            str(exc),
            exc.audit,
        )
        raise

    excluded_keys, excluded_names = corrected.corrected_exclusion_sets()
    try:
        selected, audit = corrected.base.select_observability_frames(
            frame_provider=cache.frame,
            facet_provider=cache.facet,
            geometry_provider=cache.continuation_geometry,
            excluded_keys=excluded_keys,
            excluded_names=excluded_names,
        )
    except corrected.base.FreezeAborted as exc:
        audit = pd.DataFrame(exc.audit_rows)
        try:
            verify_source_prefix(audit)
        except PrefixMismatch as prefix_exc:
            _write_abort(
                output,
                "observability_confirmation_run1_technical_continuation_prefix_mismatch",
                str(prefix_exc),
                audit,
            )
            raise prefix_exc from exc
        _write_abort(
            output,
            "observability_confirmation_run1_technical_continuation_aborted_before_complete_cohort",
            str(exc),
            audit,
        )
        raise

    prefix_digest = verify_source_prefix(audit)
    selected_path = output / "predeclared_observability_frames.csv"
    audit_path = output / "pre_freeze_declaration_attempts.csv"
    selected.to_csv(selected_path, index=False)
    audit.to_csv(audit_path, index=False)
    cfg = corrected.base.protocol()
    manifest = {
        "status": "observability_confirmation_96_frames_frozen_before_heldout_run1_technical_continuation",
        "protocol_fingerprint": corrected.base.EXPECTED_PROTOCOL_FINGERPRINT,
        "issue": 163,
        **_continuation_manifest_fields(),
        "source_prefix_selection_core_sha256_reproduced": prefix_digest,
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
            for group in corrected.base.GROUP_ORDER
        },
        "declaration_attempt_rows": int(len(audit)),
        "no_country_attempt_rows": int(
            audit["attempt_status"].eq("no_eligible_historical_country").sum()
        ),
        "selected_country_counts": {
            str(k): int(v)
            for k, v in selected["selected_country_code"].value_counts().sort_index().items()
        },
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
