# ACSP methods-paper plan

## Working title

**From occurrence records to field decisions: adaptive and complementary prioritization of biodiversity survey zones**

Alternative: **Beyond habitat-suitability maps: a validated framework for converting presence-only records into field-ready survey priorities**

## Central claim

ACSP is not proposed as another species-distribution model (SDM). It is a **decision layer between occurrence/model evidence and field deployment**. Given a fixed survey budget, it converts heterogeneous evidence into a ranked, spatially complementary set of regional survey zones, preserves evidence provenance, and exports a field-validation design.

The bounded claim is:

> Given a taxon name and occurrence records, ACSP prioritizes a fixed number of regional survey zones that recover independent held-out or prospectively detected occurrences more often than same-pool random selection, while explicitly separating ecological support from access, detectability, and exact-site claims.

## Literature gap

SDM methodology is mature for estimating relative suitability, choosing background or pseudo-absence data, reducing sampling bias, selecting algorithms, and evaluating spatial transferability. These approaches generally optimize or compare a **continuous prediction surface**. Field teams face a different decision: which small set of places should be visited next under a limited budget, across disconnected areas, without confusing known-record support with genuinely exploratory predictions?

Previous work shows that niche models can guide rare-species surveys and that adaptive monitoring can allocate effort efficiently. The remaining integration gap is a reproducible workflow that simultaneously:

1. starts from opportunistic occurrence records;
2. creates a finite, auditable candidate pool;
3. separates occurrence-supported, local-analogue, survey-gap, environmental-contrast, and model-only candidates;
4. selects a complementary **set**, rather than independently ranking cells;
5. respects a fixed candidate budget and geographic-area quotas;
6. carries recommendations into field-ready exports; and
7. evaluates the final decision using same-pool random baselines and prospective field observations.

ACSP is positioned in this gap. Its novelty is the occurrence-to-decision-to-validation chain, not a new ecological niche estimator.

## ACSP versus a conventional SDM

| Question | Conventional SDM | ACSP |
|---|---|---|
| Primary output | Continuous suitability or occurrence-probability surface | Finite ranked set of survey zones and member points |
| Main objective | Predict spatial pattern or environmental association | Maximize survey value under a fixed field budget |
| Selection unit | Grid cells evaluated mainly independently | Candidate set selected jointly for evidence and complementarity |
| Known occurrences | Training response | Transparent evidence family; known anchors remain labelled |
| SDM role | Core output | Optional macro evidence and source of labelled exploratory candidates |
| Missing SDM evidence | Often prevents prediction | Treated as unavailable; available evidence is renormalized |
| Spatial redundancy | Mostly handled in training/CV | Penalized in the final survey-set decision |
| Logistics | Usually external/post hoc | Area quotas, zone aggregation, trip diagnostics and exports |
| Validation | AUC, TSS, Boyce, calibration | Top-k recovery, lift over same-pool random, distance to new detections, discoveries per effort |
| Interpretation | Suitability is not necessarily occupancy | Representative coordinate is a regional search anchor, not an exact occupied site |

The manuscript should not claim that ACSP replaces SDMs. The stronger argument is that SDMs are **inputs to a downstream decision problem**, and high predictive discrimination does not specify the best non-redundant and feasible set of sites to visit.

## Novel contributions

1. **Candidate-set prediction rather than map prediction.** The estimand is the marginal value of adding a candidate to an already selected set under a fixed budget.
2. **Adaptive available-evidence scoring.** Missing model evidence is not silently converted into unsuitability.
3. **Exploration/exploitation separation.** Known anchors, habitat analogues, survey gaps, contrasts, and model-only sites retain distinct interpretations.
4. **Geographic complementarity.** The final set avoids spending a limited budget on nearly equivalent locations.
5. **Hierarchical validation.** General unseen-taxon retrospective testing is combined with a frozen prospective field case.
6. **Explicit precision floor.** Grid resolution, environmental resolution, and coordinate uncertainty constrain the scale of defensible claims.

## Study 1: general retrospective benchmark

Use the current frozen national hierarchical benchmark.

- unit: taxon-region pair;
- partition: complete spatial blocks;
- candidate reconstruction: training records only;
- leakage control: remove held-out known-location candidates and occurrence/distance-derived score components;
- budget: fixed Top-k;
- primary endpoint: held-out observation-unit recovery within 10 km;
- baseline: random Top-k from the identical candidate pool;
- secondary baselines: local-only, macro-only, occurrence-only where valid, and greedy same-pool oracle;
- inference: intention-to-evaluate failures as zero, taxon-region clustered bootstrap intervals, and pair-level sign-flip/randomization tests.

This estimates general ranking robustness, not field detectability.

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

The retrospective benchmark asks whether ACSP generalizes across taxa without field logistics or false-absence inference. The *C. microdonta* study asks whether the recommendation object remains useful when carried into a real expedition.

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
10. Do not refit production weights on this case before reporting frozen-model performance.

## Proposed figures

1. occurrence records → candidate evidence → complementary set → zones/routes → field outcomes;
2. suitability surface versus finite ACSP recommendation under the same budget;
3. blocked retrospective holdout and same-pool baselines;
4. retrospective recall/lift at 2, 5, and 10 km;
5. frozen *C. microdonta* candidates and clustered field detections;
6. ACSP recall against same-island random-set distributions;
7. default, local-only, macro-only, random, and oracle comparison.

## Claims table

| Claim | Status |
|---|---|
| ACSP converts occurrence evidence into a finite, auditable field decision | Method/software contribution |
| Regional 10 km Top-k prioritization exceeds same-pool random selection across independent cohorts | Supported by current retrospective benchmark |
| Representative coordinates are exact occupied sites | Unsupported |
| Five-kilometre superiority generalizes across plants | Not currently supported |
| Frozen *C. microdonta* recommendations recover positive field clusters | To be estimated from the frozen export |
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

Until it is recovered, this work locks the method, positive observations, and analysis contract—not the prospective result.