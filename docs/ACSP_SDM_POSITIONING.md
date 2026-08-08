# ACSP and species distribution models: estimand and decision boundary

This document fixes the intended scientific relationship between ACSP and species distribution models (SDMs). It is a design and interpretation guardrail for code, benchmarks, manuscripts, and future extensions.

## Short statement

ACSP is **not intended to replace an SDM or to prove that survey prioritization is universally better than species distribution modeling**.

An SDM and ACSP can use overlapping environmental information while targeting different mathematical objects:

- an SDM estimates a pointwise model quantity over locations;
- ACSP returns a finite set of regional survey decisions under a declared candidate pool and budget.

In production, an SDM can be one optional evidence channel inside ACSP. The relationship is therefore primarily **model-to-decision composition**, not model-versus-model competition.

## 1. SDM estimand

Let `x_i` denote environmental and other predictors at location `i` and let `O` denote occurrence information used for model fitting.

A fitted SDM produces a pointwise score

\[
m_i = f_\theta(x_i; O),
\]

where the interpretation of `m_i` depends on model design and may be relative suitability, occurrence intensity, or an occurrence probability under additional assumptions.

The essential point for ACSP positioning is not that every SDM treats cells as independent; many SDMs can include spatial structure, random effects, interactions, or other dependencies. The relevant distinction is that the primary fitted object remains a **location-indexed model surface or score**.

If a field team subsequently visits the five locations with the largest `m_i`, that Top-5 rule is a downstream decision rule applied to the SDM output.

## 2. ACSP estimand

Let:

- `O` be the available focal-taxon occurrence information;
- `C = {c_1, ..., c_n}` be a generated and auditable candidate pool;
- `E` be the declared evidence available for candidates;
- `B` be the field-survey budget, such as a fixed number of regional search anchors.

ACSP estimates a decision policy

\[
\pi(O, C, E, B) \rightarrow S, \qquad S \subseteq C, \ |S| \le B.
\]

The estimand is therefore the **selected finite set `S`**, not a continuous occurrence surface.

The policy may use candidate-level evidence, but its scientific output is the survey set that should be considered under the declared budget and interpretation boundary.

For policies that include complementarity, the marginal value of candidate `c_i` can depend on which candidates have already been selected. Consequently, a selected set cannot in general be reconstructed by independently thresholding one pointwise score.

## 3. What is actually distinct

The defensible distinction is based on estimand, output, and validation target rather than on a claim that SDMs are simplistic or spatially independent.

| Dimension | SDM | ACSP |
|---|---|---|
| Primary object | Location-indexed model score or surface | Finite survey set under a budget |
| Main question | What does the fitted occurrence-environment model predict at location `i`? | Which feasible candidate set should be surveyed next? |
| Output unit | Cell, point, or continuous surface | Auditable candidate set / regional search anchors |
| Candidate budget | Usually applied after modeling | Part of the declared decision problem |
| Set dependence | Not required by the model estimand | Can be explicit through complementarity or allocation rules |
| SDM use | The model itself | Optional evidence channel within a broader decision policy |
| Validation target | Prediction/discrimination/calibration appropriate to the model | Recovery or utility of the final finite decision under matched budgets |
| Failure meaning | Model may fail to fit or predict | Candidate generation, evidence, or a component model may fail; failures remain explicit in the decision audit |

## 4. Why a direct fitted-SDM Top-k benchmark is still useful

The same-pool benchmark is not designed to answer the universal question "Is ACSP better than SDM?"

Instead it asks:

> If the training information, geographic bounds, candidate pool, and Top-k budget are held constant, do occurrence-conditioned finite-set selection and fitted-SDM suitability ranking produce the same field decision?

The controlled comparison removes several avoidable confounders:

- both methods see the same training fold;
- both methods rank/select from the same candidate locations;
- both receive the same Top-k budget;
- held-out coordinates are attached only after decisions are frozen.

The recovery difference is a **secondary performance contrast**. The primary positioning value of this benchmark is that it makes decision disagreement measurable.

## 5. Descriptive differentiation diagnostics

For SDM-evaluable folds, report the following separately from held-out performance inference:

1. number of shared Top-k candidates;
2. Jaccard overlap of ACSP and fitted-SDM selected sets;
3. exact-set agreement frequency;
4. rank correlation between the declared focal-taxon local-evidence score and fitted-SDM suitability over the common candidate pool;
5. local-evidence profile of ACSP-selected versus SDM-selected candidates;
6. SDM-suitability profile of ACSP-selected versus SDM-selected candidates;
7. geographic dispersion of the selected sets, descriptively;
8. SDM applicability and failure reasons separately from failures of the shared candidate pool.

These quantities describe how the methods make decisions. They are not post-hoc superiority endpoints and should not be converted into a new significance-search exercise.

## 6. Interpretation of possible benchmark outcomes

### ACSP has higher held-out recovery

Permitted interpretation:

> The frozen ACSP policy recovered more held-out occurrences than fitted-SDM Top-k ranking in this same-pool decision benchmark.

Not permitted:

> ACSP is generally better than SDMs.

### Similar recovery

Permitted interpretation:

> The two decision rules achieved similar regional recovery in this cohort; decision-overlap diagnostics determine whether this arose from similar selections or from different selections with similar outcomes.

Not permitted:

> ACSP and SDM are the same method.

### Fitted SDM has higher recovery

Permitted interpretation:

> Fitted suitability ranking had higher recovery in this frozen cohort, while ACSP remains a distinct downstream finite-set framework and may incorporate SDM evidence in production.

Not permitted:

> ACSP has no methodological role because an SDM performed better on this benchmark.

## 7. Production composition

A production ACSP evidence vector can include an SDM-derived component `m_i` alongside occurrence-conditioned local evidence and other declared information:

\[
E_i = (l_i, m_i, g_i, a_i, \ldots).
\]

The presence of `m_i` does not turn ACSP into a second SDM. The distinction is the downstream operation:

\[
\{E_i : c_i \in C\} \rightarrow S.
\]

Conversely, an SDM followed by a sophisticated survey-design optimizer can solve a closely related decision problem. ACSP should therefore claim novelty in its **transparent occurrence-to-candidate-to-finite-decision workflow and validation boundary**, not claim exclusive ownership of survey optimization.

## 8. Manuscript wording guardrail

Preferred framing:

> Species distribution models estimate location-indexed model quantities, whereas field planning requires a finite decision under a survey budget. ACSP is positioned as an auditable occurrence-to-decision layer that can operate without a fitted SDM or incorporate SDM output as one evidence source.

Avoid framing the contribution as:

- a universally superior alternative to SDMs;
- proof that SDM maps are unsuitable for field planning;
- a claim that all SDMs treat cells independently;
- a new occurrence-probability estimator.

## 9. Future method development

Extensions such as persistent environmental patches, environmental-support continuity, route-aware patch selection, or adaptive field feedback should preserve the same boundary:

- environmental or distribution models may provide evidence;
- the novel target remains the structure or finite action required for field survey;
- validation should match that target rather than defaulting to model-surface accuracy metrics.
