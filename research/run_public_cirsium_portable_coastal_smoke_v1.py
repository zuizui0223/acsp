#!/usr/bin/env python3
"""Run the frozen portable WorldCover coastal smoke for CIR08.

Development only. The method uses strict 2000-2020 public occurrence evidence,
the pre-existing Okinawa-main frame, official ESA WorldCover 2021 v200 Map,
and the generic ``acsp.discovery`` workflow. Full method orders are constructed
before 2021-2025 novel populations are scored.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
import sys
from pathlib import Path

import pandas as pd
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "research"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

from acsp.discovery import (
    AnnularFrameSpec,
    DiscoveryContext,
    assess_occurrence_evidence,
    build_annular_candidate_frame,
    cluster_min_distance_km,
    complete_link_clusters,
    haversine_km,
    rank_discovery_frame,
)
from acsp.discovery.providers import attach_worldcover_coastal_features, build_worldcover_2021_map_crop
from benchmark_public_japan_cirsium_temporal_anchor_v1 import fetch_gbif_species

CONTRACT = ROOT / "validation" / "public_cirsium_portable_coastal_smoke_v1.json"
UNIT_ID = "CIR08"
SPECIES = "Cirsium brevicaule"
FAMILY = "COASTAL_ISLAND_STRUCTURE"


def _inside(frame: pd.DataFrame, bounds: tuple[float, float, float, float]) -> pd.DataFrame:
    west, south, east, north = bounds
    return frame.loc[
        frame["longitude"].between(west, east)
        & frame["latitude"].between(south, north)
    ].copy().reset_index(drop=True)


def _occurrence_schema(frame: pd.DataFrame) -> pd.DataFrame:
    columns = ["occurrence_id", "latitude", "longitude", "event_year", "coordinate_uncertainty_m", "provider_id"]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(
        {
            "occurrence_id": frame["gbif_key"].astype(str),
            "latitude": frame["latitude"].astype(float),
            "longitude": frame["longitude"].astype(float),
            "event_year": frame["year"].astype(int),
            "coordinate_uncertainty_m": frame["coordinate_uncertainty_m"].astype(float),
            "provider_id": "GBIF",
        }
    )


def _novel_recent_clusters(historical: pd.DataFrame, recent: pd.DataFrame):
    old = complete_link_clusters(historical, radius_km=0.5)
    new = complete_link_clusters(recent, radius_km=0.5)
    novel = []
    for cluster in new:
        if not old or min(cluster_min_distance_km(cluster, prior) for prior in old) > 0.5 + 1e-12:
            novel.append(cluster)
    return novel


def _cluster_recovery(selected: pd.DataFrame, clusters, radius_km: float) -> float:
    if selected.empty or not clusters:
        return 0.0
    points = list(zip(selected["latitude"].astype(float), selected["longitude"].astype(float)))
    recovered = 0
    for cluster in clusters:
        hit = any(
            haversine_km(lat, lon, member_lat, member_lon) <= float(radius_km) + 1e-12
            for lat, lon in points
            for member_lat, member_lon, _ in cluster.members
        )
        recovered += int(hit)
    return float(recovered / len(clusters))


def _blocked(status: str, *, fetch_audit: dict, assessment: dict | None = None, detail: str = ""):
    return pd.DataFrame(), {
        "schema_version": "public-cirsium-portable-coastal-smoke-result-v1",
        "status": status,
        "cohort_unit_id": UNIT_ID,
        "species": SPECIES,
        "family": FAMILY,
        "validated_product_changed": False,
        "new_confirmation_claim": False,
        "structural_layer_run": False,
        "recent_outcome_scoring_run": False,
        "replacement_or_precision_relaxation_used": False,
        "fetch_audit": fetch_audit,
        "assessment": assessment,
        "detail": detail,
    }


def run(out_dir: Path) -> tuple[pd.DataFrame, dict]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if contract.get("status") != "DEVELOPMENT_ONLY_FROZEN_BEFORE_PORTABLE_COASTAL_EXECUTION":
        raise ValueError("portable coastal contract is not frozen")
    if contract.get("species") != SPECIES or contract.get("feature_family") != FAMILY:
        raise ValueError("portable coastal identity/family mismatch")

    declared = contract["declared_frame"]
    bounds = tuple(float(declared[key]) for key in ("west", "south", "east", "north"))
    clip = box(*bounds)
    records, fetch_audit = fetch_gbif_species(SPECIES, maximum_records=10000, pause_seconds=0.02)
    records = _inside(records, bounds)
    historical_raw = records.loc[records["year"].between(2000, 2020)].copy().reset_index(drop=True)
    recent_raw = records.loc[records["year"].between(2021, 2025)].copy().reset_index(drop=True)
    historical = _occurrence_schema(historical_raw)
    recent = _occurrence_schema(recent_raw)

    if historical.empty:
        return _blocked("NO_STRICT_HISTORICAL_ANCHOR", fetch_audit=fetch_audit)

    assessment, anchors = assess_occurrence_evidence(historical, context=DiscoveryContext(local_component_justified=True))
    if assessment.population_anchor_count < 1:
        return _blocked("NO_STRICT_HISTORICAL_ANCHOR", fetch_audit=fetch_audit, assessment=assessment.as_dict())

    frame_spec = contract["candidate_frames"]
    outer_values = (float(frame_spec["primary_outer_radius_km"]), float(frame_spec["sensitivity_outer_radius_km"]))
    raw_frames: dict[float, pd.DataFrame] = {}
    frame_build_audits: dict[str, dict] = {}
    for outer in outer_values:
        raw, audit = build_annular_candidate_frame(
            anchors,
            spec=AnnularFrameSpec(
                grid_spacing_m=float(frame_spec["grid_spacing_m"]),
                known_exclusion_km=float(frame_spec["known_exclusion_km"]),
                outer_radius_km=float(outer),
            ),
            candidate_id_prefix=f"{UNIT_ID}_{int(round(outer * 1000)):04d}",
            clip_geometry_wgs84=clip,
        )
        raw_frames[outer] = raw
        frame_build_audits[str(outer)] = asdict(audit)

    all_frame = pd.concat(list(raw_frames.values()), ignore_index=True)
    wc_bounds = (
        float(all_frame["longitude"].min()),
        float(all_frame["latitude"].min()),
        float(all_frame["longitude"].max()),
        float(all_frame["latitude"].max()),
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    wc_path = out_dir / "private_worldcover_crop.tif"
    try:
        wc_audit = build_worldcover_2021_map_crop(
            wc_bounds,
            wc_path,
            margin_m=float(contract["worldcover"]["crop_margin_m"]),
        )
    except Exception as exc:
        return _blocked(
            "WORLDCOVER_PROVIDER_FAILURE",
            fetch_audit=fetch_audit,
            assessment=assessment.as_dict(),
            detail=f"{type(exc).__name__}:{exc}",
        )

    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    source_uri = ";".join(wc_audit.source_urls)
    source_manifest = {
        "schema_version": "portable-coastal-worldcover-source-v1",
        "sources": [
            {
                "provider_id": "ESA_WORLDCOVER",
                "layer_role": role,
                "release_id": "2021_v200",
                "retrieved_at": retrieved_at,
                "source_uri": source_uri,
                "sha256": wc_audit.output_sha256,
            }
            for role in ("landcover", "coastline", "component_geometry")
        ],
    }

    frozen_rankings: dict[float, dict[str, pd.DataFrame]] = {}
    ranking_audits: dict[str, dict] = {}
    coastal_audits: dict[str, dict] = {}
    try:
        for outer, raw in raw_frames.items():
            enriched, coastal_audit = attach_worldcover_coastal_features(
                raw,
                anchors,
                wc_path,
                neighbourhood_half_width_m=float(contract["worldcover"]["neighbourhood_half_width_m"]),
            )
            rankings, ranking_audit = rank_discovery_frame(
                enriched,
                assessment=assessment,
                source_manifest=source_manifest,
                feature_family=FAMILY,
                target_component_id=coastal_audit.target_component_id,
            )
            frozen_rankings[outer] = rankings
            ranking_audits[str(outer)] = ranking_audit.as_dict()
            coastal_audits[str(outer)] = asdict(coastal_audit)
    except ValueError as exc:
        token = str(exc)
        if token.startswith("ANCHOR_ON_NO_VALID_WORLDCOVER_LAND"):
            state = "ANCHOR_ON_NO_VALID_WORLDCOVER_LAND"
        elif token.startswith("MULTIPLE_HISTORICAL_LAND_COMPONENTS"):
            state = "MULTIPLE_HISTORICAL_LAND_COMPONENTS"
        else:
            raise
        return _blocked(state, fetch_audit=fetch_audit, assessment=assessment.as_dict(), detail=token)

    # Outcome scoring starts only after both frame-specific full ranking sets exist.
    novel = _novel_recent_clusters(historical, recent) if not recent.empty else []
    fractions = [float(value) for value in contract["ranking"]["prefix_fractions"]]
    radii = [float(value) for value in contract["outcome"]["recovery_radii_km"]]
    rows: list[dict] = []
    for outer in outer_values:
        methods = frozen_rankings[outer]
        candidate_count = len(next(iter(methods.values())))
        if any(len(frame) != candidate_count for frame in methods.values()):
            raise AssertionError("all portable coastal methods must rank the identical land candidate frame")
        for fraction in fractions:
            k = max(1, min(candidate_count, int(math.ceil(fraction * candidate_count))))
            selected = {method: frame.head(k) for method, frame in methods.items()}
            for radius in radii:
                rows.append(
                    {
                        "cohort_unit_id": UNIT_ID,
                        "species": SPECIES,
                        "family": FAMILY,
                        "outer_frame_km": outer,
                        "prefix_fraction": fraction,
                        "selected_count": k,
                        "recovery_radius_km": radius,
                        "novel_recent_clusters": int(len(novel)),
                        "structural_recall": _cluster_recovery(selected["STRUCTURAL_SUPPORT"], novel, radius),
                        "nearest_recall": _cluster_recovery(selected["ANNULAR_NEAREST_KNOWN"], novel, radius),
                        "spatial_balance_recall": _cluster_recovery(selected["DETERMINISTIC_SPATIAL_BALANCE"], novel, radius),
                    }
                )
    table = pd.DataFrame(rows)
    summary = {
        "schema_version": "public-cirsium-portable-coastal-smoke-result-v1",
        "status": "DEVELOPMENT_ONLY_PORTABLE_COASTAL_SMOKE_COMPLETE",
        "cohort_unit_id": UNIT_ID,
        "species": SPECIES,
        "family": FAMILY,
        "validated_product_changed": False,
        "new_confirmation_claim": False,
        "structural_layer_run": True,
        "recent_outcome_scoring_run": True,
        "replacement_or_precision_relaxation_used": False,
        "fetch_audit": fetch_audit,
        "historical_records_in_declared_frame": int(len(historical)),
        "historical_population_anchors": int(assessment.population_anchor_count),
        "recent_records_in_declared_frame": int(len(recent)),
        "novel_recent_clusters": int(len(novel)),
        "assessment": assessment.as_dict(),
        "worldcover_audit": asdict(wc_audit),
        "candidate_frame_build_audits": frame_build_audits,
        "coastal_feature_audits": coastal_audits,
        "ranking_audits": ranking_audits,
        "reported_outer_frames_km": list(outer_values),
        "reported_prefix_fractions": fractions,
        "reported_recovery_radii_km": radii,
        "interpretation_boundary": "Opened public development unit. All frozen cells are reported; no favorable frame/prefix/radius can be promoted without a new disjoint cohort."
    }
    return table, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    table, summary = run(args.out_dir)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.out_dir / "portable_coastal_prefix_curve.csv", index=False)
    (args.out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    private_crop = args.out_dir / "private_worldcover_crop.tif"
    if private_crop.exists():
        private_crop.unlink()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
