# ACSP v2 practical-development contract

## Status

ACSP v1 remains the frozen, publication-facing regional finite-decision baseline. Nothing in this document strengthens or rewrites the validated v1 claim.

ACSP v2 is an **experimental practical-improvement track**. Its purpose is to improve the final finite survey decision, not to create another species-distribution model and not to maximize novelty for its own sake.

The current v2 candidate-utility policy is development-frozen but **not independently validated**.

## Why v2 exists

The existing evidence shows that ACSP v1 provides real regional selection information relative to same-pool random choice, but it also shows that the fixed policy is not uniformly optimal:

- focal-taxon local-habitat evidence explains much of the observed retrospective selection signal;
- the fixed 25% geographic-complementarity term for animals has not shown a resolved incremental benefit over local-only ranking;
- generic environmental and geographic coverage methods can be competitive in some taxon-region pairs;
- fitted-SDM Top-5 ranking has similar mean regional recovery while usually selecting a different set.

Therefore v2 does not add more fixed evidence weights. It asks whether the **candidate-pool context itself can identify which candidates are likely to contribute to a fixed survey set**, using only patterns learned from other taxon-region pairs.

## Decision target

For one candidate pool `C` and a declared budget `B=5`, v2 returns a set

\[
S_{v2} \subseteq C, \qquad |S_{v2}| \le 5.
\]

The learned candidate score is trained against a development label indicating whether a candidate covers at least one spatially held-out occurrence within the 10-km regional endpoint.

This score is called **candidate decision utility**. It is not interpreted as:

- occupancy probability;
- habitat suitability;
- detectability;
- abundance;
- probability of a new population;
- field efficiency per hour.

Those quantities would require different data and estimands.

## Frozen candidate features

The model intentionally uses a small, auditable set of inference-time quantities.

Candidate-level evidence:

- `component_local_habitat_score`;
- within-pool local-score rank.

Candidate-pool spatial context:

- nearest-neighbour geographic distance;
- mean geographic distance to other candidate rows.

Candidate-pool environmental context:

- nearest-neighbour environmental distance;
- mean environmental distance;
- robust-scaled elevation, slope, roughness and TPI plus sine/cosine aspect.

One development taxon used a marine candidate surface with none of those five terrestrial terrain columns. That state is explicitly supported: `env_nn` and `env_avg` are missing and receive the frozen development-model median at inference. A **partial** five-variable terrain schema is treated as inconsistent and triggers a v1 fallback rather than silently changing the environmental representation.

Pool diagnostics:

- candidate-pool size;
- local-score standard deviation;
- local-score 90th percentile.

Broad context:

- plant versus animal;
- normalized candidate role: habitat, survey-gap, environmental or other.

The inference-time feature set deliberately excludes scientific name, absolute geographic stratum, held-out coordinates, candidate-to-held-out distance, recovery IDs and recovery outcomes.

## Frozen development model

The committed machine-readable artifact is:

`validation/acsp_v2_candidate_utility_protocol.json`

Protocol fingerprint:

`378e069f982a19abfc0183163fd503b467a1b746c11ba0b354d4f9802c155124`

It fixes:

- logistic regression with `C=0.03` and balanced classes;
- preprocessing medians, means and scales;
- one-hot category order;
- fitted all-development coefficients;
- Top-5 budget;
- candidate-utility weight `0.60`;
- short-range geographic representation weight `0.40`;
- representation scale `10 km`;
- eight fixed development outer folds grouped by complete taxon-region pair.

The candidate utility is converted into a set decision using

\[
0.6\,u_i + 0.4\left(1-e^{-d_i/10}\right),
\]

where `u_i` is the learned candidate-decision utility and `d_i` is the nearest distance in kilometres to a candidate already selected into the current set.

This geographic term is deliberately shorter-range than the v1 complementarity scale. Its role is to avoid local duplicate choices without forcing broad geographic dispersion when the learned utility does not support it.

## Development evidence

The development benchmark uses the exact reviewed secondary reconstruction artifacts from 2026-07-24:

- mixed run `30091294481`;
- plant run `30091305081`.

Together they contain 48 unique taxon-region pairs and 240 expected folds. Candidate-utility models are fitted only on other taxon-region pairs in each of eight frozen outer folds.

The reproducible grouped development target is:

| method | mean 10-km pair recall |
|---|---:|
| ACSP v2 candidate utility | 0.15332 |
| frozen ACSP v1 | 0.13181 |
| local evidence Top-5 | 0.13110 |
| geographic maximin | 0.10483 |
| same-pool random | 0.08470 |

The pair-level v2-minus-v1 development difference is `+0.02151`; the 30,000-draw pair bootstrap interval is `0.00330–0.04228`, and the sign-flip p-value is `0.03397`. Of 48 pair differences, 25 are positive, 12 negative and 11 tied.

**These are development estimates, not confirmation.** The regularization and final set-selection weights were selected while these source artifacts were available. The repository must reproduce these results, but must not cite them as evidence that v2 is validated.

## Fallback

When the v2 feature contract cannot be satisfied, `select_practical_v2()` falls back to the frozen taxon-group v1 policy and records the reason. Missing data must never silently produce a different learned model.

The one explicitly supported exception is a candidate pool with none of the five terrestrial terrain columns, matching the marine development case. Such a pool uses the frozen median-imputed environmental-context features rather than inventing terrestrial values.

## Independent confirmation gate

No production promotion and no superiority claim is permitted until a new untouched cohort is sampled and frozen.

The planned confirmation target is about 96 independent taxon-region pairs, with all prior ACSP development, confirmation, comparator, Izu and SDM-benchmark taxa excluded by scientific name.

The final protocol must be committed **before** candidate or held-out outcomes are generated. It will retain:

- Top-5 budget;
- 10-km primary regional endpoint;
- complete spatial-block holdout;
- training-only candidate reconstruction;
- pair-level inference;
- intention-to-evaluate failure retention;
- no taxon replacement after failure.

The primary comparison will be against the strongest predeclared operational baseline, not against random alone. Frozen v1, local-only, geographic/environmental controls, fitted-SDM Top-5 when applicable, and same-pool random remain secondary anchors.

## Established survey-design comparators

The confirmation suite should include actual implementations of established survey-design principles wherever the same finite candidate frame permits fair use. Priority comparator families are:

- GRTS spatially balanced sampling from `spsurvey`;
- GRTS with inclusion probability proportional to focal local evidence as a strong evidence-aware spatial design;
- `biosurvey` geographic-uniform (`uniformG_selection`), environmental-uniform (`uniformE_selection`) and environment-geography (`EG_selection`) principles where their data contract can be matched without changing the candidate universe;
- fitted-SDM Top-5 on the same candidate frame.

An ACSP-like reimplementation of these ideas is not sufficient for the final superiority claim when the original software can be used reproducibly.

## Practicality gate

Retrospective regional recovery is necessary but not sufficient for practical-tool superiority.

Promotion of access, route, replacement and survey-time terms into the validated v2 core requires prospective standardized field records containing, at minimum:

- every attempted site;
- detection and non-detection;
- actual search duration;
- searched area or protocol effort;
- access failure and reason;
- weather / season / phenological state;
- replacement-site use;
- realized travel time.

Until such data exist, the v2 ecological decision policy may improve regional candidate selection, while logistics remain transparent but separately unvalidated software functions.

## Claim guardrail

Before untouched confirmation, the strongest permitted statement is:

> A cross-taxon learned candidate-decision utility is promising in grouped development validation and has been frozen for independent testing.

Do not write:

> ACSP v2 is significantly better than ACSP v1, SDM, GRTS, biosurvey or existing survey-design tools.

That claim must be earned on untouched data under a predeclared equal-budget comparison.
