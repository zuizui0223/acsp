# Environmental occupancy geometry

Status: experimental.

## Question

How broadly, continuously, or discontinuously do observed occurrences occupy an arbitrary ecological feature space?

This differs from fitting a species-distribution surface. The method does not estimate presence probability for raster cells. It treats occurrence environments as a point cloud and returns geometry of that cloud.

## Initial quantities

- `span`: robust upper quantile of pairwise environmental distances.
- `mst_length`: total length required to connect all occupied states.
- `continuity`: environmental diameter divided by MST length. Lower values indicate a more winding or fragmented occupation.
- `gap_strength`: largest MST edge divided by the median positive MST edge.
- `component_count`: number of occupied modes after cutting unusually long MST edges using a median/MAD rule.

All features are median/MAD scaled. Constant features are neutral. The implementation accepts any finite numeric feature matrix and does not know whether features originated from rasters, polygons, field measurements, or other sources.

## Guardrails

- no raster suitability output;
- no pseudo-absence or background classifier;
- no survey route, budget, or accessibility term;
- no candidate recommendation in this first iteration;
- multiple geographically disjunct populations may remain separate environmental modes;
- projection to candidates is diagnostic only.

## Falsification plan

The method is useful only if its geometry is reproducible under occurrence thinning and spatial hold-out, distinguishes known continuous and disjunct occupation patterns, and adds ecological information beyond ordinary niche breadth or point-prototype distance. Later iterations must compare against convex-hull volume, PCA niche breadth, kernel hypervolume, clustering, and SDM-derived suitability summaries before claiming novelty.
