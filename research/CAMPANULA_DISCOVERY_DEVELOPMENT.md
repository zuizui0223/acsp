# Campanula discovery-algorithm development contract

## Status

`Campanula microdonta` is **development data**, not an independent validation cohort.
The 2026 field outcomes have already been inspected and previously motivated changes to ACSP.
They may therefore be used freely to diagnose failures, tune candidate generation, and compare
experimental strategies. They must not be presented as untouched evidence of generalization.

The frozen cross-taxon Practical Core and the frozen 192-pair confirmation artifacts remain
separate. Nothing in this development track changes their fingerprints, taxa, splits, or claims.

## Inputs already present in the repository

- training occurrences: `field_validation/campanula_microdonta/development_data/gbif_training_occurrences_through_2025.csv`
- field detections: `field_validation/campanula_microdonta/locations_2026.csv`
- 500 m field clusters: `field_validation/campanula_microdonta/development_data/detection_clusters.csv`
- leakage-controlled validation candidate pool: `candidate_pool.csv`
- real-use survey pool may be explored separately, but can never be used to claim independent validation.

Current development target contains 19 field-detection clusters across Oshima, Toshima, Niijima,
Shikinejima, and Kozushima.

## Primary development objective

The first objective is **candidate-generation completeness**, not Top-5 superiority.

A candidate generator passes the development coverage gate only when every one of the 19 field
clusters has at least one generated candidate within 1 km:

`candidate_generation_recall_1km = 19 / 19`.

This gate deliberately ignores the final candidate ranking. A ranking method cannot recover a
field cluster if candidate generation never placed any candidate near it.

The current cached pools fail this gate: only 13 of the 19 clusters are reachable within 1 km.
Therefore candidate generation is the active development bottleneck.

## Development order

1. **Generation gate** — make the candidate universe reach all 19 clusters at 1 km using only
   pre-2026 GBIF occurrences plus environmental / terrain / landscape inputs available at decision time.
2. **Compression gate** — after 19/19 is reachable, reduce the candidate universe into stable,
   interpretable patches or representative survey sites without losing that coverage.
3. **Budget curve** — measure recall at equal budgets (Top-5, Top-10, route/time budget) rather than
   forcing 19 dispersed clusters to be recoverable by exactly five points.
4. **Ablation** — identify which structural components are necessary: full-island terrain search,
   occurrence-conditioned analogue, multi-scale support, patch persistence, connectivity, etc.
5. **Only after the algorithm is frozen** — move to random cross-taxon / cross-region validation.

## Guardrails against a trivial 19/19 solution

Field coordinates are labels for development diagnostics only. They may be used to decide whether
an experiment worked, but must not be read by the candidate generator or scoring function.

Disallowed inference-time inputs include:

- 2026 field latitude / longitude;
- distance to a 2026 field detection;
- field cluster identifiers;
- whether a candidate recovered a field cluster.

The generator may use the field outcomes only after generation to compute development loss and to
choose the next experiment.

## Working hypothesis

The present hierarchy refines only selected parent regions. That creates an artificial ceiling:
large parts of an island never enter the candidate universe even when they contain terrain states
similar to known occurrences.

The next line of development therefore tests **full-island structural search** rather than merely
changing final ranking weights:

- scan the full island at a computationally tractable terrain resolution;
- characterize occurrence-conditioned local terrain states from pre-2026 occurrences;
- find repeated / connected occurrences of those states anywhere on the island;
- retain candidates or patches that remain supported across reasonable scales / thresholds;
- then optimize the finite survey set.

This is intentionally different from fitting a coarse climate SDM and taking its highest cells.
The development question is whether occurrence-supported local structures can be rediscovered
throughout an island strongly enough to include all observed field clusters.

## Promotion rule

Campanula can establish an algorithmic design, but cannot establish generality.

A method leaves this development sandbox only after:

- 19/19 candidate-generation coverage at 1 km is reached without field-label leakage;
- the rule is frozen before new taxa are evaluated;
- random taxon-region validation uses no Campanula-tuned outcomes;
- negative random-validation results are retained and the final test set is not used for retuning.
