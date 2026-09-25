# ACSP Discovery method contract

This document records the reusable structure that survived the current ACSP development history. It separates **stable invariants** from **components that are allowed to evolve**.

The goal is not to preserve every current formula. The goal is to preserve the scientific logic that prevented repeated failure modes from being reintroduced under new names.

## Stable invariants

### 1. Define the geographic/candidate frame before ranking

A selector cannot recover a site that is absent from its candidate universe. Earlier finite candidate pools failed upstream before any ranking could help.

Therefore:

```text
geographic/component frame
    -> candidate universe
    -> ranking/comparison
```

not:

```text
score everywhere
    -> choose whatever area scores well
```

A local radius is not universal. ACSP Discovery does not silently choose 2 km, 5 km, or another favorable distance after outcomes.

### 2. Treat occurrence records as evidence, not independent populations

Repeated GBIF/specimen coordinates can otherwise masquerade as multiple populations.

Exact-enough records are first converted to bounded population evidence using deterministic complete-link clustering and medoids. Single-link chaining is avoided because it can merge arbitrarily extended strings of records.

### 3. Anchor count alone cannot authorize LOCAL discovery

Public temporal diagnostics showed that later novel clusters are often far from known clusters. In the opened 96-pair development diagnostic, simple nearest-known recovery was only 11.0% within 2 km, 24.6% within 5 km and 39.1% within 10 km.

More replicated anchors made distance more informative, but did not make distance a universal selector.

Therefore LOCAL requires a separately justified ecological/range/component statement. Anchor count is supporting evidence, not a learned threshold.

### 4. ABSTAIN is a normal output

If a frozen evidence contract cannot be reconstructed from the available provider data, do not relax precision, enlarge the frame, replace the provider, or use later outcomes as anchors.

Current examples include:

- CIR04 public alpine smoke: 4 frozen anchors required, 3 strict historical population clusters reconstructible -> abstain;
- CIR01 public wetland smoke: no strict historical population anchor inside the predeclared Shikoku frame -> abstain.

These are evidence-adequacy failures, not negative structural-model results.

### 5. Keep evidence lanes separate

The opened 96-pair diagnostic showed partial but modest complementarity between nearest-known and regional environmental support. It did not justify a fitted blend.

Keep at least the following concepts separate:

- LOCAL / anchor-informed continuation;
- DETACHED / structural or environmental component;
- SENTINEL / broad or uncertainty context;
- spatially balanced comparator.

Do not fit a distance-environment weight on consumed outcomes and promote the blend as prospective.

### 6. Structural/process information must add something genuinely new

Generic terrain similarity, NDVI, WorldCover category and increasingly complex rankers repeatedly failed to localize fine occupied patches reliably.

The next useful information should represent biological structure/process rather than another generic similarity score, for example:

- wetland/moisture continuity;
- alpine landform continuity;
- open-grassland fragment continuity;
- coastal/island structure;
- forest-edge structure.

Feature families remain explicit and source-backed. The package does not infer a family from favorable outcomes.

### 7. Human movement is downstream of ecological support

Ecological candidate generation (`G_E`) and human survey feasibility (`G_F`) are separate graphs.

Roads, permissions, travel time and user movement restrictions must not create ecological support. They can constrain which already-justified candidates are reachable.

The user should eventually specify movement restrictions; the system may infer route/day/budget/stopping only after field-yield data are sufficient.

### 8. Compare on the same frame

Every proposed selector should be compared against strong same-frame baselines, at equal candidate count or later equal field effort.

Current reusable comparators include:

- nearest-known for LOCAL;
- deterministic spatial balance;
- random same-pool where appropriate.

A candidate-count comparison is not yet a matched field-effort comparison.

### 9. Freeze provenance before outcomes

Candidate frame, provider release, source hashes, structural family, graph semantics and method identity must be fixed before opening outcomes used for validation.

Provider failures and unavailable layers are part of evaluability. They are not silently repaired after outcomes.

### 10. Preserve the validated product boundary

The independently validated Japanese 2.5% / 10-km regional candidate-patch product remains a separate closed product.

`acsp.discovery` is experimental until separately confirmed. Fine/local discovery failures do not reopen the validated regional result, and regional validation does not imply local exact-site validity.

## Components allowed to evolve

The following may improve without changing the invariants above:

### Provider adapters

Examples:

- GBIF or other occurrence providers;
- GSI or other DEM providers;
- ESA WorldCover or another globally available land-cover source;
- coastline/hydrography/vegetation providers.

Adapters should normalize to provider-neutral schemas and retain source identity, release/version and SHA-256 provenance.

### Structural families

A new family may be added when a source-backed biological mechanism/structure is identified. It should declare:

- ecological question;
- required raw columns;
- source roles;
- graph semantics;
- outcome-blind transforms;
- strong same-frame comparators.

A new family should not be created merely because one consumed species responds poorly to existing families.

### Candidate-frame generators

Regional, local, detached and sentinel frames can use different generators. The frame generator must be declared before evaluation and must not use held-out outcomes.

### Survey-feasibility layer

Movement constraints, access modes, route construction and field logistics can evolve downstream once ecological candidates are frozen.

### Field-yield/stopping model

This remains unidentifiable from positive-only occurrence data. It can be developed after complete field logs include:

- searched site/route ID;
- date/phenology;
- duration/distance/area searched;
- observer effort;
- detection/non-detection;
- incomplete-search reason;
- access failure separately from biological non-detection.

Only then can ACSP estimate marginal discoveries per hour/day, infer field days/budget, or learn a stopping rule.

## Standard development loop

For each new structural/process idea:

```text
1. source-backed mechanism/structure
2. freeze input contract and frame
3. construct full deterministic method order
4. compare against strong same-frame baselines
5. keep all declared units, including failures/abstentions
6. diagnose failure without retuning consumed outcomes
7. if promising, freeze a generic rule
8. test on a disjoint cohort
```

The package should make this loop easier to execute, not make it easier to bypass.
