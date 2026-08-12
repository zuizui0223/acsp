# ACSP and EOG: joint program strategy

This document fixes the intended relationship between `zuizui0223/acsp` and `zuizui0223/eog`,
the division of scientific labour between them, and the order in which the remaining work
should be done.

It is a planning and guardrail document. It does not create new claims, and every number
quoted below is already frozen in one of the two repositories.

This file is mirrored as `docs/eog_acsp_program_strategy.md` in the EOG repository. The two
copies must be kept in sync; if they drift, this copy is canonical because ACSP is the parent
project from which the EOG geometry layer was extracted.

## 1. Verified current state

### 1.1 ACSP

- **Object:** a finite survey decision. Given occurrence records, a generated candidate pool
  `C`, declared evidence `E` and a budget `B`, ACSP returns `S ⊆ C, |S| ≤ B`.
- **Delivery:** Streamlit application, `acsp-survey` Python distribution, early `r-acsp`
  package, GBIF ingestion, CSV upload, map-first UI, field-validation exports.
- **Frozen positive evidence:** same-pool random counterfactuals at 10 km.
  Animals 12 pairs, recall `0.0981` vs random `0.0572`, lift `0.0408`
  (95% CI `0.0031`–`0.0847`). Plants 36 pairs, recall `0.1098` vs random `0.0912`,
  lift `0.0186` (95% CI `0.0035`–`0.0374`, sign-flip `p = 0.0233`).
- **Frozen negative / bounding evidence:** 5 km plant recovery is unstable and is not an
  exact-site claim (`FINE_SCALE_LIMITS_REPORT.md`). The unstratified global Top-5 failed the
  first external *Campanula microdonta* field evaluation (10 km lift `0`), which motivated the
  post-baseline area-balancing rule.
- **Frozen decision contrast:** against a production-aligned fitted SDM on identical folds,
  pools, budgets and endpoints, all-declared recovery was essentially identical
  (ACSP − SDM = `−0.0003`, 95% `−0.0385`–`0.0367`), but the *decisions* differed: mean Top-5
  Jaccard `0.264` across 101 SDM-evaluable folds, exact set agreement once.
- **Current core:** the Practical Core is deliberately parsimonious — rank the training-only
  pool by `component_local_habitat_score`, drop known-location rows, take Top-5. Three more
  complex development variants (utility+Ridge router, taxon-group calibrated blend, added set
  complementarity) all failed the predeclared improvement target.
- **Open critical item:** the 192-pair untouched confirmation against `spsurvey::grts()` and
  native `biosurvey` is **frozen but not executed**. `cohort_manifest.json` reports
  `outcomes_inspected: false` and every execution flag `false`.

### 1.2 EOG

- **Object:** the *incremental information* carried by occurrence-anchored landscape
  configuration, conditional on what a reference model already contains.
- **Delivery:** Python library plus `eog-hypothesis-survey` CLI. No application.
- **Frozen positive evidence:** A-Islands, 886 plant taxa across 842 islands, 845 estimable.
  Conditional reachability concordance `0.6177466`, species-bootstrap 95%
  `0.6086806`–`0.6269445`, sign-flip ≈ `1 × 10⁻⁵`, after matching pointwise CHELSA support and
  nearest-training-occurrence distance.
- **Frozen negative evidence:** Tanzania, 60 bird species across 14 fragments. Against a
  reference already containing patch area, a training-selected matrix-aware current flow, their
  interaction and nearest-occurrence distance, adding EOG connected frequency **worsened**
  leave-one-fragment-out log loss by `+0.0321131` (95% `+0.0174580`–`+0.0486750`,
  `p = 0.000030`).
- **Status:** the structural manuscript, figures, result tables and submission package are
  built. The remaining gates in `manuscript/submission/release_readiness.md` are
  administrative — author list, affiliations, contributions, funding, competing interests,
  AI disclosure, live journal policy, figure format — not scientific.

## 2. What actually differs

| Axis | ACSP | EOG |
|---|---|---|
| Estimand | selected finite set `S` under budget `B` | incremental held-out information of a structural feature, given a reference |
| Primary input | occurrence records | a **frozen** pointwise support field + training occurrences |
| Primary output | ranked, exportable, visitable survey zones | component classes, connected frequency, bottleneck, bridge hypotheses |
| Unit of evaluation | taxon–region pair, fixed budget, same-pool random control | species, spatial/LOSO fold, reference-vs-candidate paired loss |
| Spatial resolution of the supported claim | 10 km regional zones | landscape graph topology; no site-level claim |
| Empirical geography | Japan (GSI terrain, GBIF) | Australian islands, Tanzanian forest fragments |
| Kind of novelty | operational — map → finite auditable decision | epistemic — separating estimands and publishing the boundary where the method fails |
| Maturity | product exists; decisive external comparison unrun | evidence complete; product does not exist |

The one-line version:

> **ACSP is a decision layer with a weak algorithm and strong practicality.
> EOG is a strong methodological result with no delivery surface.**

Their weaknesses are almost exactly complementary, which is why the temptation to merge them
is strong and why it must be resisted in the specific form described in §4.

## 3. The real collision risk

EOG already contains a survey-ranking layer (`run_hypothesis_survey_pipeline`,
`discrimination_score`). ACSP is a survey-ranking tool. On the surface these look like
duplicated work. They are not, and the distinction must be stated explicitly in both
repositories rather than left implicit:

- **ACSP ranks for yield.** Where should a team go to maximise the chance of recovering the
  taxon under a fixed budget? The endpoint is held-out recovery.
- **EOG ranks for discrimination.** Where should a team go so that competing predeclared
  reachability hypotheses disagree most sharply? The endpoint is hypothesis separation, and
  the documentation already forbids reading it as occurrence probability or expected
  information gain.

These are different survey objectives — *finding* versus *experimental design*. Allowing them
to converge would destroy the clearest structural difference between the two projects. Neither
score should be renamed, blended, or presented as a variant of the other.

## 4. The one integration that is allowed, and the one that is not

### 4.1 Not allowed (for now)

Do **not** add an EOG structural feature as another weighted evidence channel inside the ACSP
candidate score. Both repositories have independently produced evidence against exactly that
move:

- Tanzania shows that adding a generic occurrence-anchored structural feature to a reference
  that already contains local support and source distance can measurably *hurt*;
- ACSP development shows that three separate attempts to add complexity on top of local-only
  ranking all failed their predeclared improvement targets.

Doing it anyway would also contaminate the frozen 192-pair cohort, which is currently the most
valuable unspent asset either project owns.

### 4.2 Allowed

Couple them at the **pool level**, not the score level, and only under a separate frozen
protocol:

```text
frozen pointwise support + training occurrences
    -> EOG support topology / connected frequency
    -> declared candidate-pool partition (anchored / detached / low-reachability)
    -> ACSP finite-set selection *within* the declared partition
    -> field validation
```

This preserves both estimands intact. EOG never emits a suitability number into ACSP's weight
vector; it emits a *stratification of the candidate pool*, which ACSP already treats as a
first-class object (declared survey areas, per-area quotas, area balancing). ACSP's existing
area-allocation machinery is the natural consumer, and the change is testable as a pool
definition rather than as a weight change — meaning it can be evaluated against the same
same-pool random controls without redefining the endpoint.

## 5. Where the joint novelty actually is

Neither repository can claim this alone, and it is the strongest available framing:

> Prediction-level equivalence does not imply decision-level equivalence.

Both projects have already established one half of this independently and with frozen numbers:

- **EOG (Tanzania):** a structural feature can be *predictively* useless or harmful against a
  strong reference.
- **ACSP (SDM contrast):** two methods with statistically indistinguishable recovery
  (`−0.0003`) nevertheless select almost disjoint field sets (Jaccard `0.264`, exact agreement
  once in 101 folds).

Put together, the open and genuinely novel question is:

> Does landscape configuration change *which finite set should be surveyed*, even in systems
> where it does not improve pointwise prediction?

This is worth stating plainly: the Tanzania negative result is an **asset**, not a liability,
for that question. A structural layer that had simply improved prediction everywhere would
make the decision-level question uninteresting. Because EOG's incremental prediction claim is
explicitly bounded, a decision-level effect — if it exists — is a separate and non-redundant
contribution rather than a restatement of the predictive one.

That question must not be answered by inspection of existing results. It requires a third
predeclared protocol, frozen before outcomes, with a decision endpoint (selected-set recovery
under a fixed budget, plus outcome-free set-overlap diagnostics) rather than a loss endpoint.

## 6. Sequencing

The order matters more than the content, because the cheapest asset to destroy is
independence.

**Step 1 — EOG: close out, do not develop.**
The science is frozen and the manuscript is built. The remaining gates are administrative.
Fix author metadata, reserve the Zenodo DOI, tag `v0.1.0`, submit. Any new EOG modelling work
started before submission delays a finished result for an unfinished one.

**Step 2 — ACSP: execute the 192-pair untouched confirmation.**
This is the single highest-value action across both repositories. Until it runs, ACSP cannot
say anything about GRTS or biosurvey, and the claim boundary in `docs/ACSP_PRACTICAL_CORE.md`
holds. Freeze feature development on the ecological ranking pathway until it has run; any
change to that pathway before execution burns 192 untouched taxa that cannot be regenerated.

**Step 3 — ACSP: report whichever way it goes.**
Both outcomes are publishable, and the plan must be written so that neither one triggers
retrofitting:
- *Practical Core ≥ GRTS/biosurvey* → the decision-layer claim is supported and the methods
  paper strengthens to a comparative claim.
- *Practical Core < GRTS/biosurvey* → ACSP is reported as an auditable, deployable
  occurrence-to-decision workflow that does **not** beat established survey design, exactly as
  `docs/ACSP_PRACTICAL_CORE.md` already commits to. That is still a usable paper, and the
  honesty is consistent with how EOG handled Tanzania.

**Step 4 — joint decision-level protocol.**
Only after Steps 1–3. Freeze it before touching outcomes. Suitable systems are multi-area
archipelago or fragmented-landscape designs where both a structural partition and a finite
budget are meaningful — which is also the system type EOG's own synthesis names as the next
strongest evidence.

**Step 5 — productisation.**
ACSP is the only delivery surface either project has. EOG should ship as a library that ACSP
optionally consumes and should not grow its own application. Practicality is maximised by
adding one consumer, not one more interface.

## 7. Guardrails

1. Do not merge the repositories. Two estimands, two claim boundaries, two paper scopes.
2. Do not blend `discrimination_score` and ACSP candidate scores, or rename either toward the
   other.
3. Do not add EOG features to the ACSP evidence weight vector before Step 2 completes.
4. Do not reopen the Tanzania benchmark. Any extension must be motivated independently,
   frozen before its own outcomes, compared against the same or stronger reference, and
   reported *alongside* the frozen negative result.
5. Do not present a post-hoc coupling of the two projects as confirmation of either.
6. Preserve unfavourable results in both repositories at their original strength. The
   *C. microdonta* baseline failure and the Tanzania adverse increment are load-bearing for the
   credibility of everything else.
7. Keep this file in sync with its EOG mirror.

## 8. What would change this plan

| Observation | Consequence |
|---|---|
| 192-pair confirmation favours GRTS or biosurvey | ACSP's contribution narrows to workflow/auditability; the joint decision-level study becomes *more* important, not less, because the algorithm claim is gone |
| 192-pair confirmation favours the Practical Core | Comparative claim opens; Step 4 gains a stronger ACSP side |
| EOG manuscript is rejected on scope rather than method | Reframe around the decision-level question of §5 rather than adding new benchmarks |
| A multi-area field season with complete visit logs becomes available | Promote Step 4 ahead of Step 5; it is the only design that can test access, detection and effort, all of which are currently unvalidated in ACSP |
