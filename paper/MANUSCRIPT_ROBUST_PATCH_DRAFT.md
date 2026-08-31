# Occurrence-conditioned robust candidate patches for biodiversity field surveys: cross-taxon confirmation and limits to geographic transfer

## Status

Submission-facing scientific draft for the current authoritative ACSP product. The historical finite Top-5 manuscript remains preserved separately in `paper/MANUSCRIPT_DRAFT.md` because it documents an earlier validated decision policy and its matched-pool comparisons. The present manuscript instead follows `VALIDATED_PRODUCT_CONTRACT.md` and treats the independently validated object as a **non-ranked set of bounded robust candidate patches**.

The validated claim is limited to the fixed Japanese 12-region frame. ACSP is **not globally validated**, and the candidate patches are **not occupancy probability**, calibrated suitability probability, exact occupied sites, priority ranks, routes, or budget-optimal itineraries. *Campanula microdonta* is used only as transparent method-development provenance and freeze regression, not as independent confirmation.

## Abstract

Occurrence records can indicate where a species has been observed, but they do not directly define a robust and field-interpretable set of places for subsequent survey. Pointwise species distribution models address a related but different task by estimating a location-indexed fitted quantity, whereas a field workflow also needs an explicit survey object and a rule for abstaining when its evidence supply is inadequate. We developed Adaptive Complementarity-based Survey Prioritization (ACSP), whose current validated core reconstructs occurrence-conditioned environmental support, evaluates that support across leave-one-prototype-out worlds, retains a frozen 2.5% consensus tier, and aggregates selected cells by a deterministic 1-km same-area complete-link rule into bounded, non-ranked candidate patches. We froze the method before opening a taxonomy-safe confirmation cohort of 96 taxon–region pairs in 12 Japanese regional frames. Across 480 declared spatial folds, including failed or empty folds as zero, the candidate-patch tier exceeded same-size random candidate-patch sets by a mean 10-km held-out recovery lift of 0.08559 (pair-bootstrap 95% confidence interval [0.05119, 0.12165]; one-sided sign-flip p = 3.33 × 10⁻⁵). Mean lift was positive for plants (0.05702) and animals (0.11415). We then examined transfer beyond the validated frame without changing the ecological core. A reserved 24-taxon country-framed replication retained positive mean lift (0.08961) but failed its preregistered uncertainty gate because the 95% interval crossed zero slightly. A completely fresh 48-taxon confirmation produced positive lift among integrated-evaluable taxa (0.13230; 95% interval [0.04958, 0.21964]) but failed the preregistered temporal-evaluability gate because only 34/48 taxa had evaluable 2021–2025 outcomes in their frozen countries. A subsequent provider-eligible observability confirmation stopped before held-out evaluation after 29 of 3,161 historical provider queries returned HTTP 429; therefore its hypothesis status was unavailable rather than negative. These results show that the robust candidate-patch core can enrich held-out occurrence recovery in its declared Japanese frame, while geographic framing, observation supply, and ecological support remain separate requirements for automatic transfer. The failed transfer gates and explicit abstention are part of the result rather than grounds for post-outcome rescue.

**Keywords:** biodiversity survey design; candidate patches; occurrence data; environmental support; spatial block validation; field survey planning; transferability; observability; abstention; species distribution models

## 1. Introduction

Biodiversity field surveys are often planned from occurrence records assembled from museums, herbaria, citizen-science platforms, previous expeditions, and opportunistic observations. These data can provide broad ecological and geographic information, but they are spatially biased and incomplete. More importantly, a set of recorded coordinates is not yet a survey plan. A researcher still needs to decide which parts of a declared geographic domain deserve field inspection, how to represent a spatially extended search area, and when the available evidence is too weak to support automatic transfer.

Species distribution models (SDMs) are a central framework for relating occurrence data to environmental predictors and projecting a location-indexed fitted quantity (Guisan and Zimmermann, 2000; Elith and Leathwick, 2009). Depending on data and model design, that quantity may be interpreted as relative suitability, intensity, or occurrence probability. Survey planning can use an SDM surface, but converting the surface into a finite field decision is an additional operation. Thresholding, choosing a number of sites, imposing spatial balance, and translating cells into field-search units are not consequences of model fitting alone.

ACSP addresses this downstream representational problem. The software name reflects its broader development history, but the current validated core does not apply a fixed complementarity bonus and does not rank candidate patches. Its estimand is the set of locations where occurrence-conditioned environmental support remains strong after systematically removing each training prototype in turn. The resulting support cells are converted into bounded patches so that the output is neither a probability raster nor a list of point coordinates presented as exact occupied sites.

This distinction creates three separable questions. First, **geographic framing** asks where the algorithm is allowed to search. Second, **observation and information adequacy** asks whether the historical and later data supply is sufficient to construct and evaluate that frame. Third, **ecological support reconstruction** asks which parts of the supplied candidate universe retain occurrence-conditioned support under perturbation of the training prototypes. A favorable result for the third question cannot repair a frame that excluded the relevant geography, and a technically sound frame cannot be evaluated if the later observation process yields no records.

The Japanese validation avoided silently estimating all three quantities at once. It used the same 12 regional frames that structured the frozen confirmation design, built candidate surfaces independently inside each frame, and tested the ecological candidate-patch rule by spatially withholding occurrence blocks. This fixed-domain experiment therefore evaluates the ecological core within a declared frame; it does not validate automatic global framing.

Our primary question was whether the frozen robust candidate-patch tier enriched held-out occurrences relative to same-size random patch sets within the declared Japanese regional frames. We then asked a separate transfer question: could the unchanged ecological core be combined with a country-framed regional lattice and satisfy preregistered completion, evaluability, and effect gates on new taxa? Finally, after temporal evaluability emerged as the limiting gate, we attempted a separately preregistered observability confirmation. That attempt stopped during historical provider queries before a complete cohort and before held-out years were opened. We retain each terminal outcome exactly as specified rather than conditioning the reported result on successful computation or favorable effect.

The contribution is therefore deliberately bounded. We provide (1) a reproducible occurrence-conditioned robust-support construction; (2) a deterministic conversion from support cells to bounded, non-ranked candidate patches; (3) independent cross-taxon confirmation within a declared Japanese frame; and (4) a prospective record of why the same validated core has not yet become a globally validated name-only product.

## 2. Methods

### 2.1 Scientific estimand and layer separation

Let a declared survey area contain a finite candidate universe

\[
U = \{u_1,\ldots,u_N\},
\]

where each candidate has environmental feature vector \(x_i\), coordinates, and a `survey_area_id`. Let the training occurrences be reduced to environmental prototypes

\[
O = \{o_1,\ldots,o_M\}.
\]

The validated ACSP core maps \((U,O)\) to a set of bounded candidate patches

\[
\mathcal{A}(U,O) \rightarrow \mathcal{P}.
\]

It does not estimate a calibrated response \(P(Y_i=1\mid x_i)\), optimize an explicit number of visits, or order \(\mathcal{P}\) by priority. Geographic-frame construction and observation adequacy are inputs or upstream gates; routing, access, field days, and budgets are downstream decisions. None of those layers is permitted to change membership of the frozen validated patch set.

### 2.2 Japanese confirmation frame and inputs

The independently confirmed domain consisted of 12 fixed Japanese regional rectangles. Each taxon–region pair was processed independently. Overlapping validation regions were not merged after candidate generation because the region identity formed part of the frozen experimental unit.

Within an evaluable region, occurrence retrieval and input generation followed frozen conventions. Up to 150 regional occurrence records were cleaned and deterministically thinned to at most 32 prototypes to reduce domination by duplicated or tightly clustered records. A deterministic 800-point terrain candidate surface was constructed for the region. The confirmed environmental features were elevation, slope, aspect represented by sine and cosine, terrain roughness, and topographic position index. Regions with insufficient complete occurrence prototypes were retained as skipped or failed under the protocol; the support fraction was not widened and another region or taxon was not substituted.

These terrain variables provide an environmental geometry for candidate support. They are not treated as a complete causal description of habitat and do not support exact-site occupancy interpretation.

### 2.3 Robust occurrence-conditioned environmental support

For each feature \(j\), candidate and prototype values were centered by the prototype median and scaled by the prototype interquartile range:

\[
z_{ij}=\frac{x_{ij}-\operatorname{median}(O_j)}{\operatorname{IQR}(O_j)}.
\]

A zero or numerically negligible interquartile range was replaced by a scale of one. The kernel scale was the median nearest-neighbour distance among the standardized occurrence prototypes, lower-bounded at 0.25. Candidate-to-prototype Euclidean distances in this robustly scaled environmental space were converted to prototype responsibility values for diagnostics. Candidate support itself was represented by the percentile rank of the nearest prototype distance, with lower ranks indicating stronger occurrence-conditioned environmental support.

Robustness was evaluated by leave-one-prototype-out reconstruction. For every complete prototype \(o_m\), the method removed that prototype, recomputed the candidate support-rank vector, and stored the resulting world as `float32`. The consensus support rank for candidate \(u_i\) was

\[
r_i=\operatorname{median}_{m=1}^{M} r_i^{(-m)},
\]

and the across-world standard deviation was retained as an uncertainty diagnostic. The validated candidate tier was fixed before confirmation as

\[
U_{0.025}=\{u_i:r_i\le 0.025\}.
\]

The 2.5% quantity is a frozen method parameter for this confirmation contract, not a claim of universal optimality across all candidate surfaces, taxa, features, or scales.

### 2.4 Bounded candidate-patch construction

Selected support cells were aggregated separately within each `survey_area_id`. Cells were processed in deterministic universe/site order. A cell could join an existing patch only when its maximum geodesic distance to every current member was at most 1,000 m. If several patches were compatible, the method chose the patch producing the smallest maximum distance. Otherwise, a new patch was created.

This deterministic complete-link rule prevents a chain of individually short links from creating an unbounded elongated cluster. The representative coordinate of each patch is the member with the strongest ecological support rank, using stable identifiers and coordinates only for deterministic tie-breaking. Patch membership, member count, representative coordinate, patch radius, the fixed merge distance, and validation status are exported. Scores and priority ranks are not part of the validated schema.

A candidate patch is an operationally bounded representation of robust support. It is not asserted to be a mapped population boundary, a contiguous habitat polygon, a barrier-delimited population, or a location at which the species is certainly present.

### 2.5 Taxonomy-safe untouched confirmation

The final Japanese confirmation cohort was frozen before focal occurrence retrieval or outcome evaluation and excluded development taxa and the *Campanula microdonta*/*C. punctata* complex. It contained 96 declared taxon–region pairs, balanced across plants and animals, Japanese regional cells, and occurrence-record strata. Each pair contributed five spatial folds, yielding 480 declared folds.

Complete spatial blocks were withheld. Candidate surfaces and occurrence prototypes were reconstructed from training records only. Held-out coordinates were used only after candidate-patch generation. Failed, empty, or otherwise unevaluable declared folds were retained as zero rather than dropped or replaced.

For each fold, the number of selected robust patches determined the size of the random comparator. Two hundred same-size random subsets were drawn from the same complete candidate-patch frame. A held-out occurrence was counted as recovered when it lay within 10 km of at least one selected patch representative under the frozen regional-screening endpoint. Results were summarized within taxon–region pairs before inference. The confirmation gate required mean lift of at least 0.015, a 30,000-draw pair-bootstrap 95% interval with lower bound greater than zero, a one-sided 30,000-draw sign-flip p-value below 0.05, and positive mean lift in both plants and animals.

### 2.6 *Campanula microdonta* as development provenance

The Izu Island *Campanula microdonta* field material was inspected during method development and is therefore not independent confirmation. Its role was diagnostic. Earlier restricted candidate pools placed a hard upper bound on recovery: only 13 of 19 field-detection clusters were within 1 km of any generated candidate, so no ranking rule could recover all clusters. Expanding to a full-island candidate universe and reconstructing leave-one-prototype-out support removed this upstream ceiling.

The frozen development object used 18 thinned pre-2026 occurrence prototypes and a 22,784-cell full-island universe. Its archived support envelope contained 2,367 cells and reached all 19 development clusters within 1 km, with a maximum nearest distance of 0.86879 km. Aggregation produced 134 bounded same-island patches. These values are retained as development and freeze-regression evidence only. The Campanula-derived threshold was not promoted directly; cross-taxon development and the subsequent untouched cohort supplied the generalized 2.5% confirmation rule.

### 2.7 Country-framed transfer experiments

Automatic use outside the fixed Japanese regional frame requires a rule for defining the outer geographic search universe. Local training-occurrence components were first rejected because they excluded held-out components before ecological candidate generation. A later line therefore used historical focal-species country membership as a broad outer registry, commit-pinned geoBoundaries geometry, and a globally anchored 2° × 2° regional lattice. Every country-intersecting tile contributed 800 deterministic geometry points, while tile boundaries were provenance only and did not become ecological or movement barriers. The occurrence-conditioned robust-support fraction, `float32` leave-one-out worlds, six terrain features, 1-km complete-link aggregation, 10-km endpoint, and 200 same-size random subsets were unchanged.

A reserved 24-taxon replication was prospectively separated from development. It required seven gates covering declared taxa, candidate-generation completion, temporal evaluability, positive mean lift, positive bootstrap lower bound, and non-negative plant and animal means. A later completely fresh 48-taxon confirmation retained the same ecological method and seven primary gates. Scientific failure was recorded as a result rather than a failed software workflow, and inspected taxa were not replaced or reused for retuning.

### 2.8 Prospective observability confirmation and abstention

The fresh 48-taxon experiment showed that later country-specific occurrence availability could prevent evaluation even when the ecological effect among evaluable taxa was positive. A development analysis on already consumed pre-fresh cohorts therefore defined one continuous, pre-heldout observability score:

\[
q=\log\{1+\text{historical records in the frozen selected country}\}.
\]

No score threshold was selected and the score was not allowed to rank candidate patches, replace countries, or rescue the completed transfer decision. A new provider-eligible 96-frame confirmation was preregistered before new candidate identities or focal-species historical queries. Provider eligibility was fixed before final identity selection, and 2021–2025 held-out data could be opened only after an exact complete pre-heldout artifact existed.

The one-shot first activation froze the discovery snapshot and queried historical provider information. Any provider error required `abort_not_evaluable`; no alternate provider, country substitution, taxon replacement, new seed, or second activation was allowed. This deliberately strict contract distinguishes a supply failure from a null biological or observability result.

### 2.9 Reproducibility and claim controls

The validated implementation is planner-free. `acsp.robust_patches` reconstructs support and patch membership without importing historical ranking or route modules, and `acsp.validated_robust` fixes all independently confirmed scientific constants. The user-facing validated table is neutrally ordered by survey area and candidate-patch identifier.

Frozen protocols, cohort manifests, result JSONs, checksums, workflow run identifiers, and failed experiments remain in the repository. The submission alignment validator reads the authoritative constants from `acsp/validated_robust.py`, verifies the two submission tables against frozen transfer records, and checks that this manuscript retains the bounded claims. The preserved historical Top-5 manuscript is not silently rewritten into the new estimand.

## 3. Results

### 3.1 Independent confirmation in the Japanese frame

All five preregistered confirmation criteria passed. Across 96 taxon–region pairs and 480 declared folds, the frozen robust candidate-patch tier achieved a mean 10-km recovery lift over same-size random patch sets of 0.085587. The pair-bootstrap 95% confidence interval was [0.051186, 0.121651], and the one-sided sign-flip p-value was 3.33 × 10⁻⁵. Mean lift was 0.057024 for plants and 0.114150 for animals.

The inference supports enrichment at the declared regional screening scale. It does not establish calibrated suitability, exact occupied-site precision, patch-level detection probability, or superiority of a subsequent route or ranking rule.

### 3.2 Country-framed transfer retained positive effects but failed full gates

In the reserved 24-taxon replication, candidate generation succeeded for 20/24 taxa and temporal evaluation was available for 18/24. Seventeen taxa were both candidate-generated and temporally evaluable. Mean robust-minus-random recovery was positive (0.089608), including plants (0.075153) and animals (0.110260), but the taxon-bootstrap 95% interval was [−0.002480, 0.182429]. Because the preregistered lower-bound gate required a value greater than zero, the replication result was scientific failure with 6 of 7 gates passed and the extension was not promoted.

The completely fresh 48-taxon confirmation produced a different limiting gate. Candidate generation succeeded for 40/48 taxa; 34/48 had evaluable later occurrence data in the frozen country, and 32 were integrated-evaluable. Mean lift among the integrated-evaluable set was 0.132298 with a 95% interval [0.049580, 0.219635]. Plant and animal means were 0.085834 and 0.173295, respectively. The effect and uncertainty gates passed, but temporal evaluability was 0.7083, below the preregistered 0.75 requirement. The complete experiment therefore again failed 1 of 7 gates and did not validate global candidate generation.

Taken together, the transfer experiments do not show a sign reversal of the ecological core. They show that a positive ecological effect conditional on successful construction and later observation is insufficient for an ordinary-use global claim when completion or evaluability gates fail.

### 3.3 The observability confirmation stopped before its hypothesis was testable

The provider-eligible first activation froze 6,147 candidate rows and initiated 3,161 unique historical focal-species provider queries. Of those queries, 3,132 succeeded and 29 returned HTTP 429. Under the frozen all-or-abort rule, no complete authoritative 96-frame artifact was created. The 2021–2025 held-out endpoint remained unopened; candidate patches, robust worlds, random baselines, recall, lift, AUC, and bootstrap inference were not run.

The terminal supply status is `protocol_abort`, the hypothesis status is `unavailable`, and promotion status is `not_promoted`. This is not evidence that the observability score is null or adverse. It is evidence that the complete prospective procedure could not be instantiated under the frozen provider contract.

### 3.4 The validated output is a set, not a ranking

The final validated CSV contains patch identity, survey-area identity, representative coordinates, support-cell count, patch radius, the fixed merge distance, the fixed support fraction, and validation status. Historical integrated scores, SDM support, access values, agreement values, and ranks are absent. The row order is neutral and cannot be interpreted as priority.

This output boundary was important because several earlier attempts to compress support into a small number of recommended points were sensitive to prototype deletion or arbitrary stopping rules. The independently supported scientific object is therefore the robust support-derived patch set; choosing a feasible subset for a particular expedition remains downstream.

## 4. Discussion

### 4.1 Why the Japanese confirmation succeeded but automatic global transfer has not

The results separate a frequently conflated set of tasks. In the Japanese confirmation, the outer geographic frame was already declared, candidate surfaces were consistently generated at a regional scale, and held-out occurrence data were available under the frozen spatial design. The experiment could therefore isolate the ecological question: did the robust support tier enrich withheld records relative to same-size random sets from the same frame? The answer was positive and independently confirmed.

A name-only global workflow has two additional failure points. It must first infer or retrieve a defensible geographic frame, and it must have enough historical and later observation supply to construct and evaluate that frame. Earlier local-component framing excluded about one quarter of held-out records before candidate generation because most misses occupied components absent from the training occurrences. Country framing improved outer-domain recall, but the complete integrated transfer still encountered uncertainty and temporal-evaluability failures. The provider-eligible successor then stopped before a complete test object existed.

Consequently, “validated in Japan” and “not yet validated globally” are not contradictory. The Japanese result identifies a supported ecological transformation conditional on a declared regional universe. The global experiments test a longer chain:

\[
\text{taxon name}
\rightarrow \text{geographic frame}
\rightarrow \text{observation adequacy}
\rightarrow \text{robust candidate patches}
\rightarrow \text{explicit abstention}.
\]

Failure anywhere in this chain blocks a global ordinary-use claim, even when the ecological component is favorable among evaluable cases.

### 4.2 What survived the development history

The strongest common structure across development was not increasingly complex scoring. It was conservative reconstruction under explicit information boundaries. Full candidate universes prevented downstream ranking from being blamed for an upstream absence. Spatial thinning reduced duplicate-record domination. Prototype-median/IQR scaling reduced sensitivity to marginal feature scales. Leave-one-prototype-out worlds prevented one occurrence prototype from defining the support envelope. Median consensus retained only support that persisted across those perturbations. Complete-link aggregation bounded each patch without allowing single-link chains.

By contrast, fixed geographic complementarity weights, learned cross-taxon ranking routers, multiple fine-scale NDVI rules, environmental transition features, and several finite-patch stopping rules did not transfer sufficiently or did not survive stronger controls. Their negative results remain part of the evidence ledger and are not reintroduced under new names.

### 4.3 Relation to SDMs and established survey design

ACSP does not claim that environmental association is unrelated to niche modelling. Both ACSP and SDMs use occurrence-environment relationships. The distinction is the immediate estimand. An SDM fits a location-indexed quantity; the validated ACSP core reconstructs a perturbation-robust support tier and emits bounded candidate patches without fitting presence/background classification or calibrated occurrence probability.

The methods can be composed. An SDM may be useful as an optional exploratory evidence layer after the validated patches exist, particularly when a team wishes to examine extrapolative or sparse-record scenarios. Such use does not make SDM output part of the independently confirmed patch-membership rule. Conversely, this study does not establish that ACSP is superior to SDM, GRTS, biosurvey, or all survey-design methods. Comparisons involving ranked Top-k decisions belong to the preserved historical decision-policy work or to a new prospectively frozen test matched to the current set-valued product.

### 4.4 Limitations

First, the independent ecological confirmation is geographically bounded to the 12 Japanese regional frames. Custom rectangles and country-framed lattices apply related code but do not inherit that confirmation automatically.

Second, the primary endpoint is 10-km held-out occurrence recovery. This is a regional screening endpoint, not evidence that a representative coordinate is occupied. Candidate cell resolution, occurrence-coordinate uncertainty, detectability, and species-specific microhabitat all limit finer interpretation.

Third, the environmental feature set is intentionally narrow and terrain-oriented. It does not represent all relevant vegetation, substrate, host, disturbance, hydrographic, or biotic interactions. Adding higher-resolution generic pixels without species-relevant information did not reliably improve fine-scale transfer during development.

Fourth, retrospective occurrence recovery cannot estimate detection probability, abundance, discoveries per field day, access legality, safety, or route efficiency. Those quantities require prospective attempted-site data, standardized non-detections, effort, season, and access outcomes.

Fifth, the global observability confirmation produced no hypothesis result. Its provider abort is informative about reproducible implementation and supply dependence, but it cannot be used to estimate the observability score's prospective AUC or to classify the hypothesis as null.

### 4.5 Implications for computational ecology practice

A practical implication is that applicability should be reported as a first-class output rather than hidden by complete-case analysis. An algorithm can appear highly effective among evaluable cases while failing to produce or evaluate decisions for a substantial fraction of declared taxa. ACSP therefore retains declared denominators, technical failures, empty folds, temporal zeros, and provider aborts in its decision records.

A second implication is that candidate generation, set representation, and operational selection should not be treated as one opaque score. The validated ecological layer can be tested independently of route heuristics, and operational tools can consume its output without rewriting its scientific meaning. This separation makes both favorable and unfavorable evidence easier to interpret.

The appropriate next global experiment is not a rescue of the consumed cohorts. It is a separately frozen end-to-end procedure with a provider design capable of producing a complete pre-heldout object, an explicit abstention rule, and genuinely fresh heterogeneous taxa and regions. Promotion would require the complete chain—not merely a favorable conditional effect—to satisfy its preregistered gates.

## 5. Conclusion

ACSP's current validated core converts occurrence-conditioned environmental support into non-ranked, bounded candidate patches. In a frozen Japanese 12-region confirmation, the 2.5% leave-one-prototype-out consensus tier enriched held-out occurrences relative to same-size random patch sets across both plants and animals. Attempts to extend the same ecological core through automatic country framing retained favorable conditional effects but failed preregistered uncertainty or temporal-evaluability gates, and the later observability confirmation stopped before held-out testing because its provider contract could not be completed.

The supported conclusion is therefore neither “ACSP works only in Japan” nor “ACSP is globally validated.” It is that a specific robust candidate-patch transformation is independently supported within its declared Japanese frame, while global ordinary-use validity additionally depends on geographic framing and observation supply. Preserving that distinction—and abstaining when the complete procedure cannot be instantiated—is part of the method.

## Data and code availability

The implementation, frozen protocols, cohort manifests, validation records, negative experiments, generated submission tables, and alignment validator are maintained in the public repository `zuizui0223/acsp`. Exact external occurrence snapshots and workflow artifacts are identified by run, artifact, digest, and file-level checksums in the corresponding validation records. A final journal submission should add the repository release DOI and GBIF dataset citations generated from the immutable release snapshot.

## Author contributions

To be completed using the target journal's CRediT taxonomy before submission.

## Competing interests

To be completed by the authors before submission.

## References

Elith, J. and Leathwick, J. R. (2009). Species distribution models: ecological explanation and prediction across space and time. *Annual Review of Ecology, Evolution, and Systematics*, 40, 677–697.

Guisan, A. and Zimmermann, N. E. (2000). Predictive habitat distribution models in ecology. *Ecological Modelling*, 135, 147–186.

Phillips, S. J., Anderson, R. P., and Schapire, R. E. (2006). Maximum entropy modeling of species geographic distributions. *Ecological Modelling*, 190, 231–259.

Roberts, D. R. et al. (2017). Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure. *Ecography*, 40, 913–929.

Runfola, D. et al. (2020). geoBoundaries: A global database of political administrative boundaries. *PLoS ONE*, 15, e0231866.

Stevens, D. L. Jr and Olsen, A. R. (2004). Spatially balanced sampling of natural resources. *Journal of the American Statistical Association*, 99, 262–278.

Zurell, D. et al. (2020). A standard protocol for reporting species distribution models. *Ecography*, 43, 1261–1277.
