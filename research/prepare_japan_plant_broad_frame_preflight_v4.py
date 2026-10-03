#!/usr/bin/env python3
"""Historical-only qualification and candidate-frame freeze for issue #203.

Input must be the exact 96 stage-1 v4 identity candidates. This script may open
only JP 2000-2020 occurrence evidence and WorldCover candidate membership. It
never queries 2021-2025 outcomes or evaluates a selector.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from acsp.discovery import (
    attach_nearest_anchor_distance,
    build_rectangular_candidate_frame,
    cluster_medoid_table,
    complete_link_clusters,
)
from acsp.discovery.providers import fetch_gbif_occurrence_evidence, retain_worldcover_land_points
from acsp.taxon_patches import VALIDATED_JAPAN_REGIONS
from prepare_cirsium_disjoint_broad_frame_replication_v1 import (
    _choose_training_region,
    _hash_candidate_ids,
    _hash_rows,
    _strict_exact,
)

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "validation" / "japan_plant_broad_frame_confirmation_v4.json"


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _selection_hash(seed: int, species_key: int) -> str:
    return hashlib.sha256(f"{int(seed)}|{int(species_key)}".encode()).hexdigest()


def _protocol() -> dict[str, Any]:
    cfg = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    if cfg.get("protocol_id") != "japan_plant_broad_frame_confirmation_v4":
        raise ValueError("protocol id drift")
    if cfg.get("status") != "FROZEN_BEFORE_IDENTITY_CANDIDATE_SELECTION_OR_FOCAL_HISTORICAL_QUERY":
        raise ValueError("protocol freeze state drift")
    stage = cfg["stage2_historical_qualification"]
    if int(stage["candidate_identity_count"]) != 96 or int(stage["final_taxa"]) != 24:
        raise ValueError("stage2 cohort size drift")
    if int(stage["minimum_historical_population_clusters_in_selected_region"]) != 5:
        raise ValueError("historical qualification threshold drift")
    if stage["selection_uses_2021_2025"] is not False:
        raise ValueError("stage2 cannot use heldout")
    return cfg


def _verify_stage1(candidates_path: Path, audit_path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    candidates = pd.read_csv(candidates_path)
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    required = {"candidate_id", "speciesKey", "scientific_name", "identity_selection_hash"}
    if not required.issubset(candidates.columns):
        raise ValueError(f"stage1 candidates missing columns: {sorted(required.difference(candidates.columns))}")
    if len(candidates) != 96 or candidates["speciesKey"].nunique() != 96 or candidates["scientific_name"].nunique() != 96:
        raise ValueError("stage1 candidate identity count drift")
    canonical = candidates[["candidate_id", "speciesKey", "scientific_name", "identity_selection_hash"]].to_dict(orient="records")
    if _canonical_sha(canonical) != str(audit.get("candidate_identity_sha256")):
        raise ValueError("stage1 candidate identity digest drift")
    if audit.get("status") != "IDENTITY_CANDIDATES_FROZEN_PRE_FOCAL_HISTORICAL_QUERY":
        raise ValueError("stage1 audit status drift")
    for key in (
        "focal_2000_2020_occurrences_opened",
        "heldout_2021_2025_opened",
        "candidate_frames_built",
        "selector_evaluated",
    ):
        if audit.get(key) is not False:
            raise ValueError(f"stage1 boundary violation: {key}")
    candidates["speciesKey"] = pd.to_numeric(candidates["speciesKey"], errors="raise").astype(int)
    return candidates.sort_values("candidate_id").reset_index(drop=True), audit


def _region_ids() -> list[str]:
    return [str(row[0]) for row in VALIDATED_JAPAN_REGIONS]


def _region_by_id() -> dict[str, tuple]:
    return {str(row[0]): row for row in VALIDATED_JAPAN_REGIONS}


def _build_universes(
    species_key: int,
    selected_historical: pd.DataFrame,
    region: dict[str, Any],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    universe = cfg["candidate_universes"]
    clusters = complete_link_clusters(selected_historical, radius_km=0.5)
    anchors = cluster_medoid_table(clusters, prefix=f"JPB4_{int(species_key)}_H")
    bounds = (
        float(region["west"]),
        float(region["south"]),
        float(region["east"]),
        float(region["north"]),
    )
    broad_raw, broad_audit = build_rectangular_candidate_frame(
        bounds,
        grid_spacing_m=float(universe["grid_spacing_m"]),
        candidate_id_prefix=f"JPB4_{int(species_key)}_{region['region_id']}_broad",
    )
    broad_raw = attach_nearest_anchor_distance(broad_raw, anchors)
    broad_raw = broad_raw.loc[
        pd.to_numeric(broad_raw["nearest_anchor_km"], errors="coerce").ge(
            float(universe["known_exclusion_km"]) - 1e-12
        )
    ].copy().reset_index(drop=True)
    broad_land, wc_audit = retain_worldcover_land_points(broad_raw)
    nearest = pd.to_numeric(broad_land["nearest_anchor_km"], errors="coerce")
    lanes = {"BROAD_LAND": broad_land}
    for radius in universe["local_outer_radii_km"]:
        lanes[f"LOCAL_{int(radius)}KM_LAND"] = broad_land.loc[
            nearest.le(float(radius) + 1e-12)
        ].copy().reset_index(drop=True)
    return {
        "historical_evidence_sha256": _hash_rows(
            selected_historical,
            ["occurrence_id", "latitude", "longitude", "event_year", "coordinate_uncertainty_m"],
        ),
        "population_anchor_sha256": _hash_rows(
            anchors,
            ["occurrence_id", "latitude", "longitude", "cluster_size"],
        ),
        "historical_population_count": int(len(anchors)),
        "selected_region": {
            "region_id": str(region["region_id"]),
            "region_name": str(region["region_name"]),
            "west": float(region["west"]),
            "south": float(region["south"]),
            "east": float(region["east"]),
            "north": float(region["north"]),
        },
        "broad_frame_audit": broad_audit.__dict__,
        "worldcover_point_audit": wc_audit.as_dict(),
        "candidate_universes": {
            name: {
                "candidate_count": int(len(frame)),
                "candidate_id_sha256": _hash_candidate_ids(frame),
            }
            for name, frame in lanes.items()
        },
    }


def select_final_qualifiers(
    qualifier_rows: list[dict[str, Any]], *, final_count: int, seed: int
) -> list[dict[str, Any]]:
    if len(qualifier_rows) < int(final_count):
        return []
    work = []
    for row in qualifier_rows:
        item = dict(row)
        item["final_selection_hash"] = _selection_hash(seed, int(item["speciesKey"]))
        work.append(item)
    return sorted(
        work,
        key=lambda x: (x["final_selection_hash"], int(x["speciesKey"])),
    )[: int(final_count)]


def run(candidates_path: Path, stage1_audit_path: Path) -> dict[str, Any]:
    cfg = _protocol()
    stage = cfg["stage2_historical_qualification"]
    candidates, _ = _verify_stage1(candidates_path, stage1_audit_path)
    max_uncertainty = float(stage["coordinate_uncertainty_m_max"])
    minimum_populations = int(stage["minimum_historical_population_clusters_in_selected_region"])
    qualifier_rows: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    state_cache: dict[int, tuple[pd.DataFrame, dict[str, Any]]] = {}

    for row in candidates.itertuples(index=False):
        key = int(row.speciesKey)
        name = str(row.scientific_name)
        historical, provider_audit = fetch_gbif_occurrence_evidence(
            name,
            country="JP",
            year_from=2000,
            year_to=2020,
            maximum_records=10000,
        )
        if int(provider_audit.matched_usage_key) != key:
            raise RuntimeError(
                f"provider identity drift for speciesKey={key}: {provider_audit.matched_usage_key}"
            )
        strict = _strict_exact(historical, max_uncertainty)
        region, selected_historical, diagnostics = _choose_training_region(
            strict,
            allowed_region_ids=_region_ids(),
            cluster_radius_km=0.5,
        )
        population_count = (
            0
            if region is None
            else int(len(complete_link_clusters(selected_historical, radius_km=0.5)))
        )
        qualified = bool(region is not None and population_count >= minimum_populations)
        ledger.append({
            "candidate_id": int(row.candidate_id),
            "speciesKey": key,
            "scientific_name": name,
            "strict_historical_records_countrywide": int(len(strict)),
            "selected_region": "" if region is None else str(region["region_id"]),
            "selected_region_historical_population_count": population_count,
            "qualified": qualified,
            "qualification_state": (
                "QUALIFIED"
                if qualified
                else ("NO_HISTORICAL_ANCHOR" if region is None else "BELOW_MIN_HISTORICAL_POPULATIONS")
            ),
        })
        if qualified:
            qualifier_rows.append({
                "candidate_id": int(row.candidate_id),
                "speciesKey": key,
                "scientific_name": name,
                "selected_region": str(region["region_id"]),
                "historical_population_count": population_count,
            })
            state_cache[key] = (selected_historical, region)

    final_rows = select_final_qualifiers(
        qualifier_rows,
        final_count=int(stage["final_taxa"]),
        seed=int(stage["final_selection_seed"]),
    )
    if not final_rows:
        return {
            "schema_version": "japan-plant-broad-frame-preflight-v4",
            "status": "STOP_PREOUTCOME_INSUFFICIENT_HISTORICAL_QUALIFIERS",
            "stage1_candidates_sha256": _file_sha(candidates_path),
            "stage1_audit_sha256": _file_sha(stage1_audit_path),
            "candidate_identity_count": 96,
            "historically_qualified_identities": int(len(qualifier_rows)),
            "required_final_taxa": int(stage["final_taxa"]),
            "qualification_ledger": ledger,
            "heldout_2021_2025_opened": False,
            "selector_evaluated": False,
            "validated_japan_product_changed": False,
            "automatic_global_adapter_changed": False,
        }

    selected: list[dict[str, Any]] = []
    for q in final_rows:
        key = int(q["speciesKey"])
        selected_historical, region = state_cache[key]
        universe = _build_universes(key, selected_historical, region, cfg)
        selected.append({**q, **universe})

    canonical = [
        {
            "speciesKey": int(row["speciesKey"]),
            "scientific_name": str(row["scientific_name"]),
            "selected_region": str(row["selected_region"]["region_id"]),
            "historical_evidence_sha256": str(row["historical_evidence_sha256"]),
            "population_anchor_sha256": str(row["population_anchor_sha256"]),
            "candidate_universes": row["candidate_universes"],
        }
        for row in selected
    ]
    return {
        "schema_version": "japan-plant-broad-frame-preflight-v4",
        "status": "PREOUTCOME_24_TAXA_AND_CANDIDATE_UNIVERSES_FROZEN",
        "stage1_candidates_sha256": _file_sha(candidates_path),
        "stage1_audit_sha256": _file_sha(stage1_audit_path),
        "candidate_identity_count": 96,
        "historically_qualified_identities": int(len(qualifier_rows)),
        "final_taxa": 24,
        "final_selection_sha256": _canonical_sha(canonical),
        "qualification_ledger": ledger,
        "selected_taxa": selected,
        "heldout_2021_2025_opened": False,
        "selector_evaluated": False,
        "human_access_used": False,
        "validated_japan_product_changed": False,
        "automatic_global_adapter_changed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--stage1-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.candidates, args.stage1_audit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in {"qualification_ledger", "selected_taxa"}},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
