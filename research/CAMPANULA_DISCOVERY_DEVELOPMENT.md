# Campanula inverse survey-algorithm development contract

## Status

`Campanula microdonta` is **development data, not an independent validation cohort**.
The 2026 field outcomes have already been inspected and have already motivated ACSP changes. They
are therefore used deliberately as a reverse-engineering instrument: the development question is
what decision structure would have been required to recover the realized field distribution without
feeding the 2026 coordinates into inference.

The frozen cross-taxon Practical Core and the frozen 192-pair confirmation artifacts remain separate.
Nothing in this development track changes their fingerprints, taxa, splits, or claims.

## Correct direction of the operational problem

The user does **not** choose a target number of sites, target field days, or a budget that ACSP then
fills. Those are outputs of the algorithm.

The user supplies only physical movement constraints that ACSP cannot infer safely, for example:

- the field-entry / hub node;
- which travel edges actually exist;
- which movement modes are available (`walk`, `road`, `trail`, `ferry`, etc.);
- unavailable / closed links.

ACSP must never invent a straight-line movement edge when the real network does not contain one.
An undeclared sea crossing, cliff crossing, flight, or other missing edge is unreachable.

The operational target is therefore:

```text
occurrence-conditioned regional screen
        -> local candidate universe
        -> set-level coverage order
        -> physically reachable movement graph
        -> coverage-versus-effort frontier
        -> automatically recommended survey size / hours / days
```

A legacy explicit-day budget remains a what-if tool, not the default scientific object.

## Inputs already present in the repository

- training occurrences: `field_validation/campanula_microdonta/development_data/gbif_training_occurrences_through_2025.csv`
- field detections: `field_validation/campanula_microdonta/locations_2026.csv`
- 500 m field clusters: `field_validation/campanula_microdonta/development_data/detection_clusters.csv`
- cached candidate pool: `field_validation/campanula_microdonta/development_data/candidate_pool.csv`

The development target contains 19 field-detection clusters across Oshima, Toshima, Niijima,
Shikinejima, and Kozushima.

## Inverse-development sequence

### 1. Freeze an outcome-free candidate / coverage order

Candidate generation and set-level coverage order are computed from pre-2026 information only. The
2026 field coordinates are not read during this stage.

### 2. Read the 19 field clusters only after the order is fixed

The field clusters are then used as development labels to diagnose:

- how many realized clusters the candidate universe can reach at 1 km;
- the first prefix at which each additional realized cluster becomes recoverable;
- whether the bottleneck is candidate generation, compression, or stopping too early;
- which structural changes improve the development loss.

This is intentional reverse engineering, not validation.

### 3. Add real human movement constraints

When an auditable road / trail / walking / ferry matrix is available, apply an explicit mode
allow-list before scheduling. Missing or disallowed edges remain unreachable. Do not substitute the
straight-line proxy to complete the network.

### 4. Infer survey effort rather than requesting it

For every reachable prefix, compute the cumulative set-level coverage and total operational effort.
The automatic policy selects the diminishing-return knee of this frontier and reports:

- recommended survey stops;
- recommended total hours;
- recommended field days under the taxon protocol;
- unreachable candidate prefixes.

The algorithm may use taxon/protocol defaults for per-site search effort and daily work capacity;
these are model assumptions, not a user-specified target budget.

### 5. Freeze the learned design before generalization tests

Campanula can be used to choose the architecture, loss function, stopping rule, and operational
representation. Once those are fixed, new untouched taxa must be used to test whether the design
transfers. Campanula itself cannot establish generality.

## Guardrails against a trivial reverse-engineered solution

Field coordinates may be used to score development experiments **after** candidate generation and
ordering, but never as inference-time features.

Disallowed inference-time inputs include:

- 2026 field latitude / longitude;
- distance to a 2026 field detection;
- field cluster identifiers;
- whether a candidate recovered a field cluster.

Allowed uses of the 2026 outcomes include diagnosing which experimental architecture failed, choosing
the next development experiment, and selecting a final architecture before untouched validation.

## Current implementation

`research/campanula_inverse_effort_development.py` implements the first reproducible inverse loop:

1. create the geometry-only coverage order without reading field detections;
2. read the 19 clusters and calculate the full prefix recovery curve;
3. report the maximum reachable cluster count and first prefix reaching it;
4. optionally accept a real travel matrix plus explicit allowed movement modes;
5. when a matrix is supplied, infer the coverage-effort knee without a user day budget.

The movement-constrained API is `acsp.infer_recommended_effort_from_matrix()`. It has no
straight-line fallback.

## Promotion rule

A method leaves this development sandbox only after:

- the Campanula inverse loss has been made explicit and the architecture is frozen;
- the frozen rule uses no 2026 field label at inference time;
- movement feasibility is represented only by explicit available edges/modes;
- target site count / days are outputs rather than tuned user budgets;
- random taxon-region validation uses no Campanula-tuned outcomes;
- negative untouched validation results are retained and are not used for retuning the final test.
