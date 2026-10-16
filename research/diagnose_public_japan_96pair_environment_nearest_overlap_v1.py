#!/usr/bin/env python3
"""Replay the frozen 96-pair comparison and diagnose environment/nearest overlap.

This is a post-result descriptive diagnostic only. It reuses the exact frozen
methods from the parent development comparison and reports aggregate hit overlap
at the already-fixed 10-km radius. It must not be used to tune a blend.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "research") not in sys.path:
    sys.path.insert(0, str(ROOT / "research"))

from acsp.taxon_patches import ROBUST_TERRAIN_FEATURES, _terrain_inputs
from acsp.validated_robust import validated_robust_candidate_patches
from benchmark_public_japan_96pair_temporal_anchor_v1 import fetch_pair_records, haversine_km
from compare_public_japan_96pair_environment_vs_distance_v1 import (
    novel_recent_clusters,
    select_nearest_known,
)

DEFAULT_DIAGNOSTIC = ROOT / "validation" / "public_japan_96pair_environment_nearest_overlap_diagnostic_v1.json"
PARENT_CONTRACT = ROOT / "validation" / "public_japan_96pair_environment_vs_distance_development_v1.json"


def cluster_hit_mask(
    selected: pd.DataFrame,
    clusters: list[list[tuple[float, float, str]]],
    radius_km: float,
) -> np.ndarray:
    if not clusters:
        return np.zeros(0, dtype=bool)
    if selected.empty:
        return np.zeros(len(clusters), dtype=bool)
    points = list(zip(selected["latitude"].astype(float), selected["longitude"].astype(float)))
    hits = []
    for cluster in clusters:
        hit = any(
            haversine_km(lat, lon, member[0], member[1]) <= float(radius_km) + 1e-12
            for lat, lon in points
            for member in cluster
        )
        hits.append(bool(hit))
    return np.asarray(hits, dtype=bool)


def zero_row(pair: pd.Series, status: str, reason: str, *, novel_clusters: int = 0) -> dict[str, object]:
    return {
        "pair_id": int(pair.pair_id),
        "taxon_group": str(pair.taxon_group),
        "region_name": str(pair.region_name),
        "species_key": int(pair.speciesKey),
        "scientific_name": str(pair.scientific_name),
        "status": str(status),
        "failure_reason": str(reason),
        "novel_recent_clusters": int(novel_clusters),
        "candidate_count_k": 0,
        "both_environment_and_nearest": 0,
        "environment_only": 0,
        "nearest_only": 0,
        "neither": 0,
        "classified_overlap_clusters": 0,
    }


def evaluate_pair(pair: pd.Series, records: pd.DataFrame, parent: dict[str, object]) -> dict[str, object]:
    historical, novel = novel_recent_clusters(records)
    if not novel:
        return zero_row(pair, "no_novel_recent_target", "no novel recent cluster", novel_clusters=0)
    minimum = int(parent["shared_historical_evidence"]["minimum_historical_rows_for_environmental_generation"])
    if len(historical) < minimum:
        return zero_row(
            pair,
            "insufficient_historical_evidence",
            f"strict historical rows={len(historical)} < {minimum}",
            novel_clusters=len(novel),
        )

    bounds = (float(pair.west), float(pair.south), float(pair.east), float(pair.north))
    area_id = f"pair-{int(pair.pair_id):03d}"
    try:
        surface, prototypes, _ = _terrain_inputs(historical, bounds, area_id=area_id)
        patches, _ = validated_robust_candidate_patches(
            surface,
            prototypes,
            feature_columns=ROBUST_TERRAIN_FEATURES,
            area_col="survey_area_id",
        )
        k = int(len(patches))
        if k <= 0:
            raise ValueError("environmental support produced zero candidate patches")
        nearest = select_nearest_known(
            surface,
            historical,
            pair_id=int(pair.pair_id),
            count=k,
            exclusion_km=float(parent["scientific_methods"]["nearest_known"]["known_reobservation_exclusion_km"]),
        )
    except Exception as exc:
        return zero_row(
            pair,
            "parent_method_generation_failure",
            f"{type(exc).__name__}: {str(exc)[:240]}",
            novel_clusters=len(novel),
        )

    radius = 10.0
    env_hit = cluster_hit_mask(patches, novel, radius)
    near_hit = cluster_hit_mask(nearest, novel, radius)
    both = env_hit & near_hit
    env_only = env_hit & ~near_hit
    near_only = ~env_hit & near_hit
    neither = ~env_hit & ~near_hit
    total = len(novel)
    if int(both.sum() + env_only.sum() + near_only.sum() + neither.sum()) != total:
        raise AssertionError("overlap categories do not partition novel clusters")

    return {
        "pair_id": int(pair.pair_id),
        "taxon_group": str(pair.taxon_group),
        "region_name": str(pair.region_name),
        "species_key": int(pair.speciesKey),
        "scientific_name": str(pair.scientific_name),
        "status": "classified",
        "failure_reason": "",
        "novel_recent_clusters": int(total),
        "candidate_count_k": int(k),
        "both_environment_and_nearest": int(both.sum()),
        "environment_only": int(env_only.sum()),
        "nearest_only": int(near_only.sum()),
        "neither": int(neither.sum()),
        "classified_overlap_clusters": int(total),
    }


def summarize(table: pd.DataFrame) -> dict[str, object]:
    if len(table) != 96:
        raise ValueError(f"expected 96 retained rows, got {len(table)}")
    classified = table.loc[table["status"].eq("classified")].copy()
    totals = {
        key: int(classified[key].sum())
        for key in ("both_environment_and_nearest", "environment_only", "nearest_only", "neither")
    }
    denominator = int(classified["classified_overlap_clusters"].sum())
    if denominator != sum(totals.values()):
        raise AssertionError("aggregate overlap categories do not partition denominator")
    env_hits = totals["both_environment_and_nearest"] + totals["environment_only"]
    nearest_hits = totals["both_environment_and_nearest"] + totals["nearest_only"]
    union_hits = env_hits + totals["nearest_only"]
    intersection = totals["both_environment_and_nearest"]
    hit_union_for_jaccard = env_hits + nearest_hits - intersection

    subgroup = {}
    for group in ("plant", "animal"):
        frame = classified.loc[classified["taxon_group"].eq(group)]
        d = int(frame["classified_overlap_clusters"].sum())
        eonly = int(frame["environment_only"].sum())
        nonly = int(frame["nearest_only"].sum())
        both = int(frame["both_environment_and_nearest"].sum())
        subgroup[group] = {
            "classified_pairs": int(len(frame)),
            "classified_clusters": d,
            "both": both,
            "environment_only": eonly,
            "nearest_only": nonly,
            "environment_only_fraction_of_clusters": float(eonly / d) if d else None,
            "nearest_only_fraction_of_clusters": float(nonly / d) if d else None,
        }

    return {
        "schema_version": "public-japan-96pair-environment-nearest-overlap-result-v1",
        "status": "POST_RESULT_DESCRIPTIVE_OVERLAP_COMPLETE",
        "validated_product_changed": False,
        "new_independent_confirmation_claim": False,
        "declared_pairs": 96,
        "classified_pairs": int(len(classified)),
        "status_counts": {str(k): int(v) for k, v in table["status"].value_counts().items()},
        "classified_novel_clusters": denominator,
        **totals,
        "environment_recovered_clusters": int(env_hits),
        "nearest_recovered_clusters": int(nearest_hits),
        "environment_or_nearest_union_clusters": int(union_hits),
        "environment_only_fraction_of_classified_clusters": float(totals["environment_only"] / denominator) if denominator else None,
        "nearest_only_fraction_of_classified_clusters": float(totals["nearest_only"] / denominator) if denominator else None,
        "union_fraction_of_classified_clusters": float(union_hits / denominator) if denominator else None,
        "nearest_fraction_of_classified_clusters": float(nearest_hits / denominator) if denominator else None,
        "environment_increment_over_nearest_absolute": float(totals["environment_only"] / denominator) if denominator else None,
        "nearest_increment_over_environment_absolute": float(totals["nearest_only"] / denominator) if denominator else None,
        "hit_set_jaccard": float(intersection / hit_union_for_jaccard) if hit_union_for_jaccard else None,
        "subgroup": subgroup,
        "interpretation_boundary": "Post-result descriptive overlap only. It cannot rescue the failed parent nomination gate or validate an environment-nearest union."
    }


def run(sample_file: Path, diagnostic_path: Path = DEFAULT_DIAGNOSTIC) -> tuple[pd.DataFrame, dict[str, object]]:
    diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8"))
    if diagnostic.get("status") != "POST_RESULT_DIAGNOSTIC_FROZEN_BEFORE_OVERLAP_RERUN":
        raise ValueError("overlap diagnostic contract is not frozen")
    parent = json.loads(PARENT_CONTRACT.read_text(encoding="utf-8"))
    sample = pd.read_csv(sample_file)
    sample = sample.loc[sample["status"].eq("predeclared")].sort_values("pair_id").reset_index(drop=True)
    if len(sample) != 96 or sample["scientific_name"].nunique() != 96:
        raise ValueError("expected exact frozen 96-pair cohort")

    rows = []
    for _, pair in sample.iterrows():
        try:
            records, _ = fetch_pair_records(pair, page_size=300, maximum_records=10000, pause_seconds=0.02)
            row = evaluate_pair(pair, records, parent)
        except Exception as exc:
            row = zero_row(pair, "provider_or_fetch_failure", f"{type(exc).__name__}: {str(exc)[:240]}")
        rows.append(row)
    table = pd.DataFrame(rows).sort_values("pair_id").reset_index(drop=True)
    return table, summarize(table)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-file", type=Path, required=True)
    parser.add_argument("--diagnostic", type=Path, default=DEFAULT_DIAGNOSTIC)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    table, summary = run(args.sample_file, args.diagnostic)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.out_dir / "pair_overlap_counts.csv", index=False)
    (args.out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
