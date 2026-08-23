# Geographic framing development v1 — rejected local-component baseline

## Status

**Development-only negative result. Do not promote this framing rule to the validated ACSP product.**

This directory freezes the first automatic geographic-framing experiment under Issue #135. The validated Japanese name-only product remains the pre-existing 12 fixed Japanese rectangles. No production adapter, candidate-patch rule, movement rule, or validated claim is changed by this experiment.

## Frozen method

Protocol: `../acsp_geographic_framing_development_protocol_v1.json`

Protocol fingerprint:

`887526145c4fc0e2c9c3986c8424b4814b50155108a937b5d6a613b2ee974c0f`

Method ID: `training_block_component_10km_padding_v1`

The rule used training occurrence coordinates only:

1. assign records to the existing global 0.1-degree spatial blocks;
2. form 8-neighbour connected components of occupied training blocks;
3. retain every component, including singletons; no remote-noise deletion;
4. pad each component envelope by the already-frozen 10 km primary recovery radius;
5. deterministically union overlapping padded frames.

Held-out coordinates, outcomes, SDM/SSDM values, ranking scores, user bounds, site count, survey days, and monetary budget are not inputs to frame construction.

## Development evidence

The already-opened robust-patch v2 cohort was repurposed as **framing development evidence only**:

- 96 unique taxon-region pairs;
- 5 spatial folds per pair;
- 480 declared folds;
- 470 evaluable folds in the re-exported snapshot;
- 10 folds retained as zero because two taxa failed the unchanged upstream v2 export rule (`occurrences occupy fewer than two spatial blocks`).

Once used here, all 96 taxa are permanently non-confirmatory for geographic framing. Campanula was not used as independent confirmation.

The original untouched robust-patch confirmation was **not replayed**. The original workflow had not archived its per-fold occurrence CSVs, so the already-opened taxon identities were re-exported from current GBIF using the unchanged v2 fold rule. The re-exported occurrence snapshot is fingerprinted as:

`4a72414e4916a0d2c870e4ccda4537d997398e859df8a3162683328359535209`

Primary completed development run:

- workflow run: `32573980179`
- artifact: `9476080869`
- artifact digest: `sha256:2fc47e36aec7ca7c06244ffaefd3e49e9786cf80f8dd2fe46790e3e87e90d8d1`

## Result: v1 fails as a general name-only framing rule

Across the full 480-fold intention-to-evaluate denominator:

- mean held-out frame containment: **0.7662**;
- median inferred-frame area / original fixed-region area: **0.5181**;
- mean area ratio: **0.5325**;
- median final frame count: **3**;
- plant mean containment: **0.8581**;
- animal mean containment: **0.6743**.

The method reduced the geographic search area to roughly half of the original fixed region, but about 23% of held-out records fell outside the inferred frames before candidate generation. A downstream ecological candidate algorithm cannot recover a record that has already been excluded from the geographic search universe.

Therefore **candidate-patch end-to-end evaluation was intentionally not run for v1**. The framing layer already failed its prerequisite containment diagnostic.

## Why padding retuning is not the next step

A post-hoc diagnostic classified each v1 miss only after the v1 frame had been frozen and evaluated. Among 1,996 missed held-out records in the 470 evaluable folds:

- **302 (15.1%)** belonged to a full occupied-block component that also contained training records;
- **1,694 (84.9%)** belonged to a held-out-only component with no training block.

For animals, 1,318 of 1,355 misses were in held-out-only components.

This means most failure is not a small gap around a training-supported component. The missing geographic component is absent from the focal training occurrences, so a local occurrence-component geometry rule has no information telling it where that component lies. Retuning the 10 km padding or adding another local distance threshold on these same outcomes is therefore not justified.

A post-hoc single training-coordinate bounding box with the same frozen 10 km padding reached mean containment **0.8806** with median area ratio **0.7835**, but this is only an upper-envelope diagnostic. It is not promoted because it collapses disjunct distributions and still misses roughly 12%.

## Architectural conclusion

The next research architecture should change from:

`focal occurrence components -> narrow inferred frame -> ecological robust support`

to:

`broad outcome-blind search universe -> ecological robust support -> candidate patches`.

The existing 12 fixed Japanese rectangles are one concrete example of an external search-universe prior. The unresolved task is to generalize that search-universe registry without hand-drawn bounds and without choosing its scale from these development outcomes.

## Claim boundary

This experiment does **not** change or weaken the already-confirmed robust candidate-patch core:

- support fraction remains 0.025;
- support worlds remain float32;
- candidate-patch aggregation remains frozen at 1 km same-area complete-link;
- the 96-pair / 480-fold robust-core evidence remains historical evidence for that core, not fresh framing confirmation;
- candidate patches remain non-ranked;
- route/day/budget/access/field-efficiency claims remain outside the validated scientific core;
- Campanula remains development/freeze-regression/operational-smoke evidence only.

A future geographic-framing confirmation must exclude every taxon used in framing development and must include genuinely new geography before any beyond-Japan framing claim is made.
