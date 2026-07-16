# Environmental occupancy geometry: manuscript plan

Status: development stage; Campanula is excluded from the general-method benchmark.

## Core claim under test

Occurrence records can be treated as a point cloud in arbitrary ecological feature space. Three continuous quantities—environmental span, MST continuity, and MST gap strength—describe how broadly and discontinuously observed states are occupied without fitting raster-cell presence probability.

The first paper should not claim that the method replaces SDMs. The defensible claim is that it estimates a different object: the geometry of occupied ecological states, with stability under occurrence thinning and predictive relevance for held-out states.

## Development evidence required

1. Predeclared random taxon-region pairs spanning plants, animals, and geographic strata.
2. An informative-state filter declared before examining geometry outcomes.
3. Repeated thinning stability for span, continuity, and gap strength.
4. Held-out occurrence projection compared with same-region available environmental states.
5. Pair-level medians and positive-pair fractions, not only pooled means.
6. Runtime and memory reporting.

## Confirmation evidence still required

1. Freeze all thresholds after the development cohort.
2. Draw a new confirmation cohort with no overlap in taxon-region pairs.
3. Extract environmental features directly at occurrence coordinates rather than through nearest-candidate proxies.
4. Compare against PCA niche breadth, convex-hull or kernel hypervolume, nearest-prototype distance, and standard clustering stability.
5. Run sensitivity analyses for feature subsets, sample size, thinning fraction, and spatially blocked hold-out.
6. Show ecological interpretation on independent examples only after the general method is fixed.

## Primary quantities

- `span`: upper quantile of robust pairwise environmental distances.
- `continuity`: environmental diameter divided by total MST length.
- `gap_strength`: largest positive MST edge divided by the median positive MST edge.

`component_count` remains a diagnostic visualization only. It is not a primary inferential quantity because integer mode counts are unstable near a cutting threshold.

## Publication development gate

- informative taxon-region fraction >= 0.75;
- median pair span relative error <= 0.25;
- median pair continuity absolute error <= 0.15;
- median pair gap-strength relative error <= 0.35;
- median pair projection lift over random > 0;
- at least 60% of informative pairs have positive median projection lift.

Passing this gate supports moving to a frozen confirmation cohort. It is not itself confirmation or proof of novelty.
