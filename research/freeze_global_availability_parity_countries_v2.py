#!/usr/bin/env python3
"""Stage 2 v2 for issue #197: freeze historical-only country plans for 48 identities.

This stage consumes the committed, byte-pinned stage-1-v2 identity cohort and
its authoritative receipt. Only after those hashes and information-boundary
flags verify does it open historical 1900-2020 country facets for exactly the
48 frozen taxa, once per taxon, and apply the provider-supported evidence-first
automatic country planner.

It does not open country geometry, candidate patches, robust support, random
baselines, or 2021-2025 heldout data. Technical provider errors abort instead
of replacing a taxon or being mislabeled as biological unavailability.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time
from typing import Callable, Mapping

import pandas as pd

from acsp.discovery.country_frames import CountryFrameState, plan_automatic_global_country
from geographic_framing_country_registry_v3 import HISTORICAL_YEARS, fetch_country_facet_counts
from geoboundaries_v6_coverage_contract import alpha2_to_alpha3_if_supported, load_iso_mapping

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "validation" / "acsp_global_availability_parity_confirmation_v2.json"
DEFAULT_IDENTITIES_PATH = ROOT / "validation" / "acsp_global_availability_parity_identities_v2.csv"
DEFAULT_RECEIPT_PATH = ROOT / "validation" / "acsp_global_availability_parity_identity_freeze_v2_result.json"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: object) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def protocol() -> dict[str, object]:
    value = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    if value.get("protocol_id") != "acsp_global_availability_parity_confirmation_v2":
        raise ValueError("availability-parity v2 protocol id drift")
    if list(value["automatic_country_frame"]["historical_years"]) != list(HISTORICAL_YEARS):
        raise ValueError("historical year range drift")
    if value["automatic_country_frame"]["heldout_used"] is not False:
        raise ValueError("country freeze may not use heldout")
    if value["cohort"]["no_taxon_replacement_after_identity_freeze"] is not True:
        raise ValueError("post-identity replacement rule drift")
    return value


def supported_alpha2_codes() -> set[str]:
    mapping = load_iso_mapping()
    return {code for code in mapping if alpha2_to_alpha3_if_supported(code) is not None}


def verify_stage1(
    identities_path: Path = DEFAULT_IDENTITIES_PATH,
    receipt_path: Path = DEFAULT_RECEIPT_PATH,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Verify the committed stage-1-v2 cohort before any historical query."""
    identities_path = Path(identities_path)
    receipt_path = Path(receipt_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    if receipt.get("schema_version") != "acsp-global-availability-parity-identity-freeze-v2-result":
        raise ValueError("stage1-v2 receipt schema drift")
    if receipt.get("status") != "IDENTITY_FREEZE_COMPLETE_PRE_HISTORICAL_COUNTRY_QUERY_V2":
        raise ValueError("stage1-v2 receipt is not a complete identity-only freeze")
    if receipt.get("committed_identity_file") != "validation/acsp_global_availability_parity_identities_v2.csv":
        raise ValueError("stage1-v2 committed identity path drift")

    expected_sha = str(receipt.get("artifact", {}).get("identities_csv_sha256", ""))
    if _sha256_file(identities_path) != expected_sha:
        raise ValueError("stage1-v2 committed identity SHA256 mismatch")

    boundary = receipt.get("information_boundary")
    if not isinstance(boundary, dict):
        raise ValueError("stage1-v2 receipt information boundary missing")
    for key in (
        "focal_historical_country_facets_opened",
        "country_geometry_opened",
        "candidate_generation_run",
        "heldout_2021_2025_opened",
        "robust_support_run",
        "random_baseline_run",
        "recall_or_lift_read",
        "outcome_driven_tuning",
        "validated_japan_core_changed",
    ):
        if boundary.get(key) is not False:
            raise ValueError(f"stage1-v2 information boundary violated: {key}")

    identities = pd.read_csv(identities_path)
    required = {
        "availability_pair_id",
        "taxon_group",
        "record_count_stratum",
        "speciesKey",
        "scientific_name",
        "identity_selection_hash",
    }
    missing = sorted(required.difference(identities.columns))
    if missing:
        raise ValueError(f"stage1-v2 identities missing columns: {missing}")
    if len(identities) != 48 or identities["speciesKey"].nunique() != 48 or identities["scientific_name"].nunique() != 48:
        raise ValueError("stage1-v2 identity artifact is not 48 unique taxa")
    if identities["taxon_group"].value_counts().to_dict() != {"plant": 24, "animal": 24}:
        raise ValueError("stage1-v2 identity group balance drift")
    for group in ("plant", "animal"):
        counts = (
            identities.loc[identities["taxon_group"].eq(group), "record_count_stratum"]
            .astype(int).value_counts().sort_index().to_dict()
        )
        if counts != {0: 6, 1: 6, 2: 6, 3: 6}:
            raise ValueError(f"stage1-v2 identity stratum balance drift for {group}: {counts}")

    records = identities.sort_values("availability_pair_id", kind="mergesort")[[
        "availability_pair_id",
        "taxon_group",
        "record_count_stratum",
        "speciesKey",
        "scientific_name",
        "identity_selection_hash",
    ]].to_dict(orient="records")
    if _canonical_sha256(records) != str(receipt.get("identity_canonical_sha256", "")):
        raise ValueError("stage1-v2 identity canonical digest mismatch")

    return identities.sort_values("availability_pair_id", kind="mergesort").reset_index(drop=True), receipt


def fetch_historical_counts_once(
    species_key: int,
    *,
    facet_provider: Callable[[int, tuple[int, int]], Mapping[str, int]] = fetch_country_facet_counts,
    attempts: int = 4,
    base_sleep_seconds: float = 0.4,
) -> dict[str, int]:
    last_error: Exception | None = None
    for attempt in range(int(attempts)):
        try:
            return dict(
                sorted(
                    (str(code).upper(), int(count))
                    for code, count in facet_provider(int(species_key), HISTORICAL_YEARS).items()
                )
            )
        except Exception as exc:
            last_error = exc
            if attempt + 1 < int(attempts):
                time.sleep(float(base_sleep_seconds) * (2 ** attempt))
    assert last_error is not None
    raise RuntimeError(
        f"historical provider failed after {attempts} attempts for speciesKey={int(species_key)}: "
        f"{type(last_error).__name__}: {last_error}"
    ) from last_error


def freeze_country_plans(
    identities: pd.DataFrame,
    *,
    facet_provider: Callable[[int, tuple[int, int]], Mapping[str, int]] = fetch_country_facet_counts,
) -> tuple[pd.DataFrame, dict[str, object]]:
    cfg = protocol()
    supported = supported_alpha2_codes()
    minimum = int(cfg["automatic_country_frame"]["historical_country_min_count"])
    rows: list[dict[str, object]] = []
    query_count = 0

    for row in identities.sort_values("availability_pair_id", kind="mergesort").itertuples(index=False):
        key = int(row.speciesKey)
        counts = fetch_historical_counts_once(key, facet_provider=facet_provider)
        query_count += 1
        plan = plan_automatic_global_country(
            counts,
            provider_supported_country_codes=supported,
            historical_min_count=minimum,
            tie_break_seed=int(cfg["cohort"]["selection_seed"]),
        )
        selected = str(plan.selected_country_code or "")
        selected_count = int(counts.get(selected, 0)) if selected else 0
        rows.append(
            {
                **row._asdict(),
                "country_plan_state": plan.state.value,
                "selected_country_code": selected,
                "historical_selected_country_count": selected_count,
                "historical_country_count": int(len(counts)),
                "historical_country_counts_json": json.dumps(counts, sort_keys=True, separators=(",", ":")),
                "country_plan_candidate_audit_json": json.dumps(
                    plan.as_dict()["candidates"], sort_keys=True, separators=(",", ":")
                ),
            }
        )

    frame = pd.DataFrame(rows)
    if query_count != len(identities):
        raise AssertionError("historical query count drift")
    state_counts = frame["country_plan_state"].value_counts().to_dict()
    ready = int(state_counts.get(CountryFrameState.READY.value, 0))
    audit = {
        "schema_version": "global-availability-parity-country-freeze-v2",
        "status": "HISTORICAL_COUNTRY_PLANS_FROZEN_PRE_GEOMETRY_PRE_CANDIDATES_PRE_HELDOUT_V2",
        "taxon_count": int(len(identities)),
        "historical_facet_query_count": int(query_count),
        "historical_facet_query_mode": "one focal query per already-frozen v2 taxon; sequential with bounded retry",
        "ready_country_count": ready,
        "state_counts": {str(key): int(value) for key, value in state_counts.items()},
        "country_plan_canonical_sha256": _canonical_sha256(
            frame[[
                "availability_pair_id",
                "speciesKey",
                "scientific_name",
                "country_plan_state",
                "selected_country_code",
                "historical_selected_country_count",
            ]].to_dict(orient="records")
        ),
        "country_geometry_opened": False,
        "candidate_generation_run": False,
        "heldout_2021_2025_opened": False,
        "robust_support_run": False,
        "random_baseline_run": False,
        "recall_or_lift_read": False,
        "field_outcomes_used": False,
        "country_selection_uses_historical_evidence_only": True,
        "taxon_replacement_after_identity_freeze": False,
        "validated_japan_core_changed": False,
    }
    return frame, audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--identities", type=Path, default=DEFAULT_IDENTITIES_PATH)
    parser.add_argument("--identity-receipt", type=Path, default=DEFAULT_RECEIPT_PATH)
    parser.add_argument("--country-output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    args = parser.parse_args()

    identities, _ = verify_stage1(args.identities, args.identity_receipt)
    plans, audit = freeze_country_plans(identities)
    args.country_output.parent.mkdir(parents=True, exist_ok=True)
    plans.to_csv(args.country_output, index=False)
    args.audit_output.parent.mkdir(parents=True, exist_ok=True)
    args.audit_output.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
