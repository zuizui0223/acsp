# Campanula development contract: frozen ecological support -> candidate patches

## Status

`Campanula microdonta` is **development data, not an independent validation cohort**. The 2026 field outcomes have already been inspected and may be used only for diagnosis and freeze-reproduction checks. The frozen cross-taxon Practical Core / retrospective evidence remains separate and unchanged.

The active Campanula line is intentionally simple: reproduce the frozen occurrence-conditioned support envelope and export bounded survey-candidate patches. ACSP does **not** infer route, movement mode, field days, site count, or budget in this line.

## Frozen ecological object

Inputs fixed before 2026 outcomes are opened:

- pre-2026 GBIF occurrence cache through 2025;
- 500 m occurrence thinning;
- 18 occurrence prototypes;
- full-island 22,784-cell candidate universe from frozen GSI DEM coverage;
- pinned ESA WorldCover 2021 NDVI composite;
- NDVI-state support ranking;
- internal leave-one-prototype-out consensus.

Frozen primary 1-km support rule:

- support threshold: `0.09945575892925262`;
- each LOO support-rank vector cast to `float32` before the consensus median;
- inclusion: `rank <= threshold + 1e-12`;
- reproduction runtime: **Python 3.12**, matching original freeze run `31892691452`;
- frozen development artifact run `31856717236`, digest `sha256:d05de653400abc76537aeeb3554506fbf8fd0e197f381401cb3a03e69b058ce8`;
- canonical support cells: **2,367**;
- archived development recovery: **19/19**;
- archived maximum nearest distance: **0.8687897057613438 km**.

Python 3.11 retained the 19/19 endpoint but moved five threshold-boundary cells (`2367 -> 2362`), so Python 3.12 is part of the numerical reproduction contract.

This object is an occurrence-conditioned robust survey-support envelope. It is **not** occupancy probability, calibrated suitability probability, or a validated finite Top-k policy.

## Active output

```text
pre-2026 occurrences
        ↓
full-island candidate universe
        ↓
LOO consensus support
        ↓
frozen support threshold
        ↓
bounded same-island patches
        ↓
candidate patch CSV
```

The exact reproduction exports **2,367 eligible cells as 134 bounded patches**:

- Oshima: 96
- Niijima: 20
- Kozushima: 13
- Toshima: 4
- Shikinejima: 1

These 134 patches are the candidate output. They are not a requirement to visit 134 sites and are not subsequently reduced by a hidden field-outcome rule.

## Why finite patch compression is not the target

The historical finite-patch experiments are diagnostics only:

- old restricted candidate pools reached only 13/19; full-island generation removed that upstream ceiling;
- a historical 32-patch diagnostic reached 19/19 but failed prototype-deletion robustness and was rejected for freeze;
- an 11-patch field-outcome minimum cover is only a diagnostic lower bound;
- pointwise inverse classification required 82 patches cross-fit / 86 full-fit for complete recovery;
- prototype-coverage knee: 19 patches, 11/19;
- support-envelope mass knee: 20 patches, 13/19; complete prefix 38;
- equal-fragment representation: 22 patches, 13/19; complete prefix 87;
- pure within-island k-center: 13 patches, 9/19; complete prefix 87.

The conclusion is not to search for another stopping rule on Campanula. The retained scientific object is the robust support envelope and its bounded patch representation.

## Active runnable path

- `research/campanula_robust_support_patch_export.py`
- `.github/workflows/campanula-inverse-development.yml` (display name: `Campanula robust support export`)

The workflow must reproduce the 2,367-cell / 19-of-19 freeze before exporting patches.

## Guardrails

Inference-time support cells and patch boundaries must not use:

- 2026 field latitude / longitude;
- distance to 2026 detections;
- field cluster identifiers;
- whether a candidate recovered a field cluster;
- any extension rule that adds patches until field detections are recovered.

Field outcomes are allowed only for post-freeze reproduction checks and development diagnosis.

## Promotion rule

A generalized candidate-patch method derived from this development line requires:

1. exact reproduction of the archived ecological freeze;
2. outcome-blind candidate and patch generation;
3. no field-tuned finite Top-k or stopping threshold;
4. untouched taxon-region evaluation after freeze;
5. no retuning on the final untouched cohort.
