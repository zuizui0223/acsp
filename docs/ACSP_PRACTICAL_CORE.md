# ACSP Practical Core

## Decision

The practical ACSP core is intentionally simpler than the historical frozen v1 policy.

After additional development, the default finite decision is:

> **rank the training-only candidate pool by focal local-habitat evidence and select the Top-5 after removing known-location candidates.**

The rule is identical for plants and animals. There is no fixed geographic-complementarity term in the practical core.

This is a practical simplification, not a retrospective rewrite of the publication-facing `ValidatedCorePolicy`. The historical v1 remains frozen for reproducibility.

## Why the policy was simplified

The 2026-07-24 standard-baseline reconstruction showed that focal local-habitat evidence carried most of the retrospective recovery signal. For plants, local-only and frozen v1 were identical. For animals, the fixed 25% geographic-complementarity term was not resolved as an incremental benefit.

A later 24-pair cohort that had originally been untouched for the fitted-SDM comparison was used as an intermediate v2 gate. Once those outcomes were inspected, that cohort ceased to be independent confirmation and became development data. In those 24 pairs, local-only exceeded frozen v1 by about 0.0325 mean 10-km recall; the animal-only difference was about 0.0651.

We then tried to improve local-only using the combined 72 development pairs. The following variants all failed the predeclared practical-improvement target under fully nested taxon-region evaluation:

| development variant | mean gain over local-only | 95% pair bootstrap interval | sign-flip p |
|---|---:|---:|---:|
| candidate-utility + Ridge policy router | +0.0059 | -0.0081 to +0.0198 | 0.42 |
| taxon-group calibrated local/utility blend | +0.0065 | -0.0065 to +0.0188 | 0.33 |
| local + geographic/environmental set complementarity | +0.0012 | -0.0006 to +0.0037 | 0.50 |

The learned/router approach helped animals in some folds but did not generalize sufficiently to plants. Added set complementarity was essentially neutral. These negative results are treated as evidence **against** adding complexity to the current default.

## Evidence audit

Within the existing candidate table, ranking by local-habitat evidence was also stronger than ranking by the other production evidence columns. `integrated_support_score`, `survey_gap_score`, `environmental_novelty`, access scores, and evidence-agreement terms all reduced mean 10-km recovery when used as standalone ranking scores in development.

This does not mean those fields are useless operationally. It means they currently lack evidence for promotion into the ecological ranking core. Access and logistics remain useful as feasibility constraints outside the validated ecological ranking.

## Practical-core contract

The machine-readable contract is:

`validation/acsp_practical_core_protocol.json`

Fingerprint:

`3dafe65b6bef09b1878d688730d5feb64a8de58843b06ff9fb14a876512d4905`

The selector:

1. receives a candidate pool already generated from training occurrences only;
2. removes rows labelled as occurrence-supported / known-location / known anchor;
3. ranks by `component_local_habitat_score` descending;
4. breaks ties by stable candidate/site ID;
5. returns at most five rows;
6. does not read scientific name, region identity, held-out coordinates, held-out recovery, SDM predictions, survey-gap scores, access scores, or geographic-complementarity terms.

The local score is interpreted as **occurrence-conditioned local environmental support**, not occupancy probability or calibrated habitat suitability.

## What remains unvalidated

The practical core is development-frozen but not yet validated as superior to established survey-design tools.

The next independent confirmation must use taxa never used in any prior ACSP development or comparison. The same-pool primary comparator is the official `spsurvey::grts()` implementation with proportional inclusion driven by the same local evidence and a requested 10-km minimum distance.

A broad claim of superiority to existing survey-planning software additionally requires an end-to-end comparison against the native `biosurvey` workflow. That comparison must allow each tool to generate its own sites from the same region, environmental information, and field budget.

## Claim boundary

Allowed before untouched confirmation:

> Development favored a parsimonious local-evidence finite-decision rule over more complex ACSP variants, so this rule was frozen for independent comparison against established survey-design methods.

Not allowed before untouched confirmation:

> ACSP Practical Core is significantly better than GRTS, biosurvey, SDM, or existing survey-planning tools.

## Design implication

The development evidence changes the role of ACSP. The main contribution should not be described as a complicated new ecological predictor. The practical contribution is a transparent decision layer that converts occurrence-conditioned local evidence into a finite, auditable field-survey set and exposes stronger established alternatives as explicit comparators.

If the practical core cannot beat those comparators on untouched data, ACSP should remain a useful auditable workflow rather than be claimed as a superior selection algorithm.
