# Aggregate topology cannot identify whether topology-aware medoids change Cirsium survey sites

**Status (19 October 2026):** source-locked, synthetic-only mathematical diagnostic. This is a follow-up to the method-development topology audit (PR #256), component-gap synthesis (PR #273), frozen two-site trial design (PR #274), and first-stage feasibility accounting (PR #277). **Not** an independent ecological sample, site allocation, field observation, or confirmation of candidate recovery. The independently validated Japanese ACSP robust candidate-patch path and the original fresh-SENTINEL three-arm design are untouched.

## Why the original topology percentages cannot resolve the field question

The existing original Cirsium work publishes counts of retained 100-m high-support cells and components: number of 1-km complete-link patches \(P\), internally disconnected patches \(D\), total within-patch fragments \(S\), global Moore-8 components \(G\), and associated cell fractions. These quantities do not encode *where* the retained cells lie within each patch. The two frozen downstream methods choose an **actual retained-cell representative** by different distance objectives:

1. **Topology arm:** minimizer of summed **squared** grid distances among the cells of the largest Moore-8 fragment (with the predeclared tie-break).
2. **Geometry arm:** minimizer of the same squared distances among **all** retained cells in the original patch.

Neither method changes which cells are retained or alters the 1-km complete-link patch boundary. Importantly, a patch with multiple components can yield *identical* representatives under both rules.

## Constructive proof with two entirely synthetic 100-m grids

Take the same three-cell row \(C=\{(0,0),(0,1),(0,2)\}\) (the largest Moore-8 component) in each of two **invented** one-patch geometries. Add exactly one isolated retained cell:

| Fabricated geometry | Isolated fourth cell | Topology representative | Geometry representative | Representatives differ? |
|---|---|---|---|---|
| A | \((4,1)\) | \((0,1)\) | \((0,1)\) | No; \(q=0\) |
| B | \((4,4)\) | \((0,1)\) | \((0,2)\) | Yes; \(q=1\) |

Both meet the original 1-km maximum diameter of a 100-m grid (their maximum inter-cell distances are smaller than 600 m), are internally disconnected under Moore-8 adjacency, and have **identical** retained-cell count 4, patch count 1, disconnected-patch count 1, two within-patch components (sizes 3 and 1), global component count 2, and maximum components per patch 2. Their topology medoids agree because the three-cell connected fragment does not change, but their all-member squared-distance medoids differ.

The pair gives a counterexample to the proposition that the published component counts *uniquely determine* the proportion of sites on which the two rules disagree. The synthetic examples have no species, DEM, occurrence, access or habitat interpretation. They do not assert that either geometry is present in any of the historical Cirsium units.

## Exactly what can and cannot be bounded from existing public aggregates

For an all-patches comparison, let \(P\) denote all original patches, \(D\) their internally disconnected subset and \(q_{\mathrm{all}}\) the fraction for which the two frozen site rules select different cells. Every **connected** patch necessarily gives the same representative cell under both rules. Thus:

\[
0\le q_{\mathrm{all}}\le D/P.
\]

This is an upper bound, **not** an estimated effect or a positive lower bound. With the already frozen original development-stage summaries, the non-causal upper envelopes are:

| Original method-development configuration | \(D/P\), at most differing site choices if all patches sampled |
|---|---:|
| CIR02 wetland | \(320/573=55.85\%\) |
| CIR06 alpine | \(3292/3883=84.78\%\) |
| CIR12 grassland | \(278/654=42.51\%\) |
| CIR13 grassland | \(278/654=42.51\%\) |

The proposed separate trial from PR #274 **deliberately restricts the eligible frame to disconnected patches**. For that restricted frame, existing public aggregate data allow only the vacuous interval \(0\le q_{\mathrm{disconnected}}\le1\), *provided such patches exist*. Its actual \(q\) is **unobserved**, not zero. The values 55.85%, 84.78%, and 42.51% are **not** predictions of disagreement in the restricted trial.

PR #277 already derived \(|\tau|\le q\) for the **mean expected binary site-choice-only difference** under matched observer/search/phenology conditions and equal expected response when both strategies choose the same cell. Combined with the preceding all-patch bound, \(|\tau_{\mathrm{all}}|\le D/P\) is only a conservative *theoretical envelope under those assumptions*. Neither inequality bounds noisy realized treatment-arm differences, removes selection and non-evaluation biases, or establishes a biological response.

## Data needed for the next actual gate

The information **missing** from the public topology receipts is the exact, source-authenticated retained cell membership of each original patch in a **new independently frozen cohort**, which must remain private. With those authenticated sets, the already implemented PR #274 algorithm can privately calculate the two counterfactual representative IDs, report only the **aggregate shared-site count** and \(q\) before field outcomes, and then pre-freeze a balanced assignment and person-minute schedule **after** permissions/field eligibility are assessed. The original public screen had **zero** verified independent, field-ready taxon/sector pairs; neither these synthetic masks nor the old four development units can cure that missingness.

No new species is selected, no per-cell ID, exact locality, original DEM, movement/access layer or field outcome is opened, no 100-m support membership is reclassified, and no upgrade of PR #250's full structural-order gate is implied. In particular, disconnected *model support* does not mean disconnected or unoccupied actual habitat.

## Reproduction

`research/prove_cirsium_site_choice_nonidentifiability.py` validates original Git blobs for the unchanged site-rule implementation (PR #274), frozen prospective method-design contract (PR #274), and frozen four-unit aggregate topology result (PR #273). Its two synthetic examples **call the actual existing site-choice function**. It emits a public-only JSON with synthetic graph signatures, 0-vs-1 representative disagreement and aggregate envelopes without any private cell IDs. `tests/test_cirsium_site_choice_identifiability_v1.py` and `.github/workflows/cirsium-site-choice-aggregate-identifiability.yml` require the source SHA guards and exact saved-result reproduction. The four original configurations are method-development-exposed and not four independent biological confirmations.
