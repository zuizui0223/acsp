#!/usr/bin/env python3
"""Historical-only preflight for the frozen Japan38 broad-frame confirmation v2.

The scientific candidate-frame mechanics are intentionally reused from the
already-consumed v1 preflight.  This module changes only cohort construction:
it expands every include_v2 row from the frozen Japan38 roster and permits the
existing 12 fixed Japanese regions for training-only region selection.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acsp.taxon_patches import VALIDATED_JAPAN_REGIONS
from prepare_cirsium_disjoint_broad_frame_replication_v1 import _prepare_unit

CONTRACT = ROOT / "validation" / "cirsium_japan38_broad_frame_confirmation_v2.json"
ROSTER = ROOT / "validation" / "cirsium_japan38_disjoint_v2_roster.csv"
EXPECTED_ROSTER_ROWS = 38
EXPECTED_INCLUDED_TAXA = 31


def _truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def load_frozen_units() -> list[dict[str, object]]:
    roster = pd.read_csv(ROSTER)
    required = {"member_id", "paper_taxon_concept", "provider_query_name", "include_v2", "exclusion_reason"}
    missing = sorted(required.difference(roster.columns))
    if missing:
        raise ValueError(f"Japan38 roster missing columns: {missing}")
    if len(roster) != EXPECTED_ROSTER_ROWS:
        raise ValueError(f"Japan38 roster row-count drift: {len(roster)}")
    if roster["member_id"].astype(str).nunique() != EXPECTED_ROSTER_ROWS:
        raise ValueError("Japan38 roster member IDs are not unique")

    include = roster["include_v2"].map(_truthy)
    if int(include.sum()) != EXPECTED_INCLUDED_TAXA:
        raise ValueError(f"Japan38 included-taxon count drift: {int(include.sum())}")
    excluded = roster.loc[~include]
    if excluded["exclusion_reason"].fillna("").astype(str).str.strip().eq("").any():
        raise ValueError("every excluded Japan38 row must retain an explicit exclusion reason")

    region_ids = [str(row[0]) for row in VALIDATED_JAPAN_REGIONS]
    if len(region_ids) != 12 or len(set(region_ids)) != 12:
        raise ValueError("validated Japanese region registry drift")

    units: list[dict[str, object]] = []
    for row in roster.loc[include].itertuples(index=False):
        species = str(row.provider_query_name).strip()
        if not species:
            raise ValueError(f"empty provider query name for {row.member_id}")
        units.append(
            {
                "unit_id": str(row.member_id),
                "species": species,
                "paper_taxon_concept": str(row.paper_taxon_concept),
                "allowed_fixed_regions": list(region_ids),
            }
        )
    return units


def run() -> dict[str, object]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if contract.get("status") != "FROZEN_BEFORE_2021_2025_OUTCOME_FETCH":
        raise ValueError("Japan38 confirmation contract is not pre-outcome frozen")
    if int(contract.get("cohort", {}).get("declared_taxa", -1)) != EXPECTED_INCLUDED_TAXA:
        raise ValueError("Japan38 contract declared-taxon count drift")

    units = load_frozen_units()
    results = [_prepare_unit(unit, contract) for unit in units]
    return {
        "schema_version": "cirsium-japan38-broad-frame-confirmation-preflight-v2",
        "status": "HISTORICAL_ONLY_PREFLIGHT_COMPLETE",
        "source_contract": str(CONTRACT.relative_to(ROOT)),
        "source_roster": str(ROSTER.relative_to(ROOT)),
        "recent_outcomes_fetched": False,
        "validated_japan_product_changed": False,
        "automatic_global_adapter_changed": False,
        "declared_taxa": EXPECTED_INCLUDED_TAXA,
        "units_frozen": int(sum(row.get("status") == "PREOUTCOME_CANDIDATE_UNIVERSES_FROZEN" for row in results)),
        "units_no_historical_anchor": int(sum(row.get("status") == "NO_HISTORICAL_ANCHOR" for row in results)),
        "units_provider_failure": int(sum(str(row.get("status", "")).endswith("PROVIDER_FAILURE") for row in results)),
        "units": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = run()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
