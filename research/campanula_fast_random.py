"""Fast exact matched-random recovery audit for Campanula development experiments."""
from __future__ import annotations

import numpy as np

from campanula_worldcover_discovery import haversine_km


def fast_matched_random_success(
    universe,
    detections,
    selected,
    radius_km,
    iterations,
    seed,
):
    """Exact equivalent of matched_random_success with distances precomputed once."""
    rng = np.random.default_rng(seed)
    per_island = selected.groupby("island").size().to_dict()
    prepared = {}
    for island, frame in universe.groupby("island"):
        frame = frame.reset_index(drop=False)
        island_detections = detections[detections["island"].eq(island)].reset_index(drop=True)
        coverage = np.zeros((len(island_detections), len(frame)), dtype=bool)
        for row_index, point in island_detections.iterrows():
            coverage[row_index] = haversine_km(
                float(point["latitude"]),
                float(point["longitude"]),
                frame["lat"].to_numpy(),
                frame["lon"].to_numpy(),
            ) <= float(radius_km)
        prepared[island] = (len(frame), coverage)

    recovery = np.zeros(int(iterations), dtype=int)
    for iteration in range(int(iterations)):
        recovered = 0
        for island, count in per_island.items():
            if island not in prepared:
                continue
            pool_size, coverage = prepared[island]
            draw_size = min(int(count), pool_size)
            if draw_size <= 0:
                continue
            chosen = rng.choice(pool_size, size=draw_size, replace=False)
            recovered += int(coverage[:, chosen].any(axis=1).sum())
        recovery[iteration] = recovered

    target = int(len(detections))
    return {
        "iterations": int(iterations),
        "complete_recovery_probability": float(np.mean(recovery == target)),
        "mean_recovered": float(np.mean(recovery)),
        "q05_recovered": float(np.quantile(recovery, 0.05)),
        "q95_recovered": float(np.quantile(recovery, 0.95)),
    }
