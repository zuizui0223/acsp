# ACSP algorithm simplification plan

## Current problem

The current production path mixes four different tasks:

1. evidence normalization and integration;
2. candidate ranking;
3. spatial diversification of selected points;
4. aggregation of selected points into operational zones.

`integrated_candidate_scores`, `select_complementary_candidates`, and `aggregate_candidates_to_zones` are individually transparent, but their sequential use can score the same spatial idea more than once. Survey-gap evidence enters the integrated score, geographic complementarity is then added during Top-k selection, and nearby points are finally merged into zones. The resulting output is difficult to interpret as either a probability, a ranking score, or a survey patch value.

## Simplified target architecture

### Stage 1: evidence table

Produce one normalized table with independent evidence families only:

- `environment_support`;
- `macro_support` when genuinely available;
- `access_constraint`;
- `field_support` when prospectively measured.

Occurrence count, occurrence density, nearest-known distance, and survey gap are metadata or design variables, not interchangeable ecological evidence. They should not all enter one weighted mean.

### Stage 2: candidate support

Use a small, explicit support rule. Missing evidence is renormalized, but bonuses for agreement, divergence, candidate-type text labels, and exploration should move out of the ecological support score.

Recommended development baseline:

```text
candidate_support = weighted mean(environment_support, macro_support)
```

Access remains a hard constraint or a downstream cost. Field validation is an adaptive update, not a static nominal weight before field data exist.

### Stage 3: patch construction

Replace the sequence

```text
integrated score -> geographically complementary Top-k -> complete-link zones
```

with

```text
candidate support -> radius graph -> persistent connected patches
```

Spatial complementarity is then expressed once, through disconnected patch structure. Complete-link zone aggregation remains available as a legacy baseline during validation.

### Stage 4: survey selection

Select patches under an explicit budget. Selection criteria should be named rather than hidden in a composite score:

- support;
- persistence;
- anchor/satellite/outpost stratum;
- route or search cost;
- environmental redundancy among selected patches.

## Immediate deprecations after validation

Do not remove legacy functions before the comparison benchmark is complete. If gap patches meet the predeclared gate, proceed in a follow-up PR:

1. mark `select_complementary_candidates` as a legacy regional baseline;
2. remove candidate-type string matching from score construction;
3. replace agreement and divergence bonuses with exported diagnostics;
4. stop treating survey-gap distance as an evidence-family weight;
5. consolidate duplicate Haversine implementations into one spatial utility module;
6. use one zone/patch representation throughout mapping, validation, and routing;
7. separate retrospective-safe evidence from prospective field and access information at the schema level.

## Validation gate for replacement

The new path replaces the current selector only if it:

- improves gap-separated held-out cluster recovery over nearest-known buffers and current ACSP at equal budget;
- does not materially reduce total held-out recovery;
- remains stable across predeclared threshold and link-distance sensitivity runs;
- produces fewer, more interpretable output objects than the current point-plus-zone workflow;
- passes prospective *Campanula microdonta* evaluation without tuning on the 2026 detections.

Until that gate is passed, the new module is experimental and the current ACSP remains the production baseline.
