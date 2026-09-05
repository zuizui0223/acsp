#!/usr/bin/env python3
"""Public-safe preflight for the first three Cirsium private-frame archetypes.

This does not build coordinate-bearing frames. It reads only the frozen public
cohort/source-requirement tables and reports which private source snapshots must
exist before CIR03 (local alpine), CIR08 (local coastal), and CIR02 (sentinel
uncertainty-footprint) can be executed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ARCHETYPES = ("CIR03", "CIR08", "CIR02")
SOURCE_FLAGS = (
    ("requires_primary_anchor_geometry", "primary_anchor_geometry"),
    ("requires_gsi_dem", "gsi_dem_snapshot"),
    ("requires_esa_worldcover_2021", "esa_worldcover_2021_snapshot"),
    ("requires_gsi_coastline", "gsi_coastline_snapshot"),
    ("requires_broad_sentinel_support", "sentinel_support_input"),
    ("requires_target_component_id", "target_ecological_component"),
)


def _truth(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def build_preflight(
    requirements: pd.DataFrame,
    cohort: pd.DataFrame,
    *,
    unit_ids: tuple[str, ...] = ARCHETYPES,
) -> tuple[pd.DataFrame, dict[str, object]]:
    if requirements["cohort_unit_id"].duplicated().any():
        raise ValueError("source requirements contain duplicate cohort_unit_id")
    if cohort["cohort_unit_id"].duplicated().any():
        raise ValueError("cohort contains duplicate cohort_unit_id")

    req = requirements.set_index("cohort_unit_id")
    coh = cohort.set_index("cohort_unit_id")
    rows: list[dict[str, object]] = []
    for unit_id in unit_ids:
        if unit_id not in req.index or unit_id not in coh.index:
            raise ValueError(f"missing frozen archetype unit: {unit_id}")
        r = req.loc[unit_id]
        c = coh.loc[unit_id]
        if _truth(c.get("outcome_opened", False)):
            raise ValueError(f"field outcome already opened for {unit_id}")

        required_inputs = [name for flag, name in SOURCE_FLAGS if _truth(r.get(flag, False))]
        manifest_status = str(r.get("private_source_manifest_status", "NOT_BUILT"))
        frame_status = str(r.get("private_frame_status", "NOT_BUILT"))
        ranking_status = str(r.get("public_full_ranking_status", "NOT_FROZEN"))
        source_ready = manifest_status in {"BUILT", "FROZEN", "READY"}

        blockers = [] if source_ready else ["private_source_manifest", *required_inputs]
        rows.append(
            {
                "cohort_unit_id": unit_id,
                "species_binomial": str(r["species_binomial"]),
                "occurrence_problem_class": str(r["occurrence_problem_class"]),
                "structural_feature_family": str(r["structural_feature_family"]),
                "required_private_inputs": "|".join(required_inputs),
                "private_source_manifest_status": manifest_status,
                "private_frame_status": frame_status,
                "public_full_ranking_status": ranking_status,
                "preflight_status": "READY_FOR_PRIVATE_FRAME_BUILD" if source_ready else "BLOCKED_PRIVATE_SOURCE_FREEZE",
                "blockers": "|".join(blockers),
            }
        )

    table = pd.DataFrame(rows)
    summary = {
        "schema_version": "cirsium-private-frame-archetype-preflight-v1",
        "scientific_role": "pre_field_execution_readiness_only",
        "field_outcomes_used": False,
        "exact_coordinates_used": False,
        "archetype_order": list(unit_ids),
        "units": int(len(table)),
        "ready_units": int((table.preflight_status == "READY_FOR_PRIVATE_FRAME_BUILD").sum()),
        "blocked_units": int((table.preflight_status == "BLOCKED_PRIVATE_SOURCE_FREEZE").sum()),
        "next_action": "Freeze the listed private source snapshots/manifests, then build CIR03 -> CIR08 -> CIR02 private frames without changing the frozen algorithms.",
    }
    return table, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirements", type=Path, default=Path("validation/cirsium_private_frame_source_requirements_v1.csv"))
    parser.add_argument("--cohort", type=Path, default=Path("validation/cirsium_aza3_prospective_validation_cohort_v1.csv"))
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    table, summary = build_preflight(pd.read_csv(args.requirements), pd.read_csv(args.cohort))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.out_dir / "archetype_preflight.csv", index=False)
    (args.out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
