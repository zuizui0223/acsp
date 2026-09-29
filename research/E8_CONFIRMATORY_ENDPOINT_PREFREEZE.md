# E8 confirmatory endpoint — pre-result freeze

This endpoint is frozen **before** the fresh v3 observation-balance result is known.

It activates only if v3 produces exactly 48 unique taxa arranged as 24 animal–plant pairs in 12 regions and passes all observation-balance gates.

## Question

After balancing biodiversity observation architecture by construction, is the validated ACSP robust-support recovery lift larger for animals than plants?

## Primary unit

One matched animal–plant pair.

There will be 24 equal-weight pairs.

## Ecological endpoint

For each taxon, run the already validated Japanese robust-patch method unchanged:

- 2.5% robust-support tier;
- float32 leave-one-prototype-out worlds;
- 1-km complete-link patch aggregation;
- five declared spatial folds;
- 10-km primary recovery;
- same-size random candidate-set comparator;
- failed/empty folds retained as zero.

The taxon value is mean robust-minus-random lift across five declared folds.

The pair value is animal lift minus its matched plant lift.

## Success gate

All must hold:

1. mean paired difference ≥ **+0.02**;
2. 30,000-draw paired bootstrap 95% lower bound > **0**;
3. 30,000-draw one-sided sign-flip **P < 0.05**.

No taxon or matched pair can be replaced after outcome opening.

## Interpretation ceiling

A pass would establish a taxonomic difference in ACSP recovery performance **within this observation-balanced Japanese cohort**.

It would not establish a causal effect of taxonomic kingdom, a life-history mechanism, or global universality.

A failure would close E8 without retuning the ACSP method or the matching/inference rules.
