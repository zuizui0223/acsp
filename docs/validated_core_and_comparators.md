# Validated ACSP core and same-pool comparators

## Purpose

The production ACSP application contains more evidence sources and planning features than the independently validated paper core. This document fixes that boundary and defines the next comparison stage without changing the confirmed algorithm.

## Frozen publication-facing policies

### Plants

- candidate score: `component_local_habitat_score`;
- local-evidence weight: 1.00;
- geographic-complementarity weight: 0.00;
- budget: Top-5;
- primary endpoint: held-out occurrence recall within 10 km.

### Animals

- candidate score: `component_local_habitat_score`;
- local-evidence weight: 0.75;
- geographic-complementarity weight: 0.25;
- budget: Top-5;
- primary endpoint: held-out occurrence recall within 10 km.

For both groups, candidates are reconstructed from training occurrences only. Known-location candidate types and direct occurrence-, density-, survey-gap-, novelty-, and distance-derived evidence are excluded before selection.

`ValidatedCorePolicy` and `select_validated_core` expose this narrow contract independently of the production integrated evidence score.

## Current evidence

The independently supported claim is limited to improvement over random Top-5 decisions drawn from the identical candidate pools at a 10-km regional scale. It is not an exact-site, occupancy, access, detectability, abundance, or field-efficiency claim.

## Why additional baselines are required

Same-pool random selection shows whether the frozen policy adds selection value beyond candidate generation. It does not establish superiority over established survey-design principles. A publication-strength comparison should therefore evaluate all methods on the same frozen candidate rows, held-out occurrence IDs, Top-k budget, and pair-level inference.

## Implemented comparators

`acsp.decision_baselines` provides deterministic selectors for:

1. `local_evidence_top_k` — highest declared focal-taxon score;
2. `geographic_maximin` — geographically dispersed coverage;
3. `environmental_maximin` — robust-scaled environmental coverage;
4. `dual_space_maximin` — a declared mixture of geographic and environmental distance;
5. `random_same_pool` — reproducible random sets from the identical pool.

Held-out outcome IDs are read only after each selector returns its candidate set.

## Required frozen benchmark

For every taxon–region fold:

1. rebuild candidates from training occurrences only;
2. remove known-location and occurrence-derived evidence exactly as in the confirmation benchmark;
3. retain the environmental columns used to construct the local analogue;
4. apply each selector without held-out information;
5. calculate set-level recall from the precomputed held-out coverage IDs;
6. average repeats within taxon–region pairs using the fixed intention-to-evaluate denominator;
7. compare pair-level lifts and uncertainty without tuning ACSP or the comparator mixture after results are inspected.

The minimum reported methods should be random, local score only, geographic maximin, environmental maximin, dual-space maximin, frozen ACSP, and the non-operational held-out oracle.

## Interpretation rules

- If ACSP exceeds random but not the standard comparators, the defensible contribution remains its auditable occurrence-to-decision workflow and validation contract, not superior selection performance.
- If the animal policy exceeds local-score-only and geographic-only selection, the result supports an incremental role for combining evidence and complementarity.
- If plant score-only and frozen ACSP are identical, that is expected because the frozen plant policy contains no geographic-complementarity weight.
- No comparator result should enter the paper until the cohort and all method parameters are frozen.
