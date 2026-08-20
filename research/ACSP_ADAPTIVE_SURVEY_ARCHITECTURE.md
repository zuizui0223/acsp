# ACSP candidate-patch architecture

Status: **development architecture**, not a new superiority claim.

## Current algorithmic object

ACSP is being simplified to a candidate generator rather than an end-to-end trip optimizer.

```text
training occurrences
        ↓
domain / information adequacy
        ↓
regional occurrence-conditioned ecological support
        ↓
full local candidate universe
        ↓
robust support reconstruction
        ↓
bounded survey patches
        ↓
candidate patch output
```

The method does not require a user-provided route, movement mode, hub, field-day target, site-count target, or monetary budget. Those concerns may be handled downstream by the field team or a separate tool.

## Scientific boundary

The frozen Practical Core remains the validated regional baseline. Fine-scale development must not be described as occupancy probability or calibrated suitability probability.

The Campanula development case showed that full-domain generation was more important than repeatedly tuning fine-scale filters. The stable retained object is therefore a robust support envelope converted to bounded patches, not a field-tuned Top-k list.

## Retained principles

- full-domain candidate generation;
- spatial occurrence thinning as duplicate control;
- occurrence-conditioned ecological support;
- leakage-safe leave-one-prototype / nested reconstruction where appropriate;
- bounded same-area patches rather than isolated raster-cell centers;
- explicit numerical freeze and reproducibility checks;
- untouched taxon-region evaluation after development freeze;
- negative experiments retained as constraints on future development.

## Demoted or removed from the main line

- user-specified day or monetary budgets;
- automatic field-day estimation;
- movement graphs, hubs, route optimization, road/trail/ferry mode handling;
- automatic coverage-versus-effort stopping rules;
- Campanula field-outcome minimum-cover optimization;
- repeated searches over NDVI thresholds or finite patch counts;
- claims about discoveries per day, detection probability, or route efficiency without prospective effort/non-detection data.

## Role of Campanula microdonta

The 2026 Campanula detections are development data. They are used to diagnose whether a candidate-generation representation is missing real distribution structure, not to serve as an untouched validation cohort.

The current frozen Campanula object is reproduced from pre-2026 occurrences and environmental inputs, then converted to bounded candidate patches. Field outcomes are used only after that construction for reproduction checks and development diagnosis.

## Development rule from this point

1. Keep the output simple: candidate patches.
2. Do not add operational constraints unless a future scientific question requires them.
3. Freeze candidate-generation rules before untouched cross-taxon evaluation.
4. Compare candidate-patch recovery against strong simple baselines under the same evaluation endpoint.
5. Add adaptive survey-yield learning only after prospective attempted-site, non-detection, and effort data exist.

The next scientific gain should come from showing that robust candidate patches generalize across untouched taxa/regions, not from making the operational layer more complicated.
