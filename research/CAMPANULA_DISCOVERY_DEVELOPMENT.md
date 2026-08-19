# Campanula development contract: frozen ecological support -> reachability-first planning

## Status

`Campanula microdonta` is **development data, not an independent validation cohort**. The 2026 field outcomes have already been inspected and may be used only for post-freeze diagnosis and reproduction checks. The frozen cross-taxon Practical Core / retrospective evidence remains separate and unchanged.

The active Campanula line is no longer a search for a smaller field-tuned finite Top-k patch set. The finite-patch experiments were useful diagnostics but failed robustness or automatic stopping tests. The retained ecological object is the already frozen **leave-one-prototype-out consensus support envelope** recorded in `research/campanula_development_freeze_v1.json`.

## Frozen ecological object

Inputs are fixed before 2026 outcomes are opened:

- pre-2026 GBIF occurrence cache through 2025;
- 500 m occurrence thinning;
- 18 Campanula occurrence prototypes;
- full-island 22,784-cell candidate universe derived from frozen GSI DEM coverage;
- pinned ESA WorldCover 2021 NDVI composite;
- NDVI-state support ranking;
- internal leave-one-prototype-out consensus.

The frozen primary 1-km support rule is:

- support threshold: `0.09945575892925262`;
- archived numerical semantics: each leave-one-prototype-out support-rank vector is cast to `float32` before the consensus median; threshold inclusion is `rank <= threshold + 1e-12`;
- reproduction runtime: **Python 3.12**, matching the original freeze workflow run `31892691452`; Python 3.11 reproduced the biological 19/19 endpoint but moved five threshold-boundary cells (`2367 -> 2362`), so the interpreter line is part of the numerical reproduction contract;
- frozen development artifact: workflow run `31856717236`, artifact digest `sha256:d05de653400abc76537aeeb3554506fbf8fd0e197f381401cb3a03e69b058ce8`;
- expected canonical cells: **2,367**;
- archived Campanula development recovery: **19/19**;
- archived maximum nearest distance: **0.8687897057613438 km**.

This object is an occurrence-conditioned robust survey-support envelope. It is **not** occupancy probability, calibrated suitability probability, or a validated finite Top-k policy.

## Active operational sequence

The user does **not** choose survey days, target site count, or a survey budget. The user supplies only physical constraints ACSP cannot infer safely: hub, explicit movement edges, and allowed movement modes.

```text
frozen robust ecological support envelope
        ↓
bounded same-island survey patches
        ↓
explicit allowed movement graph
        ↓
directed hub round-trip reachability
        ↓
set-level coverage on reachable patches
        ↓
coverage-versus-effort frontier
        ↓
automatic diminishing-return knee
        ↓
recommended patches + hours + days
```

Missing movement edges remain missing. ACSP must not invent straight-line sea, cliff, road, trail, ferry, or flight links. Movement is an operational constraint and never becomes biological suitability.

The current exact reproduction exports **2,367 eligible cells as 134 bounded patches**: Oshima 96, Niijima 20, Kozushima 13, Toshima 4, and Shikinejima 1. These 134 patches are the ecological candidate universe, **not** a user target or survey budget. Operational reachability and the automatic effort knee determine which subset is recommended for an actual trip.

## Why finite patch compression is not the active ecological target

The historical 5% support-patch universe and its field-informed minimum cover were diagnostics, not the frozen scientific product.

Retained findings:

- old restricted candidate pools reached only 13/19; full-island generation removed that upstream ceiling;
- a sharp canonical finite-patch diagnostic once reached 19/19 in 32 patches, but the finite policy failed prototype-deletion robustness and was explicitly rejected for freeze;
- an 11-patch field-outcome minimum cover exists only as a diagnostic lower bound and is not an inference target;
- rebuilding the nominal 32-patch coefficients on the current area-safe branch reaches complete recovery later, confirming that the historical 32-patch number should not be treated as a stable benchmark.

Therefore development no longer optimizes `32 -> 11` using Campanula field outcomes.

## Negative experiments retained as provenance

These experiments are scientifically informative but no longer runnable competitors in the active CI path:

1. **Pointwise inverse classifier**: cross-fit complete-recovery prefix 82 patches; full-fit 86. Independent patch classification did not reproduce set complementarity.
2. **Prototype-coverage knee**: 19 patches, 11/19. Sparse known occurrences are not a valid stopping/completeness signal.
3. **Support-envelope mass coverage**: knee 20 patches, 13/19; first complete prefix 38. Support area underweights small separated structures.
4. **Equal support-fragment representation**: knee 22 patches, 13/19; complete recovery only at 87. A nearby fragment cannot safely stand in for another fragment at a 1-km field endpoint.
5. **Pure within-island spatial k-center**: knee 13 patches, 9/19; complete recovery only at 87. Geographic dispersion alone is insufficient.

The rejected fragment, k-center, and 32-patch structure-diagnostic runners have been removed from the active repository path.

## Active runnable path

The Campanula ecological-to-operational bridge is:

- `research/campanula_robust_support_patch_export.py`
- `.github/workflows/campanula-inverse-development.yml` (workflow display name: `Campanula robust support export`)
- `acsp.auto_plan.plan_auto_effort()` for the separate explicit-movement operational layer.

The exporter must first reproduce the archived 2,367-cell / 19-of-19 contract exactly. Only then may its bounded support patches be passed to the reachability-first operational planner. The exported schema already carries the required operational keys (`site_id`, `latitude`, `longitude`, `survey_area_id`) while retaining ecological provenance fields.

## Guardrails

Everything used to construct an inference-time support cell, patch, ordering, reachability result, or stopping point must be fixed without 2026 field coordinates or recovery labels.

Disallowed inference-time inputs include:

- 2026 field latitude / longitude;
- distance to a 2026 field detection;
- field cluster identifiers;
- whether a candidate or patch recovered a field cluster;
- extending a prefix until all field clusters happen to be recovered.

Allowed field use is limited to post-freeze reproduction checks and development diagnosis.

## Promotion rule

No Campanula-derived operational rule is promoted merely because it looks good on Campanula. Promotion requires:

1. exact reproduction of the archived ecological freeze;
2. an explicit outcome-blind preprocessing and operational algorithm;
3. no hidden post-field threshold or site-count extension;
4. movement represented only by explicit available edges/modes;
5. untouched taxon-region evaluation after freeze, with failures retained;
6. no retuning on the final untouched cohort.
