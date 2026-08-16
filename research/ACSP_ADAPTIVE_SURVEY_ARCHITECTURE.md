# ACSP adaptive survey architecture

Status: **development architecture**, not a new superiority claim.

This document records the algorithmic structure that has survived repeated ACSP development, nested evaluation, Campanula field-driven development, and cross-taxon failure analysis. It is intentionally stricter than a list of ideas: components are retained only when their role is supported, and negative experiments constrain future development.

The machine-readable evidence ledger is `research/acsp_algorithm_component_ledger.json`.

## Current algorithmic object

ACSP is not being developed as a universal cell-wise suitability model or as a universal weighted ranking formula.

The current target is a survey decision procedure:

```text
training occurrences O
        |
        v
[1] domain / information adequacy
        |
        v
[2] occurrence-conditioned ecological support E(O)
        |
        v
[3] training-only support-policy selection
        |
        v
[4] set-level survey optimization under budget B
        |
        v
[5] operational patch / route / site set
```

The mathematical decision object is therefore closer to

`S*(O, B) = argmax_{S subset E(O), cost(S) <= B} SurveyCoverage(S)`

than to a cell-wise `P(presence | x)`.

The ecological layer constrains where a survey is defensible. The set layer decides how to spend a finite field budget inside that support. Optional SDM/SSDM remains a separate evidence source in the production app and is not required for this non-model decision path.

## Layer 1 — domain and information gate

Before an ecological support surface is trusted, the training data must establish that the requested policy is applicable.

This layer exists because earlier mixed-taxon work repeatedly showed that one land-based candidate surface cannot be transferred blindly to marine, coastal, freshwater, and terrestrial taxa. The same lesson reappeared when an outside-Izu taxon frame contained aquatic taxa despite being intended as an island plant benchmark.

The gate must be outcome-free. It can inspect taxonomy, training-record land fraction, spatial coverage, record count, and other training-only properties. It cannot inspect held-out recovery to decide applicability.

If the domain is unsupported, the correct output is `not applicable / use another domain policy`, not a forced terrestrial score.

## Layer 2 — occurrence-conditioned ecological support

The surviving ecological role is **support-region reconstruction**, not final Top-k ranking.

Historical evidence for this separation is strong:

- Old Campanula candidate pools could reach only 13/19 field clusters within 1 km, so ranking could never solve the problem.
- Full-island generation removed that ceiling.
- Static WorldCover composition and NDVI transition/gradient variants did not outperform the simpler NDVI-state representation.
- A Campanula-specific NDVI + microclimate weighted rank compressed the field case well but failed on 16 unseen Izu plant taxa.
- After the final selection was changed to strong set-level coverage, a narrow NDVI eligibility mask retained a low-budget within-island signal at q=0.10, K=5, r=1 km.

Therefore environmental information currently answers:

> Which parts of the survey domain remain ecologically supported by the observed occurrence states?

It does not directly answer:

> Which five cells have the highest probability of presence?

## Layer 3 — training-only support-policy selection

This is the principal unresolved layer.

A fixed q=0.10 is retained only as a development reference, not as a universal biological constant.

The first adaptive attempt chose q from leave-one-training-prototype-out environmental reconstruction. It failed: most folds reverted to q=1 and the K=5 policy lost the entire q10 advantage. The important lesson is that **internal model stability is not the same estimand as downstream survey usefulness**.

The active experiment therefore uses fully nested spatial evaluation:

1. outer training / held-out split defines the evaluation world;
2. within the outer training data only, create inner spatial holdouts;
3. for each candidate support breadth q, construct the support mask from inner training data;
4. choose the K-site set with the same set-level coverage objective used in final deployment;
5. score inner held-out occurrence recovery;
6. select q from inner performance only;
7. rebuild the policy on all outer training data using the selected q;
8. only then expose outer held-out coordinates.

If no q<1 improves inner survey recovery, the method falls back to q=1, i.e. pure geographic maximum coverage.

This preserves one algorithm while allowing the ecological constraint to disappear when the training data do not support it.

## Layer 4 — set-level survey optimization

This layer is currently the strongest structural result.

A survey is a set decision, not a collection of independent cell scores. The selected set should avoid wasting slots on overlapping search footprints.

The current development selector greedily maximizes newly covered public land-grid cells within the declared survey radius. It is deliberately compared against a q=1 geometry-only control.

This design absorbed several previous ideas without retaining their weaker forms:

- geographic complementarity survives as a **set objective**, not as a fixed additive score weight;
- area balancing is treated as a constraint/control problem, not a universal bonus;
- random Top-k remains useful, but a strong geometry-only selector is required whenever geometry alone can dominate random;
- candidate count is not equated with survey budget because large buffered candidate sets can saturate the domain.

## Layer 5 — operational field budget and output

K and recovery radius are not inferred biological constants. They represent the current operational evaluation design.

The deployable system should eventually accept field constraints such as:

- number of survey stops;
- survey hours;
- route distance;
- searched area;
- access or ferry/road constraints.

Patch persistence is not a mandatory ecological truth criterion. Campanula development showed that forcing support into persistent connected patches can exclude genuine detections or require excessive expansion. Patch and route representations therefore belong primarily in the operational-output layer.

## What has been rejected

The following should not return to the main line without a new predeclared rationale and evidence:

- universal fixed evidence-weight sums as the scientific core;
- independent environmental Top-cell ranking as the transferable selection family;
- Campanula's fixed 90% NDVI + 10% microclimate correction;
- WorldCover composition as a promoted microenvironment feature;
- current NDVI transition/gradient representation;
- mandatory persistent-patch filtering;
- NDVI-driven between-island allocation;
- training-occurrence-count island allocation;
- prototype-LOO environmental reconstruction as the support-width selector;
- fixed geographic complementarity bonuses applied to every taxon.

Negative results remain evidence. They narrow the algorithm rather than being discarded.

## What is conditional rather than rejected

Some ideas remain useful, but only in narrower roles:

- NDVI state: support eligibility, pending transferable policy selection;
- terrain / aspect / coast: diagnostics or candidate-domain construction, not a currently supported universal cross-taxon correction;
- persistent patches: field presentation / route aggregation, not a required support filter;
- prototype consensus: robustness diagnostics, not a guaranteed finite Top-k solution;
- SDM/SSDM: optional model evidence and exploration in the production tool, not a prerequisite for occurrence-supported survey decisions.

## Development rule from this point

Every new experiment must target exactly one unresolved layer:

1. support-policy selection;
2. domain gate;
3. multi-modal or scale-adaptive ecological support, only if the nested support-policy experiment fails;
4. operational route/equal-area budget after ecological support is stable;
5. untouched cross-taxon, cross-island confirmation after the full procedure is frozen.

An experiment must preserve all other retained components unless it explicitly declares an ablation of one of them. It must use the strongest surviving comparator, not only random.

The frozen 192-pair Practical Core cohort remains separate and untouched by this development line.
