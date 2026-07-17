# Environmental occupancy geometry API contract

This document freezes the environmental occupancy geometry behavior that is being extracted from ACSP into the standalone `zuizui0223/eog` repository.

## Frozen public objects

- `OccupancyGeometry`
- `robust_scale`
- `pairwise_distances`
- `minimum_spanning_tree`
- `infer_occupancy_geometry`
- `project_states`

## Frozen result fields

`OccupancyGeometry` contains, in order:

1. `n_occurrences`
2. `n_features`
3. `span`
4. `mst_length`
5. `continuity`
6. `gap_strength`
7. `component_count`
8. `labels`
9. `mst_edges`

Changing field names, order, or meaning requires an explicit breaking-version decision in the standalone EOG package.

## Frozen definitions

Input values are a finite two-dimensional numeric matrix with at least two rows and one feature.

Features are scaled independently using the median and normal-consistency-adjusted median absolute deviation (`MAD * 1.4826`). Constant columns are set to zero and are therefore neutral.

- `span`: the requested quantile, default 0.90, of positive pairwise Euclidean distances in robust-scaled feature space.
- `mst_length`: sum of all minimum-spanning-tree edge lengths.
- `continuity`: maximum pairwise distance divided by `mst_length`; defined as 1 when `mst_length` is zero.
- `gap_strength`: largest positive MST edge divided by the median positive MST edge; defined as 1 when there are no positive MST edges.
- `component_count` and `labels`: diagnostic components formed by cutting edges above the robust gap threshold. They are not primary inferential quantities.
- `mst_edges`: an `(n_occurrences - 1, 3)` float array containing source index, target index, and edge length.

## Frozen edge cases

- One-dimensional feature matrices are supported.
- Duplicate rows are supported.
- All-identical rows return `span=0`, `mst_length=0`, `continuity=1`, `gap_strength=1`, and one component.
- Non-finite values are rejected.
- Fewer than two rows and zero-feature matrices are rejected.
- `gap_multiplier` must be non-negative.
- `span_quantile` must lie in `(0, 1]`.
- Empty candidate arrays with the correct feature dimension are accepted by `project_states` and return empty arrays.
- Candidate feature dimension and geometry-label length must match their occurrence reference.

## Compatibility boundary

The standalone EOG repository will initially reproduce this implementation and contract exactly. ACSP may later depend on EOG as an external package, but ACSP must not silently change these numerical definitions during migration.
