#!/usr/bin/env python3
"""Strict runner for the random-taxon occupancy-geometry benchmark."""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

import benchmark_random_taxa_occupancy_geometry as benchmark


def _coordinates(frame: pd.DataFrame) -> np.ndarray:
    """Resolve all coordinate conventions produced by ACSP/GBIF loaders."""
    pairs = (
        ("decimalLatitude", "decimalLongitude"),
        ("latitude", "longitude"),
        ("_latitude", "_longitude"),
        ("lat", "lon"),
    )
    for latitude, longitude in pairs:
        if latitude in frame.columns and longitude in frame.columns:
            values = frame[[latitude, longitude]].apply(pd.to_numeric, errors="coerce").to_numpy(float)
            if np.isfinite(values).any():
                return values
    raise ValueError(
        "occurrence table lacks usable coordinate columns; available columns: "
        + ", ".join(map(str, frame.columns))
    )


def main() -> None:
    benchmark._coordinates = _coordinates
    args = benchmark.parser().parse_args()
    result = benchmark.run(args)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    declared = int(result.get("predeclared_pairs", 0))
    evaluable = int(result.get("evaluable_pairs", 0))
    if declared <= 0 or evaluable <= 0:
        raise SystemExit("No random taxon-region pair was evaluable")
    if float(result.get("completion_rate", 0.0)) < 0.75:
        raise SystemExit(
            f"Only {evaluable}/{declared} random taxon-region pairs were evaluable"
        )


if __name__ == "__main__":
    main()
