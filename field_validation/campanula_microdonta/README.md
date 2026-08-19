# *Campanula microdonta* development dataset

> **Status: development data, not independent confirmation.**
>
> The 2026 field outcomes have been inspected and have already influenced ACSP development. They therefore cannot support an independent validation claim. This dataset is used deliberately to reverse-engineer candidate generation, patch compression, ranking, and stopping rules before any resulting method is frozen and taken to untouched taxa.

## Current development target

`locations_2026.csv` contains 28 positive GPS rows from the 2026 Izu Islands survey. The 500 m clustering cache contains **19 field-detection clusters** across Oshima, Toshima, Niijima, Shikinejima, and Kozushima.

These rows are positive detections only. They cannot estimate detection probability, specificity, false absence, or discoveries per field day without a complete visit/effort log.

The old regional 10 km endpoint is not informative for this within-island development problem. The active diagnostic radius is 1 km, with smaller radii used only as sensitivity checks.

## What the old candidate pools established

Historical 97/102-candidate pools reached only 13/19 clusters within 1 km. That failure established that the old hierarchical candidate universe was incomplete; it is retained as development history rather than an active planning implementation.

The active full-island development subsequently removed that ceiling. Using only pre-2026 GBIF occurrences plus public fine-scale environmental inputs, the full-island generator can make all 19 clusters reachable. The current bottleneck is therefore **patch compression/ranking**, not basic candidate generation.

## Active inputs

`development_data/` preserves the offline development inputs and labels:

- `gbif_training_occurrences_through_2025.csv` — pre-2026 occurrence evidence;
- `detection_clusters.csv` — 500 m clusters derived from the inspected 2026 field detections;
- `candidate_pool.csv` — historical candidate pool retained for failure diagnosis;
- `manifest.json` — provenance.

The full-island inverse workflow additionally rebuilds the land-grid universe from the frozen GSI DEM artifacts and pinned ESA WorldCover NDVI input.

## Active development path

The current workflow is `.github/workflows/campanula-inverse-development.yml`.

Its sequence is:

```text
pre-2026 GBIF + frozen GSI DEM
        ↓
outcome-blind full-island candidate universe
        ↓
pinned NDVI state representation
        ↓
outcome-blind patch universe + patch features
        ↓
open 2026 field clusters only after features are frozen
        ↓
minimum set-cover family diagnosis
        ↓
learn outcome-blind patch utility from oracle-compatible membership
        ↓
leave-one-island-out internal development cross-fit
```

`research/campanula_inverse_patch_learning.py` does **not** learn one arbitrary MILP solution. A patch is labeled `oracle_compatible` when it can occur in at least one minimum-size field-outcome cover, and `oracle_necessary` when excluding it increases the minimum cover size. The model learns compatibility using only outcome-blind patch attributes.

The existing development gap is approximately:

- best existing outcome-blind complete-recovery policy: about 32 patches;
- field-outcome minimum set-cover diagnostic: about 11–12 patches.

The scientific question is whether region-agnostic, outcome-blind patch structure can close that compression gap without reading field coordinates at inference time.

## Retained field-recovery utilities

`analyze.py` and the package-level field-recovery helpers remain useful for descriptive positive-detection recall and same-area random comparisons. They are diagnostics, not an external-validation pipeline.

The old `run_temporal_external_validation.py`, area-balanced validation comparison, and their GitHub Actions workflow were removed because they assigned this already-inspected taxon an obsolete external-validation role.

## Scientific boundary

Campanula can establish an algorithmic design, reveal failure modes, and provide development labels. It cannot establish generalization.

Promotion requires:

1. freeze the Campanula-derived rule and preprocessing;
2. do not retune it after opening the new evaluation cohort;
3. test on untouched taxon-region data with failures retained;
4. keep movement/accessibility as an operational constraint rather than ecological suitability.
