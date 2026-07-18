#!/usr/bin/env python3
"""Normalize coordinate-column aliases in frozen gap-validation inputs."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


LATITUDE_ALIASES = (
    "latitude",
    "_latitude",
    "decimalLatitude",
    "decimal_latitude",
    "decimallatitude",
    "lat",
    "Latitude",
)
LONGITUDE_ALIASES = (
    "longitude",
    "_longitude",
    "decimalLongitude",
    "decimal_longitude",
    "decimallongitude",
    "lon",
    "lng",
    "Longitude",
)


def normalize_coordinate_columns(frame: pd.DataFrame, *, name: str) -> pd.DataFrame:
    """Return a copy with canonical latitude/longitude columns.

    Existing canonical columns take precedence. Aliases are matched exactly first
    and then case-insensitively. Values are coerced to numeric so unusable rows can
    be identified by downstream validation rather than failing on string content.
    """
    out = frame.copy()
    lower_to_actual = {str(column).lower(): column for column in out.columns}

    def resolve(aliases: tuple[str, ...]) -> str | None:
        for alias in aliases:
            if alias in out.columns:
                return alias
        for alias in aliases:
            actual = lower_to_actual.get(alias.lower())
            if actual is not None:
                return str(actual)
        return None

    latitude_col = resolve(LATITUDE_ALIASES)
    longitude_col = resolve(LONGITUDE_ALIASES)
    missing = []
    if latitude_col is None:
        missing.append("latitude")
    if longitude_col is None:
        missing.append("longitude")
    if missing:
        raise ValueError(
            f"{name} has no recognized {', '.join(missing)} column; "
            f"available columns: {', '.join(map(str, out.columns))}"
        )

    if latitude_col != "latitude":
        out = out.rename(columns={latitude_col: "latitude"})
    if longitude_col != "longitude":
        out = out.rename(columns={longitude_col: "longitude"})
    out["latitude"] = pd.to_numeric(out["latitude"], errors="coerce")
    out["longitude"] = pd.to_numeric(out["longitude"], errors="coerce")
    if out[["latitude", "longitude"]].dropna().empty:
        raise ValueError(f"{name} contains no usable coordinate pair after normalization")
    return out


def normalize_file(path: Path) -> None:
    frame = pd.read_csv(path)
    normalized = normalize_coordinate_columns(frame, name=str(path))
    normalized.to_csv(path, index=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        default="field_validation/campanula_microdonta/temporal_external_results",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    results = Path(args.results)
    for filename in (
        "gbif_training_occurrences_through_2025.csv",
        "distance_excluded_candidate_pool.csv",
        "independent_detection_clusters.csv",
    ):
        path = results / filename
        if not path.exists():
            raise FileNotFoundError(path)
        normalize_file(path)


if __name__ == "__main__":
    main()
