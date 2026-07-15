# From occurrence records to field decisions: complementary environmental-analogue prioritization of biodiversity survey zones

## Status

Working manuscript draft. Retrospective results are populated from frozen independent benchmark cohorts. The *Campanula microdonta* field section is prespecified but remains incomplete until the exact pre-survey ACSP candidate export is recovered. Broad route descriptions must not be substituted for that frozen coordinate-level candidate pool.

## Abstract

Opportunistic occurrence records and species distribution models can characterize environmental associations, but they do not by themselves determine which small, non-redundant set of sites should be visited under a fixed field budget. We developed ACSP, an occurrence-to-decision workflow that reconstructs local environmental analogues from training occurrences and selects a finite set of regional survey candidates, optionally penalizing geographic redundancy. We evaluated the candidate-selection core using repeated spatial-block hold-out across predeclared taxon–region pairs. Within each fold, candidates were rebuilt from training records only; known-location candidates and direct occurrence-distance and density evidence were excluded; and the selected Top-5 set was compared with 200 random Top-5 sets drawn from the identical candidate pool. In an independent animal cohort of 12 taxon–region pairs, 10-km recall was 0.0981 for ACSP and 0.0572 for random selection, a lift of 0.0408. Across 36 independent plant pairs, recall was 0.1098 versus 0.0912, a lift of 0.0186. Repeated pair-level bootstrap, random half-cohort, leave-one-pair-out, and sign-flip analyses showed that the positive direction was not driven by one taxon or one inference seed. We additionally prespecified a prospective field evaluation using 28 positive *Campanula microdonta* GPS records from five Izu Islands. Positive records are clustered before analysis and will be compared with the frozen recommendation set and same-pool random sets with identical island allocations. ACSP should not be interpreted as a replacement for species distribution modelling or as an exact-site occupancy model. Its supported contribution is a leakage-controlled, budget-explicit method for converting occurrence-conditioned environmental evidence into a finite survey decision and testing that decision against an appropriate same-pool counterfactual.

**Keywords:** biodiversity survey design; environmental analogue; occurrence data; prospective validation; spatial block cross-validation; species distribution model; survey prioritization

## 1. Introduction

Biodiversity surveys are often initiated from incomplete, opportunistic occurrence records. Species distribution models (SDMs) provide established tools for relating such records to environmental predictors and projecting relative suitability across space. Their principal output is generally a continuous surface or cell-level prediction. A field team, however, faces a different operational question: given a limited number of visits, which finite set of places should be surveyed next?

Taking the highest-scoring cells from a suitability surface is not necessarily an adequate answer. Adjacent or environmentally similar high-scoring cells may consume the available budget without expanding geographic or ecological coverage. Known observations may dominate rankings even when the purpose is exploratory sampling. Accessibility and travel constraints are frequently applied after ecological modelling, and evaluation metrics such as AUC, TSS, Boyce index, or calibration do not directly test whether a fixed Top-k survey decision is better than another feasible Top-k decision.

ACSP was developed to address this downstream decision problem. It begins with occurrence records, constructs an auditable candidate pool, retains the provenance of different evidence types, and returns a finite set of regional survey candidates. The full application can integrate local environmental analogues, optional macro-scale model support, occurrence support, survey gaps, access information, field feedback, geographic quotas, and trip diagnostics. The present study does not claim that every production component has been independently validated. Instead, it isolates and evaluates the occurrence-conditioned local-environment analogue and complementary set-selection core.

The distinction from conventional SDM is therefore one of estimand and decision unit rather than a claim that environmental associations are unrelated to niche modelling. The validated ACSP core asks whether a fixed-size candidate set recovers withheld observations better than random selections from the same generated candidate pool. This same-pool comparison controls the geographic envelope, candidate-generation process, and candidate budget, thereby testing the ranking and set-selection decision rather than the mere availability of candidate points.

We combine two complementary validation layers. First, a cross-taxon retrospective benchmark evaluates general performance using spatially withheld occurrence records and independently sampled taxon–region cohorts. Second, a prospective *Campanula microdonta* case study tests whether a recommendation object generated before field outcomes can recover detections made during a real multi-island expedition. The retrospective study addresses breadth and resistance to single-species overfitting; the field study addresses external validity and the gap between database records and real survey use.

## 2. Methods

### 2.1 Overview of the ACSP decision object

The input to the validated core is a focal taxon, a set of occurrence records, a survey region, and a fixed candidate budget. Training occurrences are used to characterize locally relevant terrain or environmental conditions and to generate candidate locations with a `component_local_habitat_score`. The output is not interpreted as an occurrence probability. It is a ranked finite candidate set intended to serve as regional search anchors.

For plants in the confirmatory benchmark, candidates were selected entirely by local-habitat evidence. For animals, local-habitat evidence received a weight of 0.75 and geographic complementarity a weight of 0.25. Complementarity was applied during candidate-set selection so that the value of a candidate depended partly on candidates already chosen. This differs from independently sorting all cells and taking the first k.

The production application can use additional evidence, including optional macro-SDM outputs and logistics. Those additions were not the basis of the confirmatory retrospective claim and are treated here as downstream product extensions.

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

A separate frozen-cohort stability audit examined sensitivity to composition and random seed without rebuilding candidates or changing the algorithm. Under five seeds, it performed 10,000 pair-level bootstrap draws, 10,000 random half-cohort draws, 10,000 sign-flip draws, and leave-one-pair-out analyses. The audit therefore tests inferential and cohort-composition stability, not performance on an additional newly sampled cohort.

### 2.6 Prospective *Campanula microdonta* field case

The prospective case uses positive GPS observations collected during fieldwork across Oshima, Toshima, Niijima, Shikinejima, and Kozushima in 2026. The current table contains 28 positive GPS rows. One Oshima longitude was corrected from 135.349870 to 139.349870 before analysis.

Nearby positive rows may represent repeated coordinates or observations within the same local population. Records are therefore grouped separately within each island using connected components at a prespecified 500-m threshold. Each component is represented by an observed medoid coordinate. Thresholds of 1 and 2 km are used as sensitivity analyses for population independence.

The primary prospective endpoint is the proportion of independent detection clusters within 10 km of the frozen ACSP recommendation set. Sensitivity radii are 0.5, 1, 2, and 5 km. The comparison baseline consists of 10,000 random candidate sets drawn from the exact pre-survey candidate pool while preserving both the total recommendation budget and the number selected within each survey area.

The field comparison requires the original candidate export, including all candidates, recommendation flags or ranks, coordinates, survey-area identifiers, candidate roles, algorithm version, and generation timestamp. A route description naming broad habitats such as ports, coasts, settlements, or mountains is insufficient because it does not define the counterfactual candidate pool or the exact frozen selection. Recommendations must not be regenerated after field detections have been inspected.

Because the currently available field table contains positive locations only, this analysis estimates detection-cluster recovery and proximity. It does not estimate occupancy, detection probability, specificity, positive predictive value, accessibility, or discoveries per search-hour. Those quantities require complete visit logs, including non-detections, inaccessible sites, effort, phenology, and searched area.

### 2.7 Reproducibility

`paper/build_paper_outputs.py` rebuilds the retrospective result tables from committed frozen cohorts and clusters the field GPS observations. When the exact frozen candidate pool is absent, it records the prospective analysis as blocked and exits successfully without reconstructing recommendations. When that file is present, the same command creates the observed recovery table, same-pool random distribution, and paper-ready comparison tables.

## 3. Results

### 3.1 Independent retrospective validation

In the independent animal cohort, ACSP recovered a mean of 0.0981 of held-out observations within 10 km, compared with 0.0572 under same-pool random selection. The resulting lift was 0.0408 across 12 declared taxon–region pairs.

Across the pooled independent plant cohorts, ACSP recall was 0.1098 and same-pool random recall was 0.0912, producing a lift of 0.0186 across 36 pairs. The previously examined 5-km plant effect did not remain stable and is not included in the supported claim.

### 3.2 Stability across seeds and taxon composition

For animals, every leave-one-pair-out mean lift remained positive, with a minimum of 0.0258. Across five resampling seeds, the minimum bootstrap probability that lift was positive was 0.9858, and the minimum corresponding probability among random half-cohorts was 0.9772. The largest pair-level sign-flip p-value was 0.0853. These results support a stable positive direction but reflect limited pair-level power for the 12-pair animal cohort.

For plants, every leave-one-pair-out lift was also positive, with a minimum of 0.0120. The minimum bootstrap probability of positive lift was 0.9942, the minimum half-cohort probability was 0.9913, and the maximum sign-flip p-value was 0.0271. The pooled plant result was therefore stable to both seed and cohort-composition perturbations.

### 3.3 Field inventory

The available *C. microdonta* dataset contains 28 positive GPS rows distributed across five islands. The number of independent 500-m detection clusters and island-specific counts are generated by `paper/build_paper_outputs.py` and reported in `paper/generated/table_2_field_inventory.csv`.

### 3.4 Prospective recovery against same-pool random selections

**Pending frozen input.** The exact pre-survey ACSP candidate pool has not yet been recovered. No prospective recovery estimate is reported, and no candidate set has been regenerated after inspection of the field detections. Once the frozen export is restored, the prespecified analysis will populate 0.5-, 1-, 2-, 5-, and 10-km recovery, the corresponding same-pool random distributions, lift, and one-sided randomization p-values.

## 4. Discussion

The retrospective results show that the ACSP local-environment analogue and set-selection core contributes information beyond the geometry of its generated candidate pools. The relevant counterfactual is not random points across all of Japan, which would be trivially weak, but random sets drawn from the same fold-specific candidates under the same budget. Positive lift against that stricter baseline indicates that the ranking and selection rule improved regional recovery.

The effect sizes should be interpreted at the scale supported by the validation. ACSP did not establish exact occupied points, and its representative coordinates are search anchors within regional survey zones. The failure of the plant result to generalize at 5 km is informative: generic terrain and land-cover evidence were sufficient for a modest regional effect but not for transferable fine-scale localization. Species-specific vegetation, substrate, moisture, host, hydrography, or phenology may be needed at finer scales.

The method remains niche-related because it learns environmental resemblance from occurrence records. Its contribution is not the invention of environmental association or a categorical separation from all SDM concepts. Rather, ACSP formalizes and validates the downstream transition from occurrence-conditioned evidence to a finite, non-redundant survey decision. This distinction matters because strong cell-level discrimination does not uniquely determine which k sites should be visited, how redundant candidates should be treated, or what counterfactual should be used to evaluate a field recommendation.

Combining cross-taxon retrospective validation with a real field case strengthens the evidence in complementary ways. Randomly sampled taxon–region pairs reduce the chance that the method was tailored to *C. microdonta*. Conversely, the field case tests whether a frozen recommendation retains meaning outside a retrospective database split. The two effect estimates should not be pooled as if they measured the same quantity: the retrospective endpoint is held-out occurrence recovery, whereas the prospective endpoint is proximity to independently observed field-detection clusters.

The prospective analysis is intentionally blocked until the frozen candidate pool is recovered. This is not merely a data-management inconvenience. Reconstructing candidates after observing successful field locations would introduce outcome-dependent selection and convert a prospective evaluation into a post-hoc illustration. Preserving this boundary is more important than producing an immediate favorable number.

Further prospective surveys should retain every attempted site, search duration and area, access failure, weather, phenological state, and non-detection. Those data would permit direct evaluation of detections or independent populations per unit effort and allow accessibility and field-feedback components of the production application to be learned and validated. Until then, the supported claim remains regional Top-k prioritization rather than occupancy or field efficiency.

## 5. Conclusion

ACSP converts occurrence-conditioned local environmental evidence into a finite survey-candidate set and evaluates that decision against random selections from the same feasible candidate pool. Independent retrospective cohorts showed positive 10-km Top-5 lift for both animals and plants, and repeated stability analyses indicated that the direction was not driven by a single taxon or seed. A prespecified *Campanula microdonta* field comparison will add real-world external validation once the immutable pre-survey candidate export is recovered. Together, the two validation layers provide a more defensible assessment than either a single-species success story or retrospective random benchmarking alone.
