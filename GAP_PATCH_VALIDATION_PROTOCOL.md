# Gap-separated patch validation protocol

## Target estimand

The new method does not claim exact-site occurrence probability. It evaluates whether occurrence-conditioned candidate support can recover **held-out, spatially disconnected population patches** under a fixed survey budget.

The primary unit is a population or occurrence cluster, not an individual record. Training occurrences, held-out occurrences, candidates, and field detections must therefore be clustered before evaluation.

## Candidate classes

Every retained patch is assigned to one predeclared class:

1. `anchor_expansion`: the patch touches the exclusion radius around a known occurrence cluster.
2. `gap_separated_satellite`: the patch is disconnected from every known anchor but remains within the predeclared satellite search distance.
3. `environmental_analogue_outpost`: the patch is disconnected and farther than the satellite search distance.

The main scientific endpoint concerns `gap_separated_satellite` patches. Anchor expansions are retained as a pragmatic field baseline; outposts are an exploration stratum.

## Frozen parameters

Parameters must be frozen before confirmatory taxa or the 2026 *Campanula microdonta* field detections are inspected:

- support thresholds;
- candidate graph link distance;
- known-anchor radius;
- maximum satellite distance;
- minimum patch membership;
- patch-overlap threshold used for persistence;
- clustering radius for occurrence populations;
- recovery radii;
- route or member-count budget.

Development sensitivity analyses may vary these values, but confirmatory results must report the frozen setting first.

## Retrospective benchmark

For every taxon-region pair:

1. Cluster occurrences into population patches.
2. Hold out one or more complete spatial clusters.
3. Build all environmental evidence and candidate locations from training clusters only.
4. Remove candidates inside the known-anchor exclusion radius.
5. Discover disconnected candidate patches across the frozen support thresholds.
6. Select patches under a fixed member-count, area, or route-time budget.
7. Measure distance from every held-out cluster to the nearest patch member.

Failed candidate generation and empty patch sets remain in the intention-to-evaluate denominator.

## Required baselines

Use the same eligible candidate pool and equal budget for:

- uniform random candidate members;
- random patches after applying the same graph construction;
- nearest-known buffer sampling;
- environmental-support Top-k;
- current ACSP complementary Top-k;
- current ACSP complete-link zones;
- gap-separated persistent patches.

The nearest-known buffer is the critical baseline. A complex gap method is not useful if a simple buffer recovers the same independent patches at equal cost.

## Primary endpoints

- held-out satellite-cluster recall under equal budget;
- recovered satellite clusters per selected patch;
- recovered satellite clusters per route hour when route data are available;
- median distance from held-out cluster to nearest patch member;
- fraction of selected effort spent on anchor, satellite, and outpost classes.

Report 1, 2, 5, and 10 km recovery as sensitivity endpoints. The primary radius must be frozen separately for regional and field-scale claims.

## Prospective *Campanula microdonta* analysis

Use only records available before the 2026 survey to build candidate patches. Cluster the 2026 field GPS records independently, then classify each field cluster as:

- overlap with a prior known cluster;
- continuous extension of a prior cluster;
- gap-separated satellite;
- remote outpost.

The principal prospective question is whether frozen gap-separated candidate patches recovered field-confirmed satellite clusters better than equal-budget buffer, random, and current-ACSP selections.

Detection efficiency cannot be claimed unless visited nondetection sites, search duration, searched path or area, phenology, and access failure are recorded.

## Ablations

Run the following ablations on development taxa:

- one support threshold only;
- no persistence term;
- single candidate cells instead of patches;
- no anchor/satellite/outpost stratification;
- geographic distance only;
- environmental support only;
- patch centroids rather than patch members for recovery.

These tests determine whether any gain comes from the gap-patch formulation itself rather than from selecting more area.
