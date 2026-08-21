# ACSP validated product contract

Status: **authoritative for the independently validated ACSP product**.

This document defines the scientific product boundary that takes precedence over older planning, UI, and research-positioning prose when those documents conflict with the current validated implementation.

## Validated product

The validated ACSP product is an **occurrence-conditioned robust candidate-patch generator**.

```text
training occurrences
        ↓
occurrence-conditioned environmental support
        ↓
leave-one-prototype-out robust support
        ↓
frozen 2.5% consensus tier
        ↓
1 km same-area deterministic complete-link aggregation
        ↓
bounded candidate patches
```

The validated output is a set of candidate patches. The patches are not priority-ranked and are not calibrated occupancy or suitability probabilities.

## Frozen scientific constants

The independently confirmed core keeps these values fixed:

- robust-support fraction: `0.025`;
- support worlds: `float32`;
- patch merge distance: `1000 m`;
- same-area aggregation only;
- confirmation frame: 96 taxon-region pairs / 480 folds;
- validated interpretation: regional candidate-patch recovery, not exact-site occupancy.

Changing these values is a new scientific experiment and must not be described as the already validated product.

## What is outside the validated core

The following may remain available as software, compatibility, exploratory, or operational layers, but they are not part of the independently validated candidate-patch claim unless separately validated:

- historical integrated candidate scores and fixed component weights;
- priority ranks, Top-k planning, or ranked survey zones;
- route optimization, hubs, travel modes, field-day estimation, or monetary budgets;
- access, detectability, abundance, phenology, or discoveries-per-day claims;
- SDM/SSDM-based re-ranking or model-only exploration;
- prospective adaptive learning from attempted sites and non-detections.

These layers must not be allowed to change candidate-patch membership inside the validated path unless a new validation protocol is explicitly frozen and passed.

## Package and dependency boundary

The validated path is planner-free at both execution and package-import time.

- `acsp.robust_patches` must not depend on `acsp.planning`.
- Importing `acsp`, `validated_robust_candidate_patches`, or `discover_validated_candidate_patches` must not import `acsp.planning`.
- Historical planner APIs may remain available through lazy compatibility exports.

## Campanula role

`Campanula microdonta` is development and freeze-regression evidence. Its field outcomes were inspected during development and therefore must not be relabeled as an untouched cross-taxon confirmation cohort.

Campanula may be used to verify that the frozen generic core still reproduces the development object, but not to expand the independent confirmation claim.

## Development rule

Future scientific development must preserve a clear separation between:

1. **validated candidate generation** — the frozen robust candidate-patch product defined here; and
2. **operational or exploratory planning** — ranking, routing, SDM/SSDM, access, field effort, or adaptive learning layers that may consume the candidate patches downstream.

If a future method changes patch membership, support representation, threshold, merge distance, or interpretation, it is a new candidate-generation method and requires a new predeclared validation cycle.

## Documentation precedence

When this contract conflicts with older text in `AGENTS.md`, `SURVEY_PLANNING_POLICY.md`, `RESEARCH_POSITIONING.md`, README files, legacy notes, or historical research artifacts, **this contract governs the current validated product**. Older documents remain useful for software history, operational workflows, and research provenance but cannot broaden the validated claim.