#!/usr/bin/env python3
"""Run the frozen Izu microenvironment benchmark with a GBIF-safe geometry.

GBIF rejects the disjoint MULTIPOLYGON used by the legacy helper. A single
bounding POLYGON is used only for retrieval; the benchmark still assigns and
retains records only inside the five frozen island rectangles.
"""
from __future__ import annotations

import benchmark_izu_microenvironment_random_taxa as benchmark


def retrieval_wkt() -> str:
    bounds = list(benchmark.ISLAND_BOUNDS.values())
    west = min(value[0] for value in bounds)
    south = min(value[1] for value in bounds)
    east = max(value[2] for value in bounds)
    north = max(value[3] for value in bounds)
    return (
        f"POLYGON(({west} {south},{east} {south},{east} {north},"
        f"{west} {north},{west} {south}))"
    )


benchmark.island_wkt = retrieval_wkt

if __name__ == "__main__":
    benchmark.main()
