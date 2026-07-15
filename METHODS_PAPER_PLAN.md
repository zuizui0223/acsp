# ACSP methods-paper plan

## Working title

**From occurrence records to field decisions: complementary environmental-analogue prioritization of biodiversity survey zones**

Alternative: **Beyond habitat-suitability maps: a validated framework for converting presence-only records into field-ready survey priorities**

## Central claim

ACSP is not proposed as a wholly new species-distribution model (SDM), and the manuscript should not imply that every production evidence component has been independently validated. The supported methodological object is the **occurrence-conditioned local-environment analogue and complementary set-selection core**.

Given a fixed survey budget, that core:

1. rebuilds environmental candidate evidence from training occurrences only;
2. removes known-location candidates and direct occurrence-distance/density evidence during validation;
3. ranks environmental analogues rather than fitting a required presence/background SDM;
4. optionally adds geographic complementarity so the selected sites form a non-redundant set; and
5. returns a finite set of regional survey zones rather than a continuous suitability map.

The bounded claim is:

> Given a taxon name and occurrence records, the ACSP local-analogue set-selection core prioritizes a fixed number of regional survey zones that recover independent held-out occurrences more often than same-pool random selection at the supported 10 km regional scale. The production application may add optional SDM, access, logistics, and field-feedback evidence, but those additions are not the basis of the current retrospective claim.

## What the implementation already does

No new OASL-style learner is required for this paper. The existing national benchmark already isolates the non-SDM environmental-learning pathway:

- every spatial fold rebuilds candidates from training occurrences only;
- candidate generation uses local terrain/environment analogues learned from those occurrences;
- known-location candidates are removed;
- occurrence support, survey-gap distance, environmental novelty, and distance-to-known components are removed from the validation ranking;
- plants are selected using `component_local_habitat_score` with evidence weight `1.0`;
- animals use the same local-habitat score with evidence weight `0.75`, leaving `0.25` for geographic complementarity;
- each Top-5 result is compared with random Top-5 draws from the identical fold-specific candidate pool.

Therefore, the validated core is narrower than the full production `integrated_support_score`. Optional macro-SDM support, access, logistics, and field-validation weights must be presented as product extensions unless separately validated.

The environmental analogue score is still niche-related. The defensible distinction from a conventional SDM is not that ACSP never uses environmental association; it is that the validated estimand and output are different: **which finite, non-redundant candidate set should be surveyed under a budget**, rather than the value of a continuous suitability surface at every cell.

## Literature gap

SDM methodology is mature for estimating relative suitability, choosing background or pseudo-absence data, reducing sampling bias, selecting algorithms, and evaluating spatial transferability. These approaches generally optimize or compare a **continuous prediction surface**. Field teams face a downstream decision: which small set of places should be visited next under a limited budget, across disconnected areas, without confusing known-record support with genuinely exploratory predictions?

Previous work shows that niche models can guide rare-species surveys and that adaptive monitoring can allocate effort efficiently. The remaining integration gap is a reproducible workflow that simultaneously:

1. starts from opportunistic occurrence records;
2. creates a finite, auditable candidate pool;
3. distinguishes known anchors, environmental analogues, survey gaps, contrasts, and optional model-led candidates;
4. selects a complementary **set**, rather than independently taking the highest cells;
5. respects a fixed candidate budget and geographic-area quotas;
6. carries recommendations into field-ready exports; and
7. evaluates the final decision using same-pool random baselines and prospective field observations.

ACSP is positioned in this gap. Its novelty is the occurrence-to-candidate-set-to-validation chain, not a claim to have invented environmental niche estimation.

## ACSP versus a conventional SDM

| Question | Conventional SDM | Validated ACSP core |
|---|---|---|
| Primary output | Continuous suitability or occurrence-probability surface | Finite ranked set of regional survey candidates |
| Main objective | Predict spatial distribution or environmental association | Improve Top-k regional recovery under a fixed candidate budget |
| Selection unit | Grid cells scored mainly independently | Candidate set selected for evidence and, where configured, complementarity |
| Required response design | Commonly presence/background, presence/absence, or point-process formulation | Presence records define environmental analogue evidence; no SDM probability is required |
| Known occurrences | Training response | Training source, but known-location candidates and direct distance evidence are excluded in recovery validation |
| SDM role | Core model output | Optional production evidence; not used for the supported local-analogue benchmark ranking |
| Spatial redundancy | Usually treated in sampling or cross-validation | Explicitly addressed in final candidate-set selection |
| Logistics | Usually external/post hoc | Added downstream as a separate operational layer |
| Validation | AUC, TSS, Boyce, calibration | Top-k held-out recovery and lift over same-pool random selection |
| Interpretation | Suitability is not necessarily occupancy | Representative point is a regional search anchor, not an exact occupied site |

The manuscript should not claim that ACSP replaces SDMs. The stronger argument is that environmental models and occurrence-derived analogues are **inputs to a downstream set-selection problem**, and predictive discrimination alone does not specify the best finite, non-redundant set of sites to visit.

## Novel contributions

1. **Candidate-set prediction rather than map prediction.** The operative output is a fixed-size set of survey candidates.
2. **Occurrence-conditioned environmental analogues.** Candidate evidence is rebuilt from training occurrences without requiring an SDM classifier.
3. **Leakage-controlled recovery validation.** Known anchors and direct occurrence-distance/density evidence are removed before held-out assessment.
4. **Complementary set selection.** Geographic redundancy can be penalized during final selection instead of only during model fitting.
5. **Same-pool random counterfactual.** Random controls use exactly the same generated candidate pool and budget.
6. **Hierarchical validation.** General unseen-taxon retrospective testing is combined with a frozen prospective field case.
7. **Explicit precision floor.** Grid resolution, environmental resolution, and coordinate uncertainty constrain the scale of defensible claims.

## Study 1: general retrospective benchmark

Use the current frozen national hierarchical benchmark.

- unit: taxon-region pair;
- partition: complete 0.1-degree spatial blocks;
- candidate reconstruction: training records only;
- leakage control: remove held-out known-location candidates and occurrence/distance-derived score components;
- budget: fixed Top-5;
- primary endpoint: held-out observation-unit recovery within 10 km;
- baseline: 200 random Top-5 draws from the identical fold-specific candidate pool;
- secondary comparison: greedy same-pool oracle;
- inference: intention-to-evaluate failures as zero, taxon-region clustered bootstrap intervals, and pair-level sign-flip/randomization tests.

This estimates general candidate-ranking robustness, not occupancy, field detectability, or exact-site accuracy.

### Existing independent results

- Independent animal cohort: 12 declared taxon-region pairs, Top-5 recall `0.0981` versus random `0.0572`; lift `0.0408`, pair-bootstrap 95% CI approximately `0.0031–0.0847`.
- Pooled independent plant cohorts: 36 declared taxon-region pairs, recall `0.1098` versus random `0.0912`; lift `0.0186`, 95% CI approximately `0.0035–0.0374`.
- The 5 km plant effect did not remain stable and must stay outside the supported claim.

### Repeated stability audit

`audit_random_validation_stability.py` reuses the frozen independent fold results and does **not** regenerate candidates after inspecting outcomes. For each group it performs, under five random seeds:

- 10,000 pair-level bootstrap resamples;
- 10,000 random half-cohort samples;
- leave-one-pair-out analysis; and
- 10,000 pair-level sign-flip draws.

Results:

| Group | Mean lift | Leave-one-pair-out minimum | Minimum bootstrap P(lift > 0) across seeds | Minimum half-cohort P(lift > 0) | Maximum sign-flip p across seeds | Verdict |
|---|---:|---:|---:|---:|---:|---|
| Animals, independent mixed cohort | 0.0408 | 0.0258 | 0.9858 | 0.9772 | 0.0853 | Stable positive direction; limited to 12 pairs |
| Plants, pooled independent cohorts | 0.0186 | 0.0120 | 0.9942 | 0.9913 | 0.0271 | Stable |

Every leave-one-pair-out estimate remained positive for both groups. These resampling checks show that the published direction is not produced by one taxon or one inference seed. They are a stability audit of frozen independent cohorts, not a substitute for drawing a further independent GBIF cohort.

## Study 2: prospective *Campanula microdonta* case

The field data contain 28 positive GPS rows across Oshima, Toshima, Niijima, Shikinejima, and Kozushima. One Oshima longitude was corrected by the data owner from `135.349870` to `139.349870`. Duplicate and nearby GPS rows must be clustered before analysis to avoid pseudoreplication.

Required immutable input:

- exact pre-survey candidate-pool export;
- recommendation flag/rank and candidate roles;
- algorithm commit/release and generation timestamp;
- all planned visits, including non-detections and not-surveyable sites, when available.

Primary positive-only endpoint:

- proportion of independent field-detection clusters within 10 km of the frozen ACSP set.

Primary comparison:

- same-pool random sets with the same total budget and same island/area allocation.

Sensitivity radii are 0.5, 1, 2, and 5 km. The 10 km endpoint remains primary because it is the independently supported regional scale.

When complete visit logs are available, analyze detection rate, time to first detection, abundance or populations per search-hour, access failure, and success by candidate role. Positive-only recovery must not be called detection probability.

## Why the two validation layers belong together

The retrospective benchmark asks whether the environmental-analogue set-selection core generalizes across taxa without field logistics or false-absence inference. The *C. microdonta* study asks whether the recommendation object remains useful when carried into a real expedition.

- retrospective breadth prevents overinterpreting one case;
- prospective field evidence prevents treating withheld GBIF records as equivalent to real survey success.

They are complementary validation layers and should not be pooled into one undifferentiated effect size.

## Prespecified rules

1. Freeze candidate pool and algorithm version before reading field outcomes.
2. Preserve failed generation and inaccessible sites in the relevant denominator.
3. Cluster positive GPS rows within a declared radius; use 500 m as the main local-population rule and report 1 and 2 km alternatives.
4. Hold candidate budget and per-island allocation fixed in random baselines.
5. Use detection-cluster recall for positive-only data; do not call it occupancy or detection probability.
6. Analyze standardized negative visits separately when effort data exist.
7. Report 10 km first; fine-scale radii cannot replace it post hoc.
8. Separate known-location recovery from exploratory discovery.
9. Report absolute performance, random baseline, lift, uncertainty, and oracle ceiling.
10. Do not refit production weights on the prospective case before reporting frozen-algorithm performance.
11. Do not describe optional production evidence as retrospectively validated unless it appears in the frozen benchmark selection rule.

## Proposed figures

1. occurrence records → occurrence-conditioned environmental analogues → complementary Top-k set → field zones → outcomes;
2. continuous suitability-map workflow versus finite ACSP candidate-set workflow;
3. blocked retrospective holdout and identical-pool random counterfactual;
4. independent retrospective recall/lift at 2, 5, and 10 km;
5. leave-one-pair-out and half-cohort stability of the 10 km lift;
6. frozen *C. microdonta* candidates and clustered field detections;
7. ACSP recovery against same-island random-set distributions.

## Claims table

| Claim | Status |
|---|---|
| ACSP converts occurrence-conditioned environmental evidence into a finite, auditable field decision | Method/software contribution |
| The local-analogue set-selection core exceeds same-pool random selection at 10 km across independent animal and plant cohorts | Supported and resampling-stable |
| The complete production integrated score, including access, SDM, logistics, and field-feedback weights, is validated as one unit | Unsupported |
| Representative coordinates are exact occupied sites | Unsupported |
| Five-kilometre superiority generalizes across plants | Not supported |
| Frozen *C. microdonta* recommendations recover positive field clusters | To be estimated from the original frozen export |
| ACSP increases detection probability or discoveries per day | Requires standardized negative/control visits and effort |
| Access/travel diagnostics are ecologically validated | Unsupported |

## Reference anchors

- Guisan A, Thuiller W. 2005. Predicting species distribution: offering more than simple habitat models. *Ecology Letters* 8:993–1009. https://doi.org/10.1111/j.1461-0248.2005.00792.x
- Guisan A et al. 2006. Using niche-based models to improve the sampling of rare species. *Conservation Biology* 20:501–511. https://doi.org/10.1111/j.1523-1739.2006.00354.x
- Elith J et al. 2006. Novel methods improve prediction of species' distributions from occurrence data. *Ecography* 29:129–151. https://doi.org/10.1111/j.2006.0906-7590.04596.x
- Phillips SJ, Anderson RP, Schapire RE. 2006. Maximum entropy modeling of species geographic distributions. *Ecological Modelling* 190:231–259. https://doi.org/10.1016/j.ecolmodel.2005.03.026
- Araújo MB, Guisan A. 2006. Five (or so) challenges for species distribution modelling. *Journal of Biogeography* 33:1677–1688. https://doi.org/10.1111/j.1365-2699.2006.01584.x
- Fourcade Y et al. 2014. Mapping species distributions with MAXENT using a geographically biased sample of presence data. *PLoS ONE* 9:e97122. https://doi.org/10.1371/journal.pone.0097122
- Fithian W et al. 2015. Bias correction in species distribution models: pooling survey and collection data for multiple species. *Methods in Ecology and Evolution* 6:424–438. https://doi.org/10.1111/2041-210X.12242
- Valavi R et al. 2019. blockCV. *Methods in Ecology and Evolution* 10:225–232. https://doi.org/10.1111/2041-210X.13107

## Immediate dependency

The prospective analysis must use the original pre-survey export at:

`field_validation/campanula_microdonta/frozen_candidate_pool.csv`

Until it is recovered, this work locks the validated core, positive observations, analysis contract, and stability audit—not the prospective result.
