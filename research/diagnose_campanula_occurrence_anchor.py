"""Describe how inspected Campanula field clusters relate to historical anchors.

Scientific role: development diagnosis only. The 2026 field detections have
already been inspected. This script must not be used as independent validation
and does not generate or rank survey candidates.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OCCURRENCES = (
    REPO_ROOT
    / "field_validation"
    / "campanula_microdonta"
    / "development_data"
    / "gbif_training_occurrences_through_2025.csv"
)
DEFAULT_CLUSTERS = (
    REPO_ROOT
    / "field_validation"
    / "campanula_microdonta"
    / "development_data"
    / "detection_clusters.csv"
)
DEFAULT_MANIFEST = (
    REPO_ROOT
    / "field_validation"
    / "campanula_microdonta"
    / "development_data"
    / "manifest.json"
)
DEFAULT_OUT_DIR = (
    REPO_ROOT / "validation" / "campanula_occurrence_anchor_diagnostic_v1"
)


def haversine_km(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """Return great-circle distance in kilometres."""
    radius_km = 6371.0088
    phi_a = math.radians(float(latitude_a))
    phi_b = math.radians(float(latitude_b))
    delta_phi = math.radians(float(latitude_b) - float(latitude_a))
    delta_lambda = math.radians(float(longitude_b) - float(longitude_a))
    value = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi_a)
        * math.cos(phi_b)
        * math.sin(delta_lambda / 2.0) ** 2
    )
    return 2.0 * radius_km * math.asin(math.sqrt(value))


def assign_island(
    latitude: float,
    longitude: float,
    island_bounds: Mapping[str, Sequence[float]],
) -> str | None:
    """Assign a point to one frozen island rectangle."""
    matches: list[str] = []
    for island, bounds in island_bounds.items():
        if len(bounds) != 4:
            raise ValueError(
                f"island_bounds[{island!r}] must contain "
                "[min_lon, min_lat, max_lon, max_lat]"
            )
        min_lon, min_lat, max_lon, max_lat = map(float, bounds)
        if min_lat <= float(latitude) <= max_lat and min_lon <= float(longitude) <= max_lon:
            matches.append(str(island))
    if len(matches) > 1:
        raise ValueError(f"point falls in overlapping island bounds: {matches}")
    return matches[0] if matches else None


def classify_anchor_distance(
    distance_km: float | None,
    *,
    local_radius_km: float,
    tail_radius_km: float,
) -> str:
    """Classify a same-island anchor distance into a development regime."""
    if distance_km is None or pd.isna(distance_km):
        return "anchor_absent"
    if float(distance_km) <= float(local_radius_km):
        return "local_continuation"
    if float(distance_km) <= float(tail_radius_km):
        return "regional_tail"
    return "distant_tail"


def diagnose_occurrence_anchors(
    occurrences: pd.DataFrame,
    clusters: pd.DataFrame,
    island_bounds: Mapping[str, Sequence[float]],
    *,
    local_radius_km: float = 2.0,
    tail_radius_km: float = 5.0,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Return cluster-level nearest-anchor diagnostics and a JSON-ready summary."""
    if local_radius_km <= 0:
        raise ValueError("local_radius_km must be positive")
    if tail_radius_km <= local_radius_km:
        raise ValueError("tail_radius_km must exceed local_radius_km")

    required_occurrence = {"_latitude", "_longitude"}
    required_cluster = {"detection_cluster_id", "island", "latitude", "longitude"}
    missing_occurrence = sorted(required_occurrence.difference(occurrences.columns))
    missing_cluster = sorted(required_cluster.difference(clusters.columns))
    if missing_occurrence:
        raise ValueError(f"occurrence table is missing columns: {missing_occurrence}")
    if missing_cluster:
        raise ValueError(f"cluster table is missing columns: {missing_cluster}")

    known = occurrences.copy()
    known["_latitude"] = pd.to_numeric(known["_latitude"], errors="coerce")
    known["_longitude"] = pd.to_numeric(known["_longitude"], errors="coerce")
    known = known.dropna(subset=["_latitude", "_longitude"]).copy()
    known["island"] = [
        assign_island(lat, lon, island_bounds)
        for lat, lon in zip(known["_latitude"], known["_longitude"])
    ]
    known = known.dropna(subset=["island"]).copy()
    # Repeated specimens and repeated observations at the same coordinate are
    # one geographic anchor for this descriptive audit.
    known = known.drop_duplicates(
        subset=["island", "_latitude", "_longitude"], keep="first"
    )

    known_by_island = {
        str(island): group.loc[:, ["_latitude", "_longitude"]].reset_index(drop=True)
        for island, group in known.groupby("island", sort=True)
    }

    rows: list[dict[str, object]] = []
    for record in clusters.to_dict(orient="records"):
        island = str(record["island"])
        latitude = float(record["latitude"])
        longitude = float(record["longitude"])
        island_known = known_by_island.get(island)

        nearest_distance: float | None = None
        nearest_latitude: float | None = None
        nearest_longitude: float | None = None
        known_anchor_count = 0

        if island_known is not None and not island_known.empty:
            known_anchor_count = int(len(island_known))
            candidates: list[tuple[float, float, float]] = []
            for known_record in island_known.to_dict(orient="records"):
                known_lat = float(known_record["_latitude"])
                known_lon = float(known_record["_longitude"])
                candidates.append(
                    (
                        haversine_km(latitude, longitude, known_lat, known_lon),
                        known_lat,
                        known_lon,
                    )
                )
            nearest_distance, nearest_latitude, nearest_longitude = min(
                candidates, key=lambda item: item[0]
            )

        rows.append(
            {
                "detection_cluster_id": record["detection_cluster_id"],
                "island": island,
                "latitude": latitude,
                "longitude": longitude,
                "same_island_unique_anchor_count": known_anchor_count,
                "nearest_same_island_known_km": nearest_distance,
                "nearest_known_latitude": nearest_latitude,
                "nearest_known_longitude": nearest_longitude,
                "anchor_regime": classify_anchor_distance(
                    nearest_distance,
                    local_radius_km=local_radius_km,
                    tail_radius_km=tail_radius_km,
                ),
            }
        )

    diagnostics = pd.DataFrame(rows).sort_values(
        ["island", "detection_cluster_id"], kind="mergesort"
    ).reset_index(drop=True)

    distances = pd.to_numeric(
        diagnostics["nearest_same_island_known_km"], errors="coerce"
    )
    distance_bands = (0.5, 1.0, 2.0, 5.0)
    summary: dict[str, object] = {
        "scientific_role": "development_diagnostic_only",
        "independent_validation": False,
        "clusters": int(len(diagnostics)),
        "unique_historical_anchors_inside_five_islands": int(len(known)),
        "anchor_regime_counts": {
            str(key): int(value)
            for key, value in diagnostics["anchor_regime"]
            .value_counts(dropna=False)
            .sort_index()
            .items()
        },
        "cumulative_clusters_within_km": {
            str(radius): int((distances <= radius).sum())
            for radius in distance_bands
        },
        "clusters_without_same_island_anchor": int(distances.isna().sum()),
        "median_nearest_same_island_known_km": (
            None if distances.dropna().empty else float(distances.dropna().median())
        ),
        "maximum_nearest_same_island_known_km": (
            None if distances.dropna().empty else float(distances.dropna().max())
        ),
        "local_radius_km": float(local_radius_km),
        "tail_radius_km": float(tail_radius_km),
        "interpretation_boundary": (
            "Describes inspected Campanula outcomes only; distances cannot define "
            "a universal discovery radius or confirmation claim."
        ),
    }
    return diagnostics, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--occurrences", type=Path, default=DEFAULT_OCCURRENCES)
    parser.add_argument("--clusters", type=Path, default=DEFAULT_CLUSTERS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--local-radius-km", type=float, default=2.0)
    parser.add_argument("--tail-radius-km", type=float, default=5.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    island_bounds = manifest.get("island_bounds")
    if not isinstance(island_bounds, dict):
        raise ValueError("manifest must contain an island_bounds object")

    diagnostics, summary = diagnose_occurrence_anchors(
        pd.read_csv(args.occurrences),
        pd.read_csv(args.clusters),
        island_bounds,
        local_radius_km=args.local_radius_km,
        tail_radius_km=args.tail_radius_km,
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    diagnostics_path = args.out_dir / "cluster_anchor_distances.csv"
    summary_path = args.out_dir / "summary.json"
    diagnostics.to_csv(diagnostics_path, index=False)
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"wrote {diagnostics_path}")
    print(f"wrote {summary_path}")


if __name__ == "__main__":
    main()
