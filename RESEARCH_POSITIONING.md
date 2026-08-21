# Research positioning and publication goals

## Current claim status

`VALIDATED_PRODUCT_CONTRACT.md` is authoritative for the independently validated ACSP product. The current supported scientific product is the **non-ranked robust candidate-patch set**, not a ranked-zone, SDM-re-ranking, route, day-budget, access-efficiency, or integrated-score product.

The broader research ideas and operational workflows below remain useful as software capabilities, historical hypotheses, secondary analyses, and future prospective validation targets. They must not be used to broaden the current validated claim unless separately frozen and validated.

The current validated core is:

- occurrence-conditioned environmental support;
- leave-one-prototype-out robust support;
- frozen 2.5% consensus tier;
- float32 support worlds;
- 1 km same-area deterministic complete-link aggregation;
- bounded candidate patches with no priority ranking;
- 96 taxon-region pairs / 480 folds as the independently confirmed frame.

`Campanula microdonta` remains development and freeze-regression evidence, not an untouched cross-taxon confirmation cohort.

This document defines the broader scientific purpose, novelty, intended users, historical hypotheses, and future validation strategy of ACSP.

It is a design guide for AI coding agents and collaborators. It is not a final literature review or manuscript draft.

## Core scientific purpose

ACSP is a field-survey planning tool whose validated core converts occurrence information into robust bounded candidate patches while keeping operational planning layers separate.

Its broader application purpose is to help researchers inspect, select, export, visit, and validate candidate survey locations without requiring an SDM.

The app is not primarily a general SDM teaching tool, a full-featured all-record modeling platform, or a replacement for specialist ecological modeling software.

The current validated scientific question is:

> Can occurrence-conditioned environmental support be reconstructed robustly into bounded candidate patches that recover held-out regional occurrences better than matched random candidate sets under a frozen cross-taxon protocol?

A broader operational question remains:

> How should researchers use those candidate patches, optional SDM/SSDM evidence, maps, and field observations to decide what to visit next?

The second question is downstream of the validated candidate-patch product and contains components that still require separate prospective validation.

## Main workflow

### Validated single-species core

1. Load occurrence records from GBIF or a researcher-owned coordinate CSV.
2. Build occurrence-conditioned environmental support using the frozen validated method.
3. Reconstruct leave-one-prototype-out robust support.
4. Retain the frozen 2.5% consensus tier.
5. Aggregate support into 1 km same-area deterministic complete-link candidate patches.
6. Export or inspect the non-ranked candidate-patch set.

No SDM, integrated candidate score, route, day count, or monetary budget is required inside this validated path.

### Optional operational single-species workflow

After the validated patch set exists, the application may additionally support:

- map-based inspection and manual selection;
- historical occurrence-supported candidate tables;
- optional SDM using independent QC, bias reduction, and prediction extent;
- clearly labeled model-only exploration;
- selected-site lists, Google Maps links, CSV/KML/HTML outputs;
- prospective field-validation records.

These features are useful but are not automatically part of the independently validated candidate-patch claim.

### Genus / multi-species workflow

Genus mode remains an operational and research extension rather than part of the current single-species robust-patch confirmation claim. It can support:

1. genus-level occurrence retrieval or uploaded researcher data;
2. observed species-richness summaries;
3. observed richness hotspot candidates;
4. optional SSDM predicted richness;
5. exploratory multi-species sampling decisions;
6. exports for biodiversity, taxonomic, phylogeographic, or evolutionary sampling.

## Intended users

The app should support:

- field ecologists selecting survey sites for a focal species;
- researchers studying poorly known, rare, or sparsely recorded species;
- taxonomists and biodiversity researchers planning multi-species or genus-level sampling;
- phylogeographic and phylogenetic researchers deciding which regions, islands, mountains, range edges, or sampling gaps to include;
- researchers using their own unpublished or historical coordinate records rather than GBIF;
- teams that need a transparent, shareable, map-based workflow for fieldwork planning.

## Scientific novelty

### 1. A robust finite candidate-patch object rather than only a pointwise prediction surface

Many occurrence-data and SDM workflows end with a distribution or suitability map. The validated ACSP core instead returns a finite set of bounded candidate patches derived from occurrence-conditioned support under a frozen robustness rule.

The candidate patches are deliberately not presented as calibrated occupancy probabilities, exact occupied sites, or priority ranks.

### 2. Candidate generation is separated from downstream operational optimization

The validated core answers where robust ecological support persists under leave-one-prototype-out reconstruction. It does not claim to solve route optimization, budget allocation, field-day scheduling, access, or detectability.

This separation prevents operational heuristics from being mistaken for independently supported ecological inference.

### 3. SDM/SSDM are optional evidence layers, not prerequisites for the validated core

SDM should not be mandatory for candidate-patch generation.

When used operationally, SDM/SSDM output should remain clearly distinguished from the robust candidate-patch object and must not silently alter validated patch membership.

### 4. The app can continue beyond the validated core without broadening the claim

The application can still provide:

- map-based patch or candidate inspection;
- selected-site lists;
- Google Maps links;
- CSV, KML, and HTML outputs;
- optional SDM/SSDM analyses;
- field-validation templates.

These features make the software useful for real fieldwork while the scientific claim remains bounded by `VALIDATED_PRODUCT_CONTRACT.md`.

### 5. The app is not limited to GBIF

Researchers can upload their own coordinate CSV files.

This allows the same occurrence-record-to-candidate-patch logic or downstream operational workflows to be applied to:

- unpublished sampling records;
- herbarium or museum coordinates;
- laboratory databases;
- historical surveys;
- citizen-science exports;
- previous field campaigns.

### 6. Field validation remains the next route to claims about effort and detection

Prospective field data are required before ACSP can support claims about:

- accessibility;
- detection probability;
- abundance;
- flowering or phenology;
- newly confirmed populations;
- discoveries per field day;
- route efficiency;
- benefit from SDM/SSDM re-ranking.

The robust candidate-patch confirmation does not establish those quantities.

## Literature gap to address

Existing research and software commonly address one or more of the following:

- occurrence-data retrieval and visualization;
- SDM or SSDM model construction;
- sampling-bias correction;
- environmental-variable selection;
- spatial validation;
- biodiversity or richness prediction;
- reserve/survey optimization;
- phylogenetic or phylogeographic analysis after samples are collected.

The current ACSP contribution should be framed narrowly around a reproducible bridge from occurrence information to a **robust finite candidate-patch set**, with operational site selection handled as a downstream layer rather than folded into the validated ecological core.

## Current supported claim

The supported claim is the frozen cross-taxon robust candidate-patch recovery result encoded in `acsp.validated_robust` and summarized in `VALIDATED_PRODUCT_CONTRACT.md`.

Permitted interpretation:

- ACSP produces occurrence-conditioned robust regional candidate patches under a fixed reconstruction and aggregation rule;
- those patches have passed the frozen cross-taxon retrospective confirmation used by the repository;
- the result supports candidate-patch recovery, not exact-site occupancy or universal operational superiority.

Do not infer from that result that:

- candidate patches are ordered by priority;
- integrated score weights are validated constants;
- SDM/SSDM improves patch selection;
- routes or budgets are optimized;
- access or detectability is known;
- field efficiency has been demonstrated.

## Historical / future research hypotheses

The following remain legitimate research questions but are not current validated conclusions.

### H1. Downstream site ranking

Do downstream site-ranking rules applied to validated patches improve prospective field detection relative to matched controls?

### H2. SDM value for sparse records

Can optional SDM evidence identify useful exploratory populations that the robust occurrence-conditioned patch core does not capture?

### H3. Evidence integration

When prospective field data exist, do combinations of robust patch membership, local habitat evidence, and model evidence improve decisions compared with each evidence source alone?

### H4. Genus / SSDM value

Can observed richness and SSDM extensions improve multi-species sampling efficiency for taxonomic, phylogeographic, or phylogenetic work?

### H5. Operational effort

Can access, route, day-budget, phenology, and non-detection data be learned prospectively to improve survey yield without contaminating the ecological candidate-generation claim?

## Recommended field-validation data

Field-validation exports should support recording:

- candidate patch ID and downstream site ID where applicable;
- candidate source / operational selection rule;
- SDM suitability or SSDM predicted richness when used;
- accessibility and access mode;
- survey date and observer;
- target-species presence or absence;
- abundance or abundance class;
- flowering status;
- number of species detected;
- whether a newly confirmed population was found;
- habitat notes;
- photographs, specimens, or DNA samples collected;
- survey effort and comments.

Priority rank or priority score may be recorded for operational experiments, but their presence in a field template does not make them part of the validated core.

## Retrospective validation boundary

Retrospective validation of the current core must preserve the frozen candidate-patch method and avoid leakage from held-out occurrence coordinates.

The confirmed candidate-patch product should be distinguished from older distance-excluded Top-k, integrated-score, comparator, and ranking analyses retained in the repository. Those older experiments are important provenance and negative/secondary evidence, but they do not redefine the current validated product.

Random point-level train/test splits are not sufficient because duplicated and nearby occurrence records leak spatial information.

Any new candidate-generation method that changes support representation, the 2.5% tier, support-world precision, patch merge distance, or patch membership requires a new predeclared development and confirmation cycle.

Model-accuracy validation should remain separate from candidate-patch validation. Prospective field validation should remain separate again, because access, effort, detectability, and non-detection are not recoverable from retrospective GBIF proximity alone.

The superseded four-island protocol remains under `legacy/` for provenance.

## Design implications for AI coding agents

When making implementation decisions, prioritize:

1. preservation of the frozen validated candidate-patch path;
2. explicit separation between candidate generation and downstream ranking/routing;
3. occurrence-based operation without requiring SDM;
4. optional SDM/SSDM with clear exploratory labeling;
5. CSV upload parity with GBIF workflows;
6. map-first inspection and export;
7. field-validation outputs for future prospective learning;
8. preservation of negative experiments and historical artifacts;
9. no reuse of inspected development taxa as untouched confirmation;
10. scientific transparency over feature quantity.

Do not add complexity merely because a modeling or optimization option exists.

A feature should be described as validated only when its own endpoint was frozen and passed independently.

## Anti-rollback rules

Do not remove or weaken these core concepts:

- `VALIDATED_PRODUCT_CONTRACT.md` governs the current validated product;
- validated robust candidate patches are non-ranked and planner-free;
- historical ranking/routing/SDM layers remain downstream unless separately validated;
- occurrence-supported operation must remain available without SDM;
- SDM-high exploration candidates must remain clearly labeled exploratory;
- researcher-owned CSV uploads must remain a first-class input;
- genus mode and SSDM remain available as broader research/operational extensions;
- field validation remains necessary for access, detectability, phenology, abundance, and efficiency claims;
- `Campanula microdonta` remains development/freeze-regression evidence, not untouched confirmation;
- the main interface should remain map-first and fieldwork-oriented.
