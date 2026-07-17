# Environmental Occupancy Geometry

This directory is the manuscript-facing entry point for the environmental occupancy geometry (EOG) method merged in PR #35.

## Scope

EOG describes the geometry of observed environmental states without fitting occurrence probability or raster suitability. The primary quantities are:

- `continuity`: environmental diameter divided by total minimum-spanning-tree length. It describes how direct or tortuous the occupied environmental path is.
- `gap_strength`: the largest minimum-spanning-tree edge divided by the median edge. It describes the strongest internal discontinuity.
- `span`: a supporting environmental breadth quantity.
- `component_count`: a diagnostic quantity only. It is not treated as a primary inferential metric.

The implementation is in [`acsp/occupancy_geometry.py`](../../acsp/occupancy_geometry.py). Direct environmental sampling used in the confirmation benchmark is in [`acsp/chelsa_sampling.py`](../../acsp/chelsa_sampling.py).

## Documentation

- [Method definitions and guardrails](../environmental_occupancy_geometry.md)
- [Original manuscript plan](../occupancy_geometry_manuscript_plan.md)
- [Verified evidence ledger](evidence_ledger.md)
- [Benchmark catalogue](../../benchmarks/README.md)

## Current claim boundary

The repository supports the following limited claim:

> EOG quantifies connectedness and internal discontinuity in occupied environmental point clouds, including structure that is not identifiable from covariance breadth or volume alone in the synthetic benchmark.

The repository does **not** currently establish that EOG is a universal replacement for species distribution models, is superior to every hypervolume or clustering method, or has been validated for causal biological interpretation.

## Manuscript work still required

1. Freeze metric names and equations.
2. Expand the direct CHELSA cohort beyond the current pilot size.
3. Compare EOG against graph-topological, single-linkage, persistent-homology, and kernel-hypervolume baselines.
4. Complete a systematic novelty review with an auditable search log.
5. Add one independent biological case study after the general-method analyses are frozen.
6. Archive a release and immutable benchmark outputs for submission.
