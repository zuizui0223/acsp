# From occurrence records to field decisions: complementary environmental-analogue prioritization of biodiversity survey zones

## Status

Working manuscript draft. Cross-taxon retrospective results and the *Campanula microdonta* temporal external evaluation are populated. The first field evaluation is retained as the baseline even though it exposed a multi-area allocation failure. A general survey-area-balanced update is reported separately as post-baseline algorithm development rather than being relabelled as an independent confirmation.

## Abstract

Opportunistic occurrence records and species distribution models can characterize environmental associations, but they do not by themselves determine which small, non-redundant set of sites should be visited under a fixed field budget. We developed ACSP, an occurrence-to-decision workflow that reconstructs local environmental analogues from training occurrences and selects a finite set of regional survey candidates. We first evaluated the candidate-selection core using spatial-block hold-out across independently sampled taxon–region pairs. Candidates were rebuilt from training records only, and selected Top-5 sets were compared with random Top-5 sets from the identical candidate pool. At 10 km, recall was 0.0981 for ACSP and 0.0572 for random selection in 12 animal pairs, and 0.1098 versus 0.0912 across 36 plant pairs. We then performed a temporal external evaluation for *Campanula microdonta*. ACSP used 281 Japanese GBIF records dated through 2025; 28 field detections collected in 2026 were withheld from candidate construction and clustered into 19 independent 500-m detection groups. The baseline plant Top-5 concentrated four candidates on Niijima and one on Shikinejima and recovered 5/19 clusters within 10 km, identical to same-allocation random selection. This exposed a general multi-area allocation failure. An area-balanced update selected one candidate on each of five islands and recovered 17/19 clusters within 10 km, but same-allocation random sets averaged 0.857 recall, leaving a ranking lift of 0.037 and a one-sided randomization p-value of approximately 0.50. At 2 km, updated recall was 0.474 versus 0.375 under random selection, a lift of 0.099, although uncertainty remained large. The field case therefore showed that explicit survey-area coverage was operationally important, while evidence ranking within islands provided at most modest additional support in this small dataset. ACSP is not an exact-site occupancy model; its supported contribution is a leakage-controlled, budget-explicit framework for converting occurrence-conditioned evidence into finite survey decisions and testing each decision against an appropriate same-pool counterfactual.

**Keywords:** biodiversity survey design; environmental analogue; occurrence data; external validation; spatial block cross-validation; species distribution model; survey prioritization

## 1. Introduction

Biodiversity surveys are often initiated from incomplete, opportunistic occurrence records. Species distribution models (SDMs) provide established tools for relating such records to environmental predictors and projecting relative suitability across space. Their principal output is generally a continuous surface or cell-level prediction. A field team, however, faces a different operational question: given a limited number of visits, which finite set of places should be surveyed next?

Taking the highest-scoring cells from a suitability surface is not necessarily an adequate answer. Adjacent or environmentally similar high-scoring cells may consume the available budget without expanding geographic or ecological coverage. The same problem arises when a survey contains several disjoint management units, islands, catchments, or protected areas: a globally ranked Top-k set can concentrate nearly all visits in one unit unless representation is part of the set objective. Evaluation metrics such as AUC, TSS, Boyce index, or calibration do not directly test whether a fixed Top-k survey decision is better than another feasible Top-k decision.

ACSP was developed to address this downstream decision problem. It begins with occurrence records, constructs an auditable candidate pool, retains the provenance of different evidence types, and returns a finite set of regional survey candidates. The full application can integrate local environmental analogues, optional macro-scale model support, occurrence support, survey gaps, access information, field feedback, geographic quotas, and trip diagnostics. The present study does not claim that every production component has been independently validated. Instead, it isolates and evaluates the occurrence-conditioned local-environment analogue and set-selection core, then uses an external field case to diagnose where that core requires an additional operational constraint.

The distinction from conventional SDM is therefore one of estimand and decision unit rather than a claim that environmental associations are unrelated to niche modelling. The validated ACSP core asks whether a fixed-size candidate set recovers withheld observations better than random selections from the same generated candidate pool. This same-pool comparison controls the geographic envelope, candidate-generation process, and candidate budget, thereby testing ranking and set selection rather than the mere availability of candidate points.

We combine two validation layers. First, a cross-taxon retrospective benchmark evaluates general performance using spatially withheld occurrence records and independently sampled taxon–region cohorts. Second, a temporal external *C. microdonta* case evaluates transfer from historical GBIF occurrences to field detections collected in a later year. The field case is also used diagnostically: the first baseline result is preserved, and any algorithm change motivated by that result is reported as post-baseline development rather than as an untouched confirmation.

## 2. Methods

### 2.1 Overview of the ACSP decision object

The input to the validated core is a focal taxon, a set of occurrence records, a survey region, and a fixed candidate budget. Training occurrences are used to characterize locally relevant terrain or environmental conditions and to generate candidate locations with a `component_local_habitat_score`. The output is not interpreted as an occurrence probability. It is a finite candidate set intended to serve as regional search anchors.

For plants in the confirmatory cross-taxon benchmark, candidates were selected entirely by local-habitat evidence. For animals, local-habitat evidence received a weight of 0.75 and geographic complementarity a weight of 0.25. The initial *C. microdonta* baseline deliberately reused the validated plant policy without species-specific tuning: global Top-5 selection by local-habitat score.

The production application can use additional evidence, including optional macro-SDM outputs and logistics. Those additions were not the basis of the confirmatory retrospective claim and are treated as downstream extensions.

### 2.2 Retrospective taxon–region sampling

Taxon–region pairs were predeclared and stratified by broad taxon group, Japanese geographic stratum, and regional occurrence-record count. Development taxa were excluded from later confirmation cohorts by scientific name. Previously used confirmation taxa were similarly excluded from subsequent extensions. Failed pairs were retained rather than replaced with more convenient taxa.

The supported confirmatory evidence consists of an independent mixed cohort and an additional independent plant cohort. The animal analysis uses 12 taxon–region pairs from the mixed cohort. The pooled plant analysis uses 12 plant pairs from that cohort and 24 further plant pairs, for 36 non-overlapping plant pairs.

### 2.3 Spatially honest candidate reconstruction

Occurrences were partitioned into 0.1-degree spatial blocks. In each of five repeats, complete blocks were withheld. The candidate builder received training occurrences only and reconstructed the candidate surface and local-environment evidence without access to held-out coordinates.

To avoid trivial recovery through proximity to known observations, known-location or occurrence-supported candidate types were removed before ranking. The benchmark also excluded direct occurrence support, survey-gap distance, environmental novelty, and distance-to-known evidence. Thus, the confirmatory ranking isolated the local environmental analogue pathway, with geographic complementarity retained for animals.

The candidate pool was generated before calculating held-out recovery. Missing or failed folds contributed zero to intention-to-evaluate pair means.

### 2.4 Top-k recovery and same-pool random baseline

The survey budget was fixed at five candidates per fold. A withheld observation was considered recovered when it occurred within the declared radius of at least one selected candidate. The primary supported regional endpoint was 10 km. Results at 2 and 5 km were retained as sensitivity analyses, but the unstable plant result at 5 km was not promoted to a supported exact-location claim.

For every fold, 200 random Top-5 sets were drawn without replacement from the identical candidate pool. This baseline controls candidate availability and tests whether the ACSP selection rule adds value beyond candidate generation alone. A greedy same-pool oracle was also calculated to describe remaining headroom within each candidate pool; it was not treated as an operational comparator because it uses held-out outcomes.

### 2.5 Pair-level inference and stability analysis

Repeated folds from one taxon–region pair were not treated as independent replicates. Fold results were averaged within pair using an intention-to-evaluate denominator of five repeats. Confidence intervals resampled taxon–region pair means. Pair-level sign flips supplied a randomization test.

A separate frozen-cohort stability audit examined sensitivity to composition and random seed without rebuilding candidates or changing the algorithm. Under five seeds, it performed 10,000 pair-level bootstrap draws, 10,000 random half-cohort draws, 10,000 sign-flip draws, and leave-one-pair-out analyses.

### 2.6 Temporal external *Campanula microdonta* evaluation

Japanese GBIF occurrences for *C. microdonta* were requested with coordinate, geospatial-quality, presence-status, country, and year filters. Records dated after 2025 were excluded. After cleaning and deduplication, 281 historical records were used to construct candidates across Oshima, Toshima, Niijima, Shikinejima, and Kozushima. The 2026 field GPS file was not read until the candidate pool and baseline Top-5 had been written.

Candidate generation produced 97 distance-excluded candidates: 24 on Oshima, 24 on Toshima, 16 on Niijima, eight on Shikinejima, and 25 on Kozushima. Known-location candidates and direct occurrence-, distance-, and survey-gap-derived score components were excluded. The baseline selected the global Top-5 by `component_local_habitat_score` with evidence weight 1.0, matching the plant policy used in the cross-taxon benchmark.

The field table contained 28 positive GPS rows. Rows were grouped separately within each island by connected components at a 500-m threshold and represented by observed medoids, yielding 19 independent detection clusters: nine on Oshima, three on Toshima, four on Niijima, one on Shikinejima, and two on Kozushima.

Recovery was measured at 0.5, 1, 2, 5, and 10 km. For each selection policy, 10,000 random Top-5 sets were drawn from the identical candidate pool while preserving the selected number of candidates in each island. Regional distances and same-island-only distances were both calculated; same-island results prevent a Niijima candidate from being credited for a Shikinejima detection.

### 2.7 Post-baseline survey-area-balanced update

The baseline field result revealed that global score ordering could concentrate the entire budget in a subset of explicitly declared survey areas. We therefore added a general set constraint: when the candidate budget is at least the number of non-empty survey areas, the greedy selector must represent every area once before allocating a second candidate to any area. Within that constraint, candidates retain the same local-habitat score ordering and optional geographic complementarity rule. No *C. microdonta* detection coordinate, recovery label, island-specific weight, or species-specific parameter enters the updated selector.

Because this constraint was added after inspecting the baseline allocation, its result is labelled post-baseline algorithm development. The 2026 dataset remains external to score fitting, but it is no longer an untouched confirmatory test for the updated selector. Same-area-allocation random sets are therefore essential for separating the effect of island coverage from the effect of environmental ranking within islands.

### 2.8 Reproducibility

`field_validation/campanula_microdonta/run_temporal_external_validation.py` retrieves historical GBIF records, freezes the baseline Top-5, and only then reads the field GPS file. `compare_area_balanced_update.py` applies the general area-balanced selector to the same frozen candidate pool before evaluating it. The workflow records the GBIF query provenance, training occurrences, full candidate pool, both Top-5 sets, detection clusters, multi-radius recovery, 10,000 random draws, and compact JSON summaries.

## 3. Results

### 3.1 Independent retrospective validation

In the independent animal cohort, ACSP recovered a mean of 0.0981 of held-out observations within 10 km, compared with 0.0572 under same-pool random selection. The resulting lift was 0.0408 across 12 declared taxon–region pairs.

Across the pooled independent plant cohorts, ACSP recall was 0.1098 and same-pool random recall was 0.0912, producing a lift of 0.0186 across 36 pairs. The previously examined 5-km plant effect did not remain stable and is not included in the supported claim.

### 3.2 Stability across seeds and taxon composition

For animals, every leave-one-pair-out mean lift remained positive, with a minimum of 0.0258. Across five resampling seeds, the minimum bootstrap probability that lift was positive was 0.9858, and the minimum corresponding probability among random half-cohorts was 0.9772. The largest pair-level sign-flip p-value was 0.0853. These results support a stable positive direction but reflect limited pair-level power for the 12-pair animal cohort.

For plants, every leave-one-pair-out lift was also positive, with a minimum of 0.0120. The minimum bootstrap probability of positive lift was 0.9942, the minimum half-cohort probability was 0.9913, and the maximum sign-flip p-value was 0.0271. The pooled plant result was therefore stable to both seed and cohort-composition perturbations.

### 3.3 Baseline temporal external result

The global plant Top-5 selected four Niijima candidates and one Shikinejima candidate. It recovered 3/19 clusters within 0.5 km, 3/19 within 1 km, 4/19 within 2 km, and 5/19 within both 5 and 10 km. At 0.5 km, recall was 0.158 versus a same-allocation random mean of 0.103, a lift of 0.054 with one-sided randomization p = 0.246. At 10 km, both ACSP and random selection had recall 0.263, with p = 1.0. Thus, the first external evaluation did not support the global Top-5 policy and exposed severe concentration across survey areas.

### 3.4 Area-balanced update

The updated selector chose one candidate on each island. It recovered 2/19 clusters within 0.5 km, 3/19 within 1 km, 9/19 within 2 km, 13/19 within 5 km, and 17/19 within 10 km. Against random sets with the same one-per-island allocation, 10-km random recall averaged 0.857 and ACSP recall was 0.895, yielding a lift of 0.037 and one-sided p approximately 0.50. At 2 km, random recall averaged 0.375 and ACSP recall was 0.474, yielding a lift of 0.099 and p approximately 0.196. The update greatly improved total field coverage relative to the concentrated baseline, but most of that gain came from enforcing representation across islands rather than from a statistically resolved advantage of environmental ranking within islands.

## 4. Discussion

The retrospective cross-taxon results show that the ACSP local-environment analogue and set-selection core contributes information beyond the geometry of its generated candidate pools at a 10-km regional scale. The relevant counterfactual is random selection from the same candidate pool, not random points across Japan.

The field case adds a different and less flattering but methodologically useful result. Reusing the globally ranked plant Top-5 policy across five islands caused four of five candidates to concentrate on Niijima. Its 10-km recovery was indistinguishable from random sets with the same allocation. The external dataset therefore functioned as a genuine validation file: it identified a failure that was not visible in single-region taxon–region benchmarks.

Adding survey-area coverage corrected the operational allocation problem. However, one candidate on every small island makes a 10-km endpoint easy to satisfy, as shown by the random mean of 0.857. The remaining 10-km ranking lift was small. The larger 2-km lift suggests possible fine-scale information in local environmental analogy, but 19 detection clusters provide insufficient power for a firm claim. Future multi-area benchmarks should therefore distinguish three contributions explicitly: candidate-surface construction, allocation across survey areas, and ranking within each area.

The method remains niche-related because it learns environmental resemblance from occurrence records. Its contribution is not the invention of environmental association or a categorical separation from all SDM concepts. Rather, ACSP formalizes the downstream transition from occurrence-conditioned evidence to a finite set decision and supplies counterfactuals that reveal whether performance comes from ecological ranking, geographic coverage, or merely the candidate envelope.

The updated *C. microdonta* result must not be described as an untouched independent confirmation. Although field coordinates were never used as model inputs, the allocation rule was added after the baseline result exposed the failure. This is algorithm development informed by external validation. Independent multi-area taxa or a later field campaign are needed to confirm the updated policy without outcome-dependent refinement.

Positive-only field detections also limit inference. They do not estimate occupancy, detection probability, specificity, accessibility, or discoveries per search-hour. Future surveys should retain every attempted site, search duration and area, access failure, weather, phenological state, and non-detection.

## 5. Conclusion

ACSP converted historical occurrence-conditioned evidence into finite survey-candidate sets and was evaluated against random sets from the same candidate pools. Independent cross-taxon cohorts supported modest positive 10-km lift for animals and plants. A later-year *C. microdonta* field dataset then revealed that the original global plant Top-5 policy could fail in a multi-island design by concentrating candidates in too few survey areas. A general area-balanced update restored island coverage, but same-allocation random comparisons showed that most of the coarse-scale gain came from representation itself, with only uncertain additional fine-scale benefit from environmental ranking. The combined evidence supports ACSP as an auditable survey-decision framework while also demonstrating why external validation must be allowed to falsify, diagnose, and improve the implemented policy.
