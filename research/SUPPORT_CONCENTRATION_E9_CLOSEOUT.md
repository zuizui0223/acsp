# E9 closeout — robust-support concentration is not a supported animal–plant macroecological difference

## Question

Does the frozen ACSP robust-support tier form a more spatially concentrated patch architecture in animals than in plants?

This was an exploratory secondary question generated from the validated 96-pair Japanese confirmation. It was **not** part of the untouched confirmation protocol and is therefore not a new confirmatory endpoint.

## Why raw support area is not the estimand

Every successful fold retains the same frozen 2.5% robust-support tier. Comparing the fraction of selected cells would therefore be nearly tautological.

Instead we quantify how those selected cells aggregate under the already frozen 1-km patch rule:

`C = (selected_cells - patch_count) / (selected_cells - 1)`.

For folds with at least two selected cells:

- C = 0 when every selected cell remains its own patch;
- larger C means more selected cells coalesce into shared patches.

Failed or empty folds have no defined support geometry and are excluded from this descriptive geometry question rather than recoded as concentrated or diffuse.

## Unmatched descriptive signal

Among evaluable folds:

- animals: 172 folds, mean concentration **0.0770**;
- plants: 203 folds, mean concentration **0.0553**.

At first glance the animal support appears more clustered.

## Factorial-design adjustment

The original cohort was intentionally balanced by:

- 12 Japanese regions;
- plant versus animal;
- four historical record-count strata.

We therefore aggregated concentration within taxon–region pair, required at least three evaluable geometry folds, and compared animals and plants **only within the same region × record-count stratum**.

This yielded 29 matched cells.

Animal minus plant concentration:

- mean **+0.00804**;
- median **0**;
- SD **0.0628**;
- 14 positive, 11 negative, 4 ties;
- bootstrap 95% CI **[-0.0144, +0.0306]**;
- one-sided paired sign-flip **P≈0.248**.

The simple animal-greater-than-plant concentration hypothesis is therefore not supported.

## Relation to validated ACSP performance

Across the 74 pairs with at least three evaluable geometry folds, pair-mean concentration was not positively associated with the validated 10-km recovery lift:

- all pairs Spearman rho ≈ **-0.094**;
- animals ≈ **-0.087**;
- plants ≈ **-0.169**.

Thus patch concentration is not an obvious explanation for the larger validated animal lift either.

## Decision

**Close E9 as an exploratory null.**

Do not build a macroecology paper around a plant–animal difference in patch concentration from this cohort.

The more promising question remains E8: why the validated recovery lift is roughly twice as large for animals (+0.1142) as plants (+0.0570), and how much of that contrast is attributable to observation architecture rather than ecological support.

## Provenance

Authoritative confirmation:
- run 32337884576
- artifact 9396133154
- digest sha256:f23c23afe4863f816f2b3a0780d9a39d6eddb383512188a0bf572dcdf055936f

Frozen cohort:
- run 32335791948
- artifact 9394691112
- digest sha256:cc0f949649491439f91e1b90d01d48acbd3f7fffc6833a75105a3bc175a5faf3
