#!/usr/bin/env python3
"""Build the full fresh-SENTINEL v2 structural order on source-complete fine cells.

The source-complete intersection is frozen by unit. Source-indeterminate fine
cells remain outside G_E and are never recoded as zero support or ranked below
source-complete cells. The output is a complete deterministic order only; no
Top-k, support threshold, compact patch count or field budget is applied.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from acsp.structural_graph import build_structural_graph_primitives
from acsp.structural_raw_adapters import adapt_structural_components
from acsp.structural_support import compose_structural_support

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_v2_fine_structural_order_v1.json"
UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
FAMILIES = {
    "CIR02": "WETLAND_MOISTURE_STRUCTURE",
    "CIR06": "ALPINE_TOPOGRAPHIC_STRUCTURE",
    "CIR12": "OPEN_GRASSLAND_STRUCTURE",
    "CIR13": "OPEN_GRASSLAND_STRUCTURE",
}
WORLD_COVER_UNITS = {"CIR02", "CIR12", "CIR13"}
TERRAIN_COLUMNS = ("elev", "slope100", "tpi300", "rough300")
WORLD_COVER_COLUMNS = (
    "wc_tree_frac_250m",
    "wc_grass_frac_250m",
    "wc_bare_frac_250m",
    "wc_water_frac_250m",
    "wc_wetland_frac_250m",
    "wc_edge_mix_250m",
)


def _inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT.resolve())
        return True
    except ValueError:
        return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_contract() -> dict[str, Any]:
    value = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if value.get("status") != "FROZEN_BEFORE_FINE_STRUCTURAL_ORDER_EXECUTION":
        raise ValueError("fine structural order contract is not frozen")
    if tuple(value.get("cohort_unit_ids") or ()) != UNITS:
        raise ValueError("fine structural-order cohort drifted")
    if value.get("unit_families") != FAMILIES:
        raise ValueError("fine structural-order family mapping drifted")
    chain = value["structural_chain"]
    if chain.get("graph_radius_cells") != 1:
        raise ValueError("fine structural graph radius drifted")
    if chain.get("composition_rule") != "ROW_MIN_CONJUNCTIVE_SUPPORT":
        raise ValueError("fine structural support composition drifted")
    order = value["order"]
    if any(order.get(key) is not False for key in (
        "top_k_applied",
        "support_threshold_applied",
        "patch_count_applied",
        "survey_budget_applied",
    )):
        raise ValueError("fine structural order includes a forbidden stopping rule")
    return value


def _validate_gsi(frame: pd.DataFrame, unit_id: str) -> pd.DataFrame:
    required = {
        "candidate_cell_id",
        "cohort_unit_id",
        "grid_row",
        "grid_col",
        "latitude",
        "longitude",
        "gsi_source_state",
        *TERRAIN_COLUMNS,
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"GSI frame missing columns: {missing}")
    if frame.empty:
        raise ValueError("GSI frame cannot be empty")
    if set(frame["cohort_unit_id"].astype(str)) != {unit_id}:
        raise ValueError("GSI frame unit identity drifted")
    if frame["candidate_cell_id"].astype(str).duplicated().any():
        raise ValueError("GSI candidate IDs must be unique")
    return frame.copy().reset_index(drop=True)


def _merge_worldcover(gsi: pd.DataFrame, worldcover: pd.DataFrame, unit_id: str) -> pd.DataFrame:
    required = {"candidate_cell_id", "worldcover_source_state", *WORLD_COVER_COLUMNS}
    missing = sorted(required.difference(worldcover.columns))
    if missing:
        raise ValueError(f"WorldCover frame missing columns: {missing}")
    if worldcover["candidate_cell_id"].astype(str).duplicated().any():
        raise ValueError("WorldCover candidate IDs must be unique")
    left_ids = gsi["candidate_cell_id"].astype(str).tolist()
    right_ids = worldcover["candidate_cell_id"].astype(str).tolist()
    if left_ids != right_ids:
        raise ValueError(f"{unit_id} GSI/WorldCover candidate identity or order drifted")
    wc = worldcover[["candidate_cell_id", "worldcover_source_state", *WORLD_COVER_COLUMNS]].copy()
    merged = gsi.merge(wc, on="candidate_cell_id", how="left", validate="one_to_one", sort=False)
    if len(merged) != len(gsi):
        raise AssertionError("source merge changed candidate denominator")
    if merged["candidate_cell_id"].astype(str).tolist() != left_ids:
        raise AssertionError("source merge changed candidate order")
    return merged


def _state_digest(frame: pd.DataFrame, *, has_worldcover: bool) -> str:
    digest = hashlib.sha256()
    columns = ["candidate_cell_id", "gsi_source_state"]
    if has_worldcover:
        columns.append("worldcover_source_state")
    for row in frame[columns].itertuples(index=False, name=None):
        digest.update(("\t".join(map(str, row)) + "\n").encode("utf-8"))
    return digest.hexdigest()


def build_fine_structural_order(
    gsi_frame: pd.DataFrame,
    *,
    unit_id: str,
    worldcover_frame: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    contract = _load_contract()
    if unit_id not in UNITS:
        raise ValueError(f"unknown fresh-SENTINEL unit: {unit_id}")
    frame = _validate_gsi(gsi_frame, unit_id)

    if unit_id in WORLD_COVER_UNITS:
        if worldcover_frame is None:
            raise ValueError(f"{unit_id} requires frozen WorldCover fine-source input")
        frame = _merge_worldcover(frame, worldcover_frame, unit_id)
    elif worldcover_frame is not None:
        raise ValueError("CIR06 must not gain an undeclared WorldCover dependency")

    terrain_complete = frame["gsi_source_state"].astype(str).eq("SOURCE_COMPLETE")
    if unit_id in WORLD_COVER_UNITS:
        worldcover_complete = frame["worldcover_source_state"].astype(str).eq("SOURCE_COMPLETE")
        complete = terrain_complete & worldcover_complete
    else:
        complete = terrain_complete

    source_complete = frame.loc[complete].copy().reset_index(drop=True)
    if source_complete.empty:
        raise ValueError(f"{unit_id} has no source-complete fine cells for structural execution")

    for column in TERRAIN_COLUMNS:
        if not np.isfinite(pd.to_numeric(source_complete[column], errors="coerce").to_numpy(float)).all():
            raise ValueError(f"source-complete terrain column is incomplete: {column}")
    if unit_id in WORLD_COVER_UNITS:
        for column in WORLD_COVER_COLUMNS:
            if not np.isfinite(pd.to_numeric(source_complete[column], errors="coerce").to_numpy(float)).all():
                raise ValueError(f"source-complete WorldCover column is incomplete: {column}")

    family = FAMILIES[unit_id]
    graph, graph_audit = build_structural_graph_primitives(
        source_complete,
        feature_family=family,
        radius=1,
    )
    components, raw_audit = adapt_structural_components(graph, feature_family=family)
    support, support_audit = compose_structural_support(components, feature_family=family)
    ordered = components.copy()
    ordered["structural_support"] = support.to_numpy(float)
    ordered = ordered.sort_values(
        ["structural_support", "candidate_cell_id"],
        ascending=[False, True],
        kind="mergesort",
    ).reset_index(drop=True)
    ordered["structural_rank"] = np.arange(1, len(ordered) + 1, dtype=np.int64)
    if ordered["structural_rank"].tolist() != list(range(1, len(ordered) + 1)):
        raise AssertionError("fine structural rank is not a complete 1..N order")

    indeterminate_count = int(len(frame) - len(source_complete))
    source_state_digest = _state_digest(
        frame,
        has_worldcover=(unit_id in WORLD_COVER_UNITS),
    )
    summary = {
        "schema_version": "cirsium-fresh-sentinel-v2-fine-structural-order-result-v1",
        "status": "FINE_STRUCTURAL_FULL_ORDER_BUILT_PRE_OUTCOME",
        "cohort_unit_id": unit_id,
        "feature_family": family,
        "candidate_rows": int(len(frame)),
        "source_complete_rows": int(len(source_complete)),
        "source_complete_fraction": float(len(source_complete) / len(frame)),
        "source_indeterminate_rows": indeterminate_count,
        "source_indeterminate_ranked": False,
        "source_indeterminate_recoded_as_absence": False,
        "source_indeterminate_recoded_as_zero_support": False,
        "structural_order_rows": int(len(ordered)),
        "rank_is_complete_1_to_n": True,
        "graph_audit": asdict(graph_audit),
        "raw_adapter_audit": asdict(raw_audit),
        "support_audit": asdict(support_audit),
        "source_state_digest_sha256": source_state_digest,
        "top_k_applied": False,
        "support_threshold_applied": False,
        "patch_count_applied": False,
        "survey_budget_applied": False,
        "field_outcomes_opened": False,
        "human_access_used": False,
        "exact_site_claim": False,
        "occupancy_claim": False,
        "next_gate": "Freeze the private full-order hash. Compact patch compression or field allocation remains a separate validation problem.",
    }
    return ordered, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-id", choices=UNITS, required=True)
    parser.add_argument("--gsi-csv-gz", type=Path, required=True)
    parser.add_argument("--worldcover-csv-gz", type=Path)
    parser.add_argument("--private-order-csv-gz", type=Path, required=True)
    parser.add_argument("--public-safe-summary-json", type=Path, required=True)
    args = parser.parse_args()

    if not args.gsi_csv_gz.is_file():
        raise SystemExit(f"missing private GSI frame: {args.gsi_csv_gz}")
    if args.unit_id in WORLD_COVER_UNITS:
        if args.worldcover_csv_gz is None or not args.worldcover_csv_gz.is_file():
            raise SystemExit(f"{args.unit_id} requires private WorldCover frame")
    elif args.worldcover_csv_gz is not None:
        raise SystemExit("CIR06 does not accept WorldCover input")
    if _inside_repo(args.private_order_csv_gz):
        raise SystemExit("refusing to write coordinate-bearing fine structural order inside repository")
    if args.private_order_csv_gz.exists() or args.public_safe_summary_json.exists():
        raise SystemExit("refusing to overwrite fine structural-order outputs")

    gsi = pd.read_csv(args.gsi_csv_gz, low_memory=False)
    wc = pd.read_csv(args.worldcover_csv_gz, low_memory=False) if args.worldcover_csv_gz else None
    ordered, summary = build_fine_structural_order(gsi, unit_id=args.unit_id, worldcover_frame=wc)
    args.private_order_csv_gz.parent.mkdir(parents=True, exist_ok=True)
    args.public_safe_summary_json.parent.mkdir(parents=True, exist_ok=True)
    ordered.to_csv(
        args.private_order_csv_gz,
        index=False,
        compression={"method": "gzip", "mtime": 0},
    )
    summary["private_structural_order_sha256"] = _sha256(args.private_order_csv_gz)
    args.public_safe_summary_json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
