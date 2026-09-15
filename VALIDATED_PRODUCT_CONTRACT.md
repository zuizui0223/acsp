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

## Confirmed automatic global adapter boundary

The separate [availability-parity confirmation v2](validation/acsp_global_availability_parity_confirmation_v2.json) passed its six preregistered gates on 48 fresh taxa. Its [canonical result](validation/acsp_global_availability_parity_confirmation_result_v2.json) promotes only automatic provider/evidence-aware historical-country framing plus the frozen robust core under the tested adapter.

- Country selection uses 1900–2020 historical counts and pinned provider coverage before candidates or heldout outcomes.
- Robust construction succeeded for 44/48 taxa, including one valid empty patch set.
- Retrospective evaluability was 35/44 **conditional on constructibility**; conditional mean lift over random was +0.0986218 with taxon-bootstrap 95% CI [+0.0385639, +0.1625447]. The evaluable empty patch set contributes zero lift.
- The identity frame was the pooled species registry of the 12 Japanese discovery regions, with prior consumed identities excluded. This does not validate arbitrary worldwide species or establish equal absolute accuracy between Japan and global cohorts.
- Explicit user-target countries must never be silently replaced by another country. This automatic-country confirmation does not separately validate arbitrary explicit-country searches.

The original 96-pair / 480-fold Japanese confirmation remains a separate result. Earlier country-framed failures and provider aborts retain their original decisions and denominators. LOCAL/DETACHED/SENTINEL structural ranking, field efficiency and occupancy claims are outside this promotion.

**Implementation status:** `acsp-patches --taxon` still runs the Japanese 12-region adapter. `acsp.discovery.country_frames` provides historical country planning; the confirmed end-to-end global procedure is implemented by the staged research pipeline. A species-only global command has not yet been integrated. `acsp-discovery` remains an experimental exploration entry point.

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
