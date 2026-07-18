# Gap-separated patch validation protocol

## Target estimand

The method does not claim exact-site occurrence probability. It evaluates whether occurrence-conditioned support can recover **held-out population patches separated from known anchors by an observed low-support corridor**, subject to a fixed travel-distance limit.

The primary unit is a population or occurrence cluster, not an individual record.

## Candidate classes

Every retained patch receives two classifications.

Spatial class:

1. `anchor_expansion`: within the known-anchor radius.
2. `gap_separated_satellite`: outside the anchor radius but within the satellite search distance.
3. `environmental_analogue_outpost`: farther than the satellite search distance.

Corridor class:

1. `continuous_anchor_extension`: an anchor expansion.
2. `barrier_separated_patch`: the anchor-patch transect contains a sufficiently long low-support run.
3. `distance_separated_without_barrier`: geographically separated, but no low-support barrier is demonstrated.

The main scientific endpoint concerns `barrier_separated_patch` objects within the satellite range.

## Frozen parameters

Freeze the following before confirmatory taxa or the 2026 *Campanula microdonta* detections are inspected:

- support thresholds;
- candidate graph link distance;
- known-anchor radius;
- maximum satellite distance;
- minimum patch membership;
- persistence overlap threshold;
- occurrence-clustering radius;
- corridor sample spacing;
- corridor interpolation radius;
- low-support threshold;
- minimum barrier length;
- recovery radii;
- origin and maximum closed-route travel distance.

Patch count, member count, score-per-member, and manually assigned survey effort are not budgets in the confirmatory comparison.

## Retrospective benchmark

For every taxon-region pair:

1. Cluster occurrences into population patches.
2. Hold out one or more complete spatial clusters.
3. Build environmental evidence and candidate locations from training clusters only.
4. Discover persistent candidate patches.
5. Sample the support corridor between each patch and its nearest known anchor.
6. Retain the distinction between mere geographic separation and demonstrated low-support barriers.
7. Select whole patches from a common origin under the same maximum closed-route distance.
8. Measure distance from every held-out cluster to the nearest selected patch member.

Failed candidate generation and empty patch sets remain in the intention-to-evaluate denominator.

## Required baselines

Apply the same origin, eligible region, and maximum travel distance to:

- random patch ordering;
- nearest-known patch ordering;
- environmental-support ordering;
- current ACSP complementary selection converted to the same route constraint;
- current complete-link zones converted to the same route constraint;
- persistent gap patches without corridor evidence;
- persistent patches requiring a demonstrated corridor barrier.

The nearest-known baseline is critical. The new method is not useful if a simple outward search from known occurrences recovers the same independent clusters within the same travel distance.

## Primary endpoints

- held-out barrier-separated satellite-cluster recall;
- total held-out cluster recall;
- cumulative recovered clusters versus closed-route distance;
- median distance from held-out cluster to nearest selected patch member;
- fraction of selected patches with a demonstrated corridor barrier;
- stability across frozen threshold and link-distance sensitivity runs.

Report 1, 2, 5, and 10 km recovery as sensitivity endpoints. Do not divide by selected patch count or candidate-member count as a primary performance measure.

## Prospective *Campanula microdonta* analysis

Use only records available before the 2026 survey. Cluster the 2026 field GPS records independently and classify each field cluster as:

- overlap with a prior known cluster;
- continuous extension;
- geographically separated without demonstrated barrier;
- barrier-separated satellite;
- remote outpost.

The principal question is whether frozen barrier-separated patches recover field-confirmed satellite clusters better than nearest-known, random, and current-ACSP selections within the same travel-distance limit.

Detection efficiency cannot be claimed unless visited nondetection sites, search duration, searched path or area, phenology, and access failure are recorded.

## Ablations

Run the following on development taxa:

- one support threshold only;
- no persistence term;
- no corridor evidence;
- geographic distance only;
- environmental support only;
- change corridor interpolation radius;
- change minimum barrier length;
- patch centroids rather than patch members for recovery.

These tests determine whether any gain comes from detecting an ecological discontinuity rather than merely selecting distant or larger areas.
