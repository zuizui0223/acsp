# From occurrence records to finite field-survey decisions: cross-taxon validation of complementary regional prioritization

## Status

Working manuscript draft restricted to the frozen pre-*Campanula microdonta* validation program. The confirmatory evidence comprises independently sampled taxon–region cohorts evaluated using training-only candidate reconstruction, fixed Top-5 decisions, and random Top-5 counterfactuals from the identical candidate pools. Production-only evidence integration, access, routing, field feedback, and later island-method development are outside this paper.

## Abstract

Biodiversity surveys often begin with incomplete and spatially biased occurrence records, but field teams must ultimately choose a small number of places to visit under a fixed budget. Species distribution models and environmental-association analyses generally return continuous spatial predictions, whereas survey planning requires a finite-set decision. We developed Adaptive Complementarity-based Survey Prioritization (ACSP), an occurrence-to-decision framework that reconstructs regional candidates from training occurrences and selects a fixed-size, non-redundant set of survey zones. We evaluated the frozen ACSP core using repeated spatial-block hold-out across independently sampled taxon–region pairs in Japan. Complete 0.1-degree spatial blocks were withheld, candidate pools were rebuilt from training records only, and candidates or score components directly associated with known occurrence locations were excluded before selection. For every fold, the ACSP Top-5 set was compared with random Top-5 sets drawn from the identical candidate pool. Failed folds and pairs remained in intention-to-evaluate estimates, and inference was conducted at the taxon–region-pair level. Within 10 km, ACSP recovered a mean proportion of 0.0981 of withheld animal observations compared with 0.0572 under same-pool random selection across 12 independently sampled animal pairs, a lift of 0.0408 (95% confidence interval 0.0031–0.0847). Across 36 independent plant pairs, recall was 0.1098 for ACSP and 0.0912 for random selection, a lift of 0.0186 (95% confidence interval 0.0035–0.0374; pair-level sign-flip p = 0.0233). Positive directions were stable to leave-one-pair-out and repeated cohort-resampling analyses. Plant recovery at 5 km was unstable and was not retained as an exact-location claim. ACSP should therefore be interpreted as a leakage-controlled and budget-explicit method for converting occurrence-conditioned evidence into finite regional survey decisions, not as an exact-site occupancy model. Its supported contribution is modest but independently replicated improvement over random decisions from the same available candidate pools at a 10-km regional scale.

**Keywords:** biodiversity survey design; complementarity; environmental analogue; occurrence data; spatial block cross-validation; survey prioritization; decision support

## 1. Introduction

Biodiversity surveys are frequently planned from opportunistic occurrence records collected for purposes other than standardized sampling. These records can reveal broad environmental associations and geographic patterns, but they do not directly specify which small set of places should be visited next. Species distribution models (SDMs) address the important task of relating occurrences to environmental predictors and projecting a pointwise quantity such as relative suitability, occurrence intensity, or probability, depending on model design. A field team faces a downstream decision: given a fixed number of visits, which finite set of regional search locations should be selected?

A simple ranking of the highest-scoring cells does not necessarily solve this decision problem. Nearby or environmentally redundant cells can consume the budget without broadening geographic or ecological coverage. Conversely, purely spatially balanced designs can spread effort efficiently but ignore focal-taxon evidence. Complementarity, environmental coverage, spatial balance, and SDM-guided survey design are established ideas; ACSP does not claim to originate them. The methodological contribution evaluated here is their placement in an auditable occurrence-to-decision workflow that reconstructs candidates using training data, selects a fixed-size focal-taxon set, and evaluates the final set against decisions drawn from the identical generated pool.

This distinction matters for validation. Conventional prediction metrics assess a model surface or candidate-level scores. They do not directly test whether a Top-k survey decision recovers more withheld observations than another feasible Top-k decision. Comparing selected sites with random points from an unrestricted landscape also conflates candidate generation with selection: a method may appear successful simply because its candidate envelope contains suitable regions. ACSP instead uses a same-pool counterfactual. Both ACSP and random selection receive the same candidate locations and budget, so their difference estimates the added recovery value of the declared selection policy within that pool.

We evaluated ACSP through a frozen, cross-taxon retrospective program. Candidate surfaces were rebuilt independently in each spatial hold-out fold using training occurrences only. Direct occurrence-location and occurrence-distance evidence were excluded before ranking. Development taxa were separated from independent confirmation taxa, failed cases were not replaced, and repeated folds were summarized within taxon–region pairs. Our primary question was whether ACSP Top-5 regional decisions recovered more held-out occurrences within 10 km than random Top-5 decisions from the same candidate pools. We also assessed whether the result was robust to taxon composition and inference seed, while retaining unsuccessful 5-km analyses as evidence against a general exact-location claim.

## 2. Methods

### 2.1 ACSP decision object and frozen policies

The validated ACSP core takes a focal taxon, occurrence records, a bounded survey region, and a fixed candidate budget. Training occurrences characterize locally relevant environmental or terrain states and generate candidate locations. The output is a set of regional search anchors, not an estimated occurrence probability and not a guarantee that each representative coordinate is occupied or accessible.

The confirmatory policies were frozen before the independent cohorts were evaluated. Plant candidates were selected by local-habitat evidence alone. Animal candidates combined local-habitat evidence with geographic complementarity, with weights 0.75 and 0.25, respectively. The budget was five candidates. These narrow policies differ from the current production application, which can incorporate additional observed, macro-model, survey-gap, access, logistics, and field-feedback evidence. Those production extensions are not treated as independently validated in this paper.

### 2.2 Taxon–region cohorts

Taxon–region pairs were sampled using predeclared strata for broad taxonomic group, Japanese geographic region, and regional occurrence-record count. Scientific names used during development were excluded from later confirmation draws. Taxa used in an earlier confirmation cohort were excluded from subsequent extensions. Failed taxa were retained in audit tables and were not replaced with taxa that produced more convenient results.

The supported confirmatory evidence comprises 12 animal taxon–region pairs from an independent mixed cohort and 36 non-overlapping plant pairs: 12 plant pairs from the mixed cohort and 24 additional independently drawn plant pairs. The development cohort was used to establish and freeze the policies and is not the basis of the primary independent effect estimates.

### 2.3 Spatially honest candidate reconstruction

Occurrences were assigned to 0.1-degree spatial blocks. In each of five repeated folds, complete blocks were withheld. The candidate builder received only the remaining training occurrences and reconstructed the candidate pool and local-habitat evidence without access to held-out coordinates.

Known-location and occurrence-supported candidate types were removed before selection. Direct occurrence support, occurrence density, survey-gap distance, environmental novelty derived from known locations, and distance-to-known evidence were excluded from the confirmatory score. This prevented trivial recovery through candidates placed at or immediately around observations that remained in training. Candidate generation and selection were completed before held-out recovery was calculated.

Missing or failed folds contributed zero to the intention-to-evaluate pair mean. This rule prevented technical or ecological failures from disappearing through complete-case analysis.

### 2.4 Fixed-budget recovery and same-pool counterfactual

For each fold, ACSP selected five candidates. A held-out occurrence was counted as recovered when at least one selected candidate lay within the declared recovery radius. The primary frozen endpoint was recall within 10 km. Results at 2 and 5 km were retained as sensitivity analyses, but a 5-km plant effect that failed to replicate was excluded from the supported product claim.

The central counterfactual consisted of 200 random Top-5 sets sampled without replacement from the identical candidate pool. The same-pool design held constant the candidate-generation process, geographic envelope, candidate availability, and survey budget. A greedy oracle using held-out outcomes was computed only to describe theoretical headroom within the candidate pool; because it used outcomes unavailable at decision time, it was not treated as an operational comparator.

### 2.5 Pair-level inference and stability

Repeated folds from the same taxon–region pair were not treated as independent biological replicates. Fold outcomes were averaged within pairs using the fixed five-repeat intention-to-evaluate denominator. Confidence intervals resampled pair means. Pair-level sign flips supplied a randomization test of the mean lift over random selection.

A separate stability audit operated on frozen independent pair-level results without rebuilding candidates or changing the algorithm. Across five random seeds it performed 10,000 pair-level bootstrap draws, 10,000 random half-cohort draws, 10,000 sign-flip draws, and leave-one-pair-out analyses. These procedures evaluated sensitivity to finite cohort composition and inference randomness; they were not substitutes for independent taxon sampling.

### 2.6 Reproducibility and interpretation controls

The publication builder regenerates the retrospective validation table, seed-sensitivity table, machine-readable claim matrix, and frozen plant and animal policy manifests. It does not read field GPS data or post-baseline algorithms. Each policy manifest records the score column, Top-k budget, evidence and complementarity weights, spatial-block size, recovery radius, excluded evidence families, supported wording, unsupported claims, and a deterministic fingerprint.

The current software also implements deterministic geographic, environmental, and combined geographic–environmental maximin selectors on the same candidate pool. These comparators were added to support the next benchmark stage. Their results will not enter this manuscript until the frozen candidate-level fold exports have been evaluated without modifying the ACSP policy.

## 3. Results

### 3.1 Independent animal confirmation

Across 12 independently sampled animal taxon–region pairs, ACSP recovered a mean proportion of 0.0981 of held-out observations within 10 km. Random Top-5 sets from the same candidate pools recovered 0.0572. The mean lift was 0.0408, with a pair-clustered 95% confidence interval of 0.0031–0.0847.

Every leave-one-pair-out mean lift remained positive; the minimum was 0.0258. Across five inference seeds, the minimum bootstrap probability that mean lift was positive was 0.9858, and the minimum corresponding probability among random half-cohorts was 0.9772. The largest pair-level sign-flip p-value across seeds was 0.0853, reflecting the limited power of a 12-pair cohort despite a stable positive direction.

### 3.2 Independent plant confirmation

Across 36 independent plant taxon–region pairs, ACSP recall within 10 km was 0.1098, compared with 0.0912 under same-pool random selection. The mean lift was 0.0186, with a 95% confidence interval of 0.0035–0.0374 and pair-level sign-flip p = 0.0233.

All leave-one-pair-out lifts were positive, with a minimum of 0.0120. Across five seeds, the minimum bootstrap probability of positive lift was 0.9942, the minimum random-half-cohort probability was 0.9913, and the maximum sign-flip p-value was 0.0271. The positive plant direction was therefore not attributable to one pair or one inference seed.

### 3.3 Boundary of spatial precision

The attempted general plant claim at 5 km did not pass independent confirmation. In the additional plant cohort, Top-5 recall at 5 km was 0.0493 compared with 0.0379 for same-pool random selection, but the pair-clustered lift of 0.0114 had a 95% confidence interval of −0.0067–0.0298. The effective candidate-cell width was also too coarse for a general exact-location interpretation. ACSP therefore retains 10 km as its supported regional scale and treats 5-km results as sensitivity evidence only.

## 4. Discussion

The independent cross-taxon results support a bounded conclusion: the frozen ACSP policies added modest regional recovery value beyond random selection from their generated candidate pools. The effect was positive in both animal and plant confirmation samples, persisted under leave-one-pair-out analyses, and was stable across repeated pair-level resampling. Because the counterfactual used the same candidate pool, these effects cannot be attributed merely to placing candidates in a favorable geographic envelope.

The magnitude of improvement was small, especially for plants. This is not unexpected for a strict same-pool comparison: random sets already inherit the candidate-generation process and can recover many held-out observations by chance. The baseline is intentionally harder than random points across a study region. The resulting lift should be interpreted as the additional value of the declared ranking and set policy among already plausible regional candidates, not as the total value of the full occurrence-to-candidate workflow.

ACSP occupies a downstream position relative to SDMs and other environmental-association methods. It can use environmental evidence, but its validated estimand is a fixed-budget finite set rather than a pointwise suitability surface. This difference does not imply that complementarity, spatial balance, environmental coverage, or SDM-guided surveys are new ideas. The contribution is an auditable combination of focal-taxon candidate reconstruction, leakage-controlled finite-set selection, and decision-level same-pool validation.

Random selection is necessary but not sufficient as the only comparator. Established survey-design methods can construct geographically balanced, environmentally balanced, or combined designs without using the ACSP local-analogue ranking. The new comparator implementation enables these methods to be evaluated on the frozen candidate pools. Until that benchmark is completed, this paper should not claim superiority over spatially balanced sampling, environmental maximin sampling, combined geographic–environmental designs, or SDM-led Top-k selection.

The supported spatial scale is also deliberately limited. Ten-kilometre recovery validates regional prioritization, not an exact search point. The 5-km plant interval crossed zero, and candidate-cell resolution places an additional technical ceiling on fine interpretation. High-resolution terrain and generic land-cover refinements tested during development did not provide transferable improvement. Finer claims will require species-relevant vegetation, substrate, moisture, host, hydrographic, or bathymetric information and new independent validation.

Several production functions remain outside the evidence base reported here. The current application can integrate macro-model outputs, access evidence, field feedback, multiple survey areas, route proxies, and alternative Discovery or Learning plans. These features may improve usability and generate testable hypotheses, but they must not be described as cross-taxon validated merely because they are implemented. The machine-readable claim matrix and frozen policy manifests are intended to keep software capabilities separate from evidential status.

Prospective validation should record every attempted site, standardized search duration and area, non-detections, access failures, weather, phenological state, observer, and survey method. Such data would permit evaluation of discoveries per search hour, detection-aware performance, access-adjusted utility, and adaptive learning. The current positive-only retrospective endpoint cannot establish occupancy, specificity, abundance, accessibility, or field efficiency.

## 5. Conclusion

ACSP converts occurrence-conditioned environmental evidence into fixed-budget regional survey decisions and evaluates those decisions against random alternatives from the same candidate pools. Independent plant and animal cohorts supported modest positive lift in held-out occurrence recovery at 10 km, while an attempted 5-km plant claim did not replicate. The current evidence therefore supports ACSP as an auditable regional survey-prioritization framework, not as an exact-site occupancy model or a universally superior survey-design algorithm. The next evidential step is a frozen same-pool comparison with established geographic, environmental, dual-space, and score-only selection methods, followed by prospective effort-standardized field evaluation.
