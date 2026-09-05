#!/usr/bin/env python3
"""Build one private Cirsium source manifest from the frozen public requirements.

The output contains hashes/provenance for coordinate-bearing or licensed/private
source files and therefore must stay outside the public git repository. This tool
does not fetch sources, open field outcomes, or infer missing evidence classes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_V1_DIGEST = "sha256:fe1971d5547b4741fdcfc568fe568193007398afca6dd0aa316c2713d8d6e430"
AUDIT_V2_DIGEST = "sha256:5e908fecb625f2f8e4e87e758a0a9d0ace63c14e63fce19cf7bf87c0c7fe8147"


def _inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPO_ROOT.resolve())
        return True
    except ValueError:
        return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _existing(paths: Iterable[Path], label: str) -> list[Path]:
    out = [Path(p) for p in paths]
    for path in out:
        if not path.is_file():
            raise ValueError(f"missing {label} file: {path}")
    return out


def _truth(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _file_records(paths: list[Path]) -> list[dict[str, str]]:
    return [{"file_name": path.name, "sha256": _sha256(path)} for path in paths]


def build_manifest(
    requirements: pd.DataFrame,
    cohort: pd.DataFrame,
    *,
    unit_id: str,
    range_sector_file: Path,
    raw_grid_file: Path,
    primary_anchor_file: Path | None = None,
    sentinel_evidence_file: Path | None = None,
    gsi_dem_files: tuple[Path, ...] = (),
    worldcover_files: tuple[Path, ...] = (),
    coastline_file: Path | None = None,
    target_component_file: Path | None = None,
    target_component_id: str | None = None,
) -> dict[str, object]:
    req = requirements.set_index("cohort_unit_id")
    coh = cohort.set_index("cohort_unit_id")
    if unit_id not in req.index or unit_id not in coh.index:
        raise ValueError(f"unknown frozen cohort unit: {unit_id}")
    r = req.loc[unit_id]
    c = coh.loc[unit_id]
    if _truth(c.get("outcome_opened", False)):
        raise ValueError(f"field outcome already opened for {unit_id}")

    range_sector_file = _existing([range_sector_file], "range-sector")[0]
    raw_grid_file = _existing([raw_grid_file], "raw-grid")[0]
    dem = _existing(gsi_dem_files, "GSI DEM")
    wc = _existing(worldcover_files, "ESA WorldCover")

    local = str(r["occurrence_problem_class"]) == "LOCAL_CONTINUATION"
    if _truth(r.get("requires_primary_anchor_geometry", False)) and primary_anchor_file is None:
        raise ValueError("frozen unit requires primary-anchor geometry")
    if _truth(r.get("requires_broad_sentinel_support", False)) and sentinel_evidence_file is None:
        raise ValueError("frozen unit requires sentinel evidence/support input")
    if _truth(r.get("requires_gsi_dem", False)) and not dem:
        raise ValueError("frozen unit requires at least one GSI DEM snapshot")
    if _truth(r.get("requires_esa_worldcover_2021", False)) and not wc:
        raise ValueError("frozen unit requires at least one ESA WorldCover 2021 snapshot")
    if _truth(r.get("requires_gsi_coastline", False)) and coastline_file is None:
        raise ValueError("frozen unit requires the pinned GSI coastline snapshot")
    if _truth(r.get("requires_target_component_id", False)):
        if target_component_file is None or not str(target_component_id or "").strip():
            raise ValueError("frozen unit requires target ecological component id and definition")

    anchor = _existing([primary_anchor_file], "primary-anchor")[0] if primary_anchor_file else None
    sentinel = _existing([sentinel_evidence_file], "sentinel-evidence")[0] if sentinel_evidence_file else None
    coastline = _existing([coastline_file], "GSI coastline")[0] if coastline_file else None
    component = _existing([target_component_file], "target-component")[0] if target_component_file else None

    manifest = {
        "schema_version": "cirsium-private-source-manifest-v1",
        "cohort_unit_id": unit_id,
        "species_binomial": str(r["species_binomial"]),
        "field_outcomes_opened": False,
        "aza3_slot_id": str(c["aza3_slot_id"]),
        "range_sector_id": str(c["range_sector"]),
        "range_sector_geometry_sha256": _sha256(range_sector_file),
        "occurrence_input": {
            "event_date_max": "2025-12-31",
            "audit_v1_artifact_digest": AUDIT_V1_DIGEST,
            "audit_v2_artifact_digest": AUDIT_V2_DIGEST,
            "sentinel_evidence_class": str(c["sentinel_evidence_class"]),
            "sentinel_subregime": str(c["sentinel_subregime"]),
            "eligible_primary_anchor_private_table_sha256": _sha256(anchor) if anchor else "",
            "sentinel_broad_evidence_private_table_sha256": _sha256(sentinel) if sentinel else "",
        },
        "candidate_grid": {
            "target_spacing_m": 100,
            "geometry_rule": "cirsium-candidate-frame-contract-v1",
            "private_raw_grid_sha256": _sha256(raw_grid_file),
        },
        "gsi_dem": {
            "required": _truth(r.get("requires_gsi_dem", False)),
            "source": "Geospatial Information Authority of Japan elevation data / frozen unit snapshot",
            "files": _file_records(dem),
        },
        "esa_worldcover": {
            "required": _truth(r.get("requires_esa_worldcover_2021", False)),
            "source": "ESA WorldCover 2021 v200 10 m",
            "files": _file_records(wc),
        },
        "gsi_coastline": {
            "required": _truth(r.get("requires_gsi_coastline", False)),
            "source": "GSI Fundamental Geospatial Data, Basic Items, coastline",
            "observed_service_release_before_freeze": "2026-07-31",
            "file_name": coastline.name if coastline else "",
            "private_snapshot_sha256": _sha256(coastline) if coastline else "",
        },
        "target_ecological_component": {
            "required": _truth(r.get("requires_target_component_id", False)),
            "component_id": str(target_component_id or ""),
            "definition_file_name": component.name if component else "",
            "definition_sha256": _sha256(component) if component else "",
        },
        "broad_sentinel_support": {
            "required": _truth(r.get("requires_broad_sentinel_support", False)),
            "evidence_class": str(c["sentinel_evidence_class"]),
            "sentinel_subregime": str(c["sentinel_subregime"]),
            "private_support_input_sha256": _sha256(sentinel) if sentinel else "",
        },
        "private_salt": {"committed": False, "sha256_recorded_publicly": False},
        "authorization_access_layers_in_G_E": False,
        "build_audit": {
            "local_unit": local,
            "requirements_row_frozen": True,
            "cohort_row_frozen": True,
            "field_outcomes_used": False,
            "missing_required_sources": [],
        },
    }
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-id", required=True)
    parser.add_argument("--requirements", type=Path, default=Path("validation/cirsium_private_frame_source_requirements_v1.csv"))
    parser.add_argument("--cohort", type=Path, default=Path("validation/cirsium_aza3_prospective_validation_cohort_v1.csv"))
    parser.add_argument("--range-sector", type=Path, required=True)
    parser.add_argument("--raw-grid", type=Path, required=True)
    parser.add_argument("--primary-anchor", type=Path)
    parser.add_argument("--sentinel-evidence", type=Path)
    parser.add_argument("--gsi-dem", type=Path, action="append", default=[])
    parser.add_argument("--worldcover", type=Path, action="append", default=[])
    parser.add_argument("--gsi-coastline", type=Path)
    parser.add_argument("--target-component-definition", type=Path)
    parser.add_argument("--target-component-id")
    parser.add_argument("--out-json", type=Path, required=True)
    args = parser.parse_args()

    if _inside_repo(args.out_json):
        raise SystemExit("refusing to write a private source manifest inside the git repository")
    manifest = build_manifest(
        pd.read_csv(args.requirements),
        pd.read_csv(args.cohort),
        unit_id=args.unit_id,
        range_sector_file=args.range_sector,
        raw_grid_file=args.raw_grid,
        primary_anchor_file=args.primary_anchor,
        sentinel_evidence_file=args.sentinel_evidence,
        gsi_dem_files=tuple(args.gsi_dem),
        worldcover_files=tuple(args.worldcover),
        coastline_file=args.gsi_coastline,
        target_component_file=args.target_component_definition,
        target_component_id=args.target_component_id,
    )
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PRIVATE_SOURCE_MANIFEST_BUILT", "cohort_unit_id": args.unit_id}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
