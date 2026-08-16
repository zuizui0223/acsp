# ACSP adaptive survey architecture

Status: **development architecture**, not a new superiority claim.

This document records the algorithmic structure that has survived repeated ACSP development, nested evaluation, Campanula field-driven development, and cross-taxon failure analysis. Components are retained only when their role is supported, and negative experiments constrain future development.

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

The decision object is closer to

`S*(O, B) = argmax_{S subset E(O), cost(S) <= B} SurveyCoverage(S)`

than to a cell-wise `P(presence | x)`.

The ecological layer constrains where a survey is defensible. The set layer decides how to spend a finite field budget inside that support. Optional SDM/SSDM remains a separate evidence source in the production app and is not required for this non-model decision path.

## Layer 1 — domain and information gate

Before an ecological support surface is trusted, the training data must establish that the requested policy is applicable.

Earlier mixed-taxon work showed that one land-based candidate surface cannot be transferred blindly to marine, coastal, freshwater, and terrestrial taxa. The same issue reappeared when a predeclared outside-Izu plant frame contained seagrasses and an alga.

The research-layer gate now gives observed training-surface support precedence over coarse kingdom labels. A vascular plant with strong land-supported training occurrences may enter the terrestrial policy; a nominal plant with predominantly non-land training support does not. Missing support evidence returns an unverified/inapplicable state rather than silently forcing a terrestrial policy.

The gate remains outcome-free. Held-out recovery cannot decide applicability.

## Layer 2 — occurrence-conditioned ecological support

The surviving ecological role is **support-region reconstruction**, not final Top-k ranking.

Evidence for this separation is strong:

- old Campanula candidate pools could reach only 13/19 field clusters within 1 km, so ranking could never solve the problem;
- full-island generation removed that ceiling;
- static WorldCover composition and the current NDVI transition/gradient variants did not outperform simpler NDVI-state support;
- a Campanula-specific NDVI + microclimate weighted rank compressed the field case but failed on 16 unseen Izu plant taxa;
- after final selection was changed to strong set-level coverage, a narrow NDVI eligibility mask retained a low-budget within-island signal at q=0.10, K=5, r=1 km.

Environmental information therefore currently answers:

> Which parts of the survey domain remain ecologically supported by the observed occurrence states?

It does not directly answer:

> Which cells have the highest calibrated probability of presence?

### Representation failures already learned

A single global nearest-prototype envelope with taxon-specific q chosen by fully nested inner spatial recovery did **not** generalize. At K=5 its lift over pure geographic coverage was only +0.009 with a confidence interval crossing zero; K=10 and K=20 were negative.

A second representation split training occurrence space into robust MST-gap environmental modes and gave every mode equal search opportunity at identical total support area. Multimodality was genuinely detected in 42/80 outer folds, but the representation made fixed-q10 recovery clearly worse at all K. Thus the failure was not solved by simply protecting rare modes equally.

The active representation question is now narrower:

> How much **local prototype agreement** should a candidate require?

The current experiment keeps the same NDVI-state variables and total support area but compares distance to one versus the mean distance to two or three nearest training prototypes. This tests support scale without adding variables or changing survey footprint.

## Layer 3 — training-only support-policy selection

This layer now has a fixed validation architecture even though the best ecological representation is unresolved.

A fixed q=0.10 remains a development reference, not a universal biological constant.

Two lessons are frozen:

1. prototype-LOO environmental reconstruction is the wrong internal objective because internal environmental stability is not downstream survey value;
2. support-policy adaptation must be **fully nested** and optimize the same survey-set recovery objective used at deployment.

For every active representation, the procedure is:

1. outer training / held-out split defines the evaluation world;
2. within outer training only, create identical inner spatial holdouts;
3. construct every predeclared candidate policy from inner training data;
4. select K sites with the same set-level coverage objective used in deployment;
5. compare paired inner-fold recovery against the q=1 geometry-only policy;
6. require a candidate policy to be feasible on every inner fold;
7. if no ecological policy has positive mean inner lift, fall back to q=1;
8. rebuild the chosen policy on all outer training data;
9. only then expose outer held-out coordinates.

The current support-scale experiment selects `(k, q)` inside this unchanged framework, with k in the predeclared set {1,2,3}. Exact ties prefer broader support and then smaller k.

## Layer 4 — set-level survey optimization

This is currently the strongest structural result.

A survey is a set decision, not a collection of independent cell scores. The selected set should avoid wasting slots on overlapping search footprints.

The development selector greedily maximizes newly covered public land-grid cells within the declared survey radius. It is deliberately compared against a q=1 geometry-only control.

This layer absorbed several earlier ideas without retaining their weaker forms:

- geographic complementarity survives as a **set objective**, not as a fixed additive score weight;
- area balancing is treated as a constraint/control problem, not a universal bonus;
- random Top-k remains useful, but a strong geometry-only selector is required whenever geometry alone can dominate random;
- candidate count is not equated with survey budget because large buffered candidate sets can saturate the domain.

The reference Python selector has also been replaced in heavy nested workflows by an exact sparse implementation. Regression tests and a full strict-nested rerun produced byte-identical scientific outputs, so this is computational optimization only.

## Layer 5 — operational field budget and output

K and recovery radius are not inferred biological constants. They represent the current operational evaluation design.

The deployable system should eventually accept field constraints such as:

- number of survey stops;
- survey hours;
- route distance;
- searched area;
- access or ferry/road constraints.

Patch persistence is not a mandatory ecological truth criterion. Campanula development showed that forcing support into persistent connected patches can exclude genuine detections or require excessive expansion. Patch and route representations therefore belong primarily in the operational-output layer.

## Rejected components

The following should not return to the main line without a new predeclared ablation rationale and evidence:

- universal fixed evidence-weight sums as the scientific core;
- independent environmental Top-cell ranking as the transferable selection family;
- Campanula's fixed 90% NDVI + 10% microclimate correction;
- WorldCover composition as a promoted microenvironment feature;
- current NDVI transition/gradient representation;
- mandatory persistent-patch filtering;
- NDVI-driven between-island allocation;
- training-occurrence-count island allocation;
- prototype-LOO environmental reconstruction as support-width selection;
- fully nested q adaptation inside the unchanged single nearest-prototype envelope;
- equal-opportunity MST multimodal support balancing;
- fixed geographic complementarity bonuses applied to every taxon.

Negative results remain evidence. They narrow the algorithm rather than being discarded.

## Conditional rather than rejected

- NDVI state: still the active ecological support signal, but its transferable representation is unresolved;
- terrain / aspect / coast: diagnostics or candidate-domain construction, not a supported universal cross-taxon correction;
- persistent patches: field presentation / route aggregation, not a required support filter;
- prototype consensus: robustness diagnostics, not a guaranteed finite Top-k solution;
- SDM/SSDM: optional model evidence and exploration in the production tool, not a prerequisite for occurrence-supported survey decisions.

## Development rule from this point

Every new experiment must target exactly one unresolved layer.

Current order:

1. local prototype-support scale (active: k=1/2/3, fully nested);
2. spatial support scale only if local prototype scale fails;
3. external integration/freeze of the domain gate;
4. operational route/equal-area budget after ecological support is stable;
5. untouched cross-taxon, cross-island confirmation after the complete procedure is frozen.

An experiment must preserve all other retained components unless it explicitly declares an ablation of one of them. It must use the strongest surviving comparator, not only random.

The frozen 192-pair Practical Core cohort remains separate and untouched by this development line. The previously declared outside-Izu 24-pair cohort also cannot confirm the new domain gate because inspection of its taxon identities directly motivated that gate; a new final cohort must be sampled after method freeze.
