#!/usr/bin/env python3
"""Build the fresh-SENTINEL v2 public Japan broad outer frame.

This stage replaces the v1 dependency on a private exact-site/range-sector
polygon. It uses only the commit-pinned geoBoundaries Japan ADM0 geometry and
the already-frozen complete 2-degree country lattice. No focal occurrence,
private exact site, P02 result, field outcome, road/access layer, or budget is
used to decide which outer-frame tiles exist.

The output candidate coordinates are execution data and must remain outside the
public repository. A coordinate-free summary is safe to inspect or hash later.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from acsp.global_geometry import (
    GEOBOUNDARIES_LICENSE,
    GEOBOUNDARIES_RELEASE_COMMIT,
    GEOBOUNDARIES_RELEASE_TAG,
    GEOBOUNDARIES_SOURCE_ID,
    fetch_geoboundaries_country_geometry,
)
from acsp.global_inputs import CountryLandGeometry
from acsp.global_lattice import (
    LATTICE_STEP_DEG,
    POINTS_PER_REGIONAL_TILE,
    build_regional_country_surface,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "validation" / "coverage_then_fine_structure_fresh_sentinel_v2.json"
COUNTRY_CODE = "JP"
UNITS = ("CIR02", "CIR06", "CIR12", "CIR13")
METHOD_IDENTITY = "JP_PUBLIC_COUNTRY_BROAD_FRAME_V1"


def _inside_repo(path: Path, repo_root: Path = ROOT) -> bool:
    try:
        path.resolve().relative_to(repo_root.resolve())
        return True
    except ValueError:
        return False


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _stable_candidate_ids(surface: pd.DataFrame) -> pd.Series:
    required = {"regional_tile_id", "latitude", "longitude"}
    missing = sorted(required.difference(surface.columns))
    if missing:
        raise ValueError(f"regional surface missing required columns: {missing}")
    order = surface.copy().reset_index(drop=True)
    order["_tile_index"] = order.groupby("regional_tile_id", sort=True).cumcount()
    return pd.Series(
        [
            f"JP_{tile}_p{int(index):04d}"
            for tile, index in zip(order["regional_tile_id"].astype(str), order["_tile_index"])
        ],
        index=order.index,
        dtype="object",
    )


def build_fresh_sentinel_v2_outer_frame(
    geometry: CountryLandGeometry,
    *,
    points_per_tile: int = POINTS_PER_REGIONAL_TILE,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build the shared geometry-only Japan outer frame for all four fresh units."""
    if geometry.normalized_code() != COUNTRY_CODE:
        raise ValueError("fresh-SENTINEL v2 outer frame must use the frozen Japan country geometry")
    if int(points_per_tile) <= 0:
        raise ValueError("points_per_tile must be positive")

    surface, audit = build_regional_country_surface(
        geometry,
        points_per_tile=int(points_per_tile),
    )
    if surface.empty:
        raise ValueError("Japan broad outer frame is empty")
    if surface["survey_area_id"].astype(str).nunique() != 1:
        raise ValueError("fresh-SENTINEL v2 outer frame must retain one country-level survey_area_id")

    frame = surface.copy().reset_index(drop=True)
    frame.insert(0, "candidate_cell_id", _stable_candidate_ids(frame))
    if frame["candidate_cell_id"].duplicated().any():
        raise AssertionError("fresh-SENTINEL v2 candidate IDs must be unique")
    frame["outer_frame_identity"] = METHOD_IDENTITY
    frame["field_outcomes_used"] = False
    frame["private_exact_site_geometry_used"] = False
    frame["occurrence_selected_tile"] = False

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if contract.get("status") != "FROZEN_BEFORE_PUBLIC_BROAD_FRAME_EXECUTION":
        raise ValueError("fresh-SENTINEL v2 contract is not in its frozen pre-execution state")
    if tuple(contract.get("cohort_unit_ids") or ()) != UNITS:
        raise ValueError("fresh-SENTINEL v2 cohort identity drifted")

    summary = {
        "schema_version": "cirsium-fresh-sentinel-public-broad-frame-v2",
        "status": "PUBLIC_BROAD_OUTER_FRAME_BUILT_PRE_OUTCOME",
        "method_identity": METHOD_IDENTITY,
        "country_code": COUNTRY_CODE,
        "cohort_unit_ids": list(UNITS),
        "shared_outer_frame_across_units": True,
        "candidate_count": int(len(frame)),
        "intersecting_tile_count": int(audit.intersecting_tile_count),
        "points_per_tile": int(audit.points_per_tile),
        "lattice_step_deg": float(audit.lattice_step_deg),
        "geometry_source_id": str(geometry.source_id),
        "geometry_source_version": str(geometry.source_version),
        "geometry_release_tag": GEOBOUNDARIES_RELEASE_TAG,
        "geometry_release_commit": GEOBOUNDARIES_RELEASE_COMMIT,
        "geometry_license": GEOBOUNDARIES_LICENSE,
        "geometry_provider_expected_source_id": GEOBOUNDARIES_SOURCE_ID,
        "historical_occurrence_tile_selection": False,
        "private_exact_site_geometry_used": False,
        "p02_result_used": False,
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used": False,
        "human_access_used": False,
        "survey_days_input": False,
        "monetary_budget_input": False,
        "user_site_count_input": False,
        "next_gate": (
            "Attach source-backed ecological primitives to this frozen shared outer frame; "
            "do not open prospective field outcomes."
        ),
    }
    return frame, summary


def run(private_out_csv: Path, summary_out_json: Path) -> dict[str, Any]:
    private_out_csv = Path(private_out_csv).resolve()
    summary_out_json = Path(summary_out_json).resolve()
    if _inside_repo(private_out_csv) or _inside_repo(summary_out_json):
        raise ValueError("coordinate-bearing v2 outer-frame execution outputs must remain outside the public repository")
    if private_out_csv.exists() or summary_out_json.exists():
        raise ValueError("refusing to overwrite an existing fresh-SENTINEL v2 outer-frame output")

    geometry = fetch_geoboundaries_country_geometry(COUNTRY_CODE)
    frame, summary = build_fresh_sentinel_v2_outer_frame(geometry)
    private_out_csv.parent.mkdir(parents=True, exist_ok=True)
    summary_out_json.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(private_out_csv, index=False)
    payload = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    summary_out_json.write_text(payload, encoding="utf-8")
    result = {
        **summary,
        "private_frame_sha256": _sha256_bytes(private_out_csv.read_bytes()),
        "summary_sha256": _sha256_bytes(payload.encode("utf-8")),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-out-csv", type=Path, required=True)
    parser.add_argument("--summary-out-json", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.private_out_csv, args.summary_out_json)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
