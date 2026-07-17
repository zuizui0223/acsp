# Verified EOG evidence ledger

This file records results that were verified from GitHub Actions artifacts produced by PR #35. It separates observed results from interpretation and prevents manuscript text from drifting beyond the available evidence.

## Synthetic topology discrimination

Design:

- fragmentation scenarios matched to zero mean and identity covariance;
- path tortuosity tested separately to avoid topology-destroying scenario-specific whitening;
- 100 repeats with 120 points per scenario;
- Campanula not used.

Verified summary:

| Result | Value |
|---|---:|
| fragmentation PCA breadth range | 0.0 |
| fragmentation Gaussian log-volume range | 2.22e-16 |
| two-mode gap / connected gap | 2.3278 |
| missing-bridge gap / connected gap | 3.3817 |
| curved continuity / straight continuity | approximately 0.494 |
| benchmark gate | PASS |

Supported interpretation: `gap_strength` distinguishes fragmented structures when first and second moments are matched, and `continuity` distinguishes a curved path from a straight path in the controlled path experiment.

## Direct CHELSA confirmation

Design:

- 12 predeclared taxon-region pairs;
- CHELSA v2.1 30 arc-second bio1, bio4, bio12, and bio15 sampled directly at occurrence and candidate coordinates;
- 30 thinning repeats with a 70% training fraction;
- minimum four unique environmental states;
- Campanula not used.

Verified summary:

| Result | Value |
|---|---:|
| technically eligible pairs | 11 / 12 |
| informative among eligible | 11 / 11 |
| median span relative error | approximately 0.079 |
| median continuity absolute error | approximately 0.030 |
| median gap relative error | approximately 0.119 |
| median projection lift | approximately 0.867 |
| positive projection-lift fraction | 1.0 |
| complete success | 10 / 11 |
| direct confirmation gate | PASS |

Supported interpretation: the three geometry summaries are reproducible under the frozen thinning design for most technically eligible pilot pairs. Projection lift is supporting evidence only and is not a novelty claim.

## Conventional comparator benchmark

Compared methods:

- PCA breadth;
- regularized Gaussian covariance log-volume;
- two-cluster K-means silhouette;
- centroid projection distance;
- nearest-occurrence projection distance.

Verified median thinning errors:

| Quantity | Median error |
|---|---:|
| K-means silhouette absolute error | approximately 0.023 |
| continuity absolute error | approximately 0.030 |
| span relative error | approximately 0.079 |
| gap-strength relative error | approximately 0.119 |
| PCA-breadth relative error | approximately 0.121 |
| Gaussian log-volume absolute error | approximately 0.395 |

Supported interpretation: continuity was highly reproducible, while K-means silhouette was also highly reproducible. The benchmark does not support a universal winner claim.

## Incremental-information pilot

The real-taxon pilot had eight evaluable pairs. This sample is too small for a definitive independence test.

Verified exploratory results:

- maximum absolute Spearman association between continuity and the conventional comparator set: approximately 0.786;
- maximum absolute Spearman association between gap strength and the conventional comparator set: approximately 0.476;
- leave-one-out linear prediction from PCA breadth, Gaussian volume, and K-means silhouette performed worse than an intercept-only baseline for both topology quantities;
- conventional-nearest matched pairs retained median differences of approximately 0.109 in continuity and 3.57 in gap strength.

Supported interpretation: the pilot suggests that `gap_strength`, and to a lesser extent `continuity`, are not trivially reconstructed from the selected conventional summaries. It does not establish universal statistical independence.

## Claims not yet supported

Do not state any of the following as established results:

- EOG outperforms all SDMs, hypervolumes, clustering methods, or topological methods;
- the metrics are unprecedented in graph theory or ecological topology;
- the current eight- or eleven-pair cohorts establish generality across taxa;
- EOG quantities have a causal ecological interpretation;
- nearest-neighbour projection is novel;
- `component_count` is a stable primary metric.
