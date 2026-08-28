Warning: truncated output (original token count: 51943)
Total output lines: 2681

# AI Change Log

## 2026-08-28 - Codex (OpenAI) - Freeze provider observability terminal boundary

Changed files:
- validation/acsp_provider_eligible_observability_first_activation_terminal_v1.json
- docs/provider_eligible_observability_terminal_2026-08-27.md
- tests/test_provider_eligible_observability_terminal.py
- CHANGELOG_AI.md

Summary:
- Recorded authoritative first-activation run 33031292325 and its stage-1/stage-2 artifact identities.
- Preserved the original `abort_not_evaluable` result after 29 of 3,161 historical provider queries returned HTTP 429.
- Described the terminal result on the prospective two-axis vocabulary as supply `protocol_abort`, hypothesis `unavailable`, and not promoted, without retroactively changing the frozen protocol.
- Fixed the publication consequence at the validated Japanese product plus an auditable global observability/evaluability limit for the Ecological Informatics route.

Features preserved:
- The validated Japanese 2.5% support tier, 1 km candidate-patch aggregation, non-ranked planner-free core, app, optional SDM/SSDM, maps, exports, and field-planning layers are unchanged.
- The 2021–2025 heldout observability outcomes remain unopened, and no candidate patches, robust support, random comparator, recall, or lift were run for the aborted activation.

Known risks / TODO:
- No global or country-framed ACSP product is promoted. MEE still requires a separately frozen end-to-end ordinary-use confirmation; JAE still requires prospective field-utility evidence.

## 2026-08-22 - ChatGPT (OpenAI) - Artifact-derived operational coverage scale

Changed files:
- acsp/operational_selector.py
- acsp/reachability.py
- research/campanula_robust_support_patch_export.py
- test_field_plan_cli.py
- test_operational_cli.py
- test_operational_selector.py
- test_reachability_selector.py
- CHANGELOG_AI.md

Summary:
- Removed the separate hidden `DEFAULT_OPERATIONAL_COVERAGE_FLOOR_KM = 1.0` from downstream operational selection.
- Validated candidate-patch artifacts now provide the downstream redundancy/coverage scale through `patch_merge_distance_m`; the selector verifies that the field is finite, positive, and internally consistent and reports `coverage_scale_source`.
- Legacy or pre-validated candidate tables without merge-distance metadata may fall back only to the median positive finite `candidate_patch_radius_m`, with that fallback explicitly identified in the audit. Non-empty tables with neither usable source now fail instead of inventing a numeric threshold.
- Carried the already-frozen Campanula patch merge distance into the archived patch artifact as provenance. This metadata does not alter robust support, patch identity, or validated candidate membership.

Features preserved:
- The frozen 2.5% leave-one-prototype-out support rule, float32 support worlds, frozen 1 km same-area complete-link candidate-patch aggregation, and 96-pair/480-fold confirmation evidence are unchanged.
- Weighted OSM reachability, no candidate straight-line fallback, and automatic visit-count selection remain downstream and unchanged in behavior.
- The live Campanula 5 km operational smoke remains 22 validated patches -> 14 operational visits, 30 reachability edges, and 5 movement components; the 1.0 km redundancy scale is now traceable to `candidate_patch_artifact.patch_merge_distance_m` rather than a duplicated operational constant.

Known risks / TODO:
- Legacy/pre-validated candidate tables without `patch_merge_distance_m` use the explicitly audited median-positive-radius fallback. That compatibility path is not part of the independently validated candidate-patch claim.

## 2026-08-21 - ChatGPT (OpenAI) - Planner-free package import boundary

Changed files:
- acsp/__init__.py
- acsp/validated_robust.py
- test_package_import_boundary.py
- docs/planner_free_import_boundary.md
- CHANGELOG_AI.md

Summary:
- Converted package-root public exports to lazy resolution so importing `acsp` or the validated candidate-patch APIs no longer imports `acsp.planning`.
- Preserved every existing package-root compatibility export; historical planner, model, and validation modules load only when explicitly requested.
- Added clean-interpreter regressions covering planner-free validated imports and on-demand historical planner loading.
- Updated validated-patch comments to reflect the planner-free aggregation introduced by PR #93.

Features preserved:
- The frozen 2.5% leave-one-prototype-out robust-support rule, float32 support worlds, 1 km same-area patch aggregation, candidate membership, 96-pair/480-fold confirmation statistics, historical planner APIs, app/CLI, optional SDM/SSDM, maps, exports, and field-validation workflows are unchanged.

Known risks / TODO:
- Lazy package-root resolution changes import timing only; package/research suites and isolated wheel imports remain the compatibility gate.

## 2026-08-21 - Codex (OpenAI) - Planner-free robust patch aggregation

Changed files:
- acsp/robust_patches.py
- test_robust_patches.py
- CHANGELOG_AI.md

Summary:
- Replaced the robust candidate-patch core's call into the historical ranked-planner aggregator with a small deterministic complete-link implementation local to `acsp.robust_patches`.
- Preserved same-area patch membership, deterministic patch IDs, representative support cells, representative coordinates, patch radii, and the fixed merge distance while removing planner score, rank, model, access, agreement, and evidence-summary fields from the raw robust patch table.
- Added direct legacy-parity coverage for patch geometry and an explicit regression that forbids planner diagnostics in robust patch output.

Features preserved:
- The frozen 2.5% leave-one-prototype-out robust-support rule, 1 km patch merge, environmental features, candidate membership, and validation claim ceiling are unchanged.
- The historical planner remains available for its existing ranked-planning workflows; only the validated robust-patch core is decoupled from it.
- GBIF and CSV inputs, optional SDM/SSDM, maps, exports, and field-validation workflows are unchanged.

Known risks / TODO:
- The compatibility test intentionally imports the historical planner as a regression oracle; production robust-patch code no longer imports or calls it.

## 2026-08-16 - ChatGPT (OpenAI) - Adaptive survey architecture convergence

Changed files:
- Campanula microenvironment development scripts/workflows and development freezes
- validation/izu_island_microenvironment_random_taxa_20260816/*
- validation/izu_microenvironment_generalization_development/*
- research/acsp_algorithm_component_ledger.json
- research/ACSP_ADAPTIVE_SURVEY_ARCHITECTURE.md
- research/acsp_training_domain_gate.py and tests
- research/develop_izu_nested_training_policy_selection_v2.py and tests
- CHANGELOG_AI.md

Summary:
- Treated Campanula microdonta as a development instrument rather than independent validation and removed the old candidate-universe ceiling by full-island search.
- Preserved negative ablations: static WorldCover composition, the current NDVI transition/gradient representation, mandatory persistent-patch filtering, fixed Campanula microclimate correction, occurrence-count island allocation, and independent environmental Top-cell ranking did not generalize sufficiently.
- The frozen Campanula-derived 0.90 NDVI + 0.10 microclimate ranking failed a predeclared unseen 16-taxon Izu plant transfer (0.7192 recall versus 0.8608 same-allocation random); those 16 taxa are permanently development-only.
- Diagnosed survey-budget saturation: 793 points with a 1 km recovery buffer covered most of the island grid and drove same-allocation random recall to about 0.86, so point count alone is not treated as field budget.
- Reframed the main algorithm as occurrence-conditioned ecological support followed by set-level maximum geographic coverage under an external survey budget.
- Under a strong geometry-only comparator, only q=0.10 / K=5 / 1 km retained a provisional within-island NDVI-support signal (+0.030 recall; bootstrap lower bound >0; sign-flip p<0.05). NDVI between-island allocation and training-occurrence-count allocation were rejected.
- Tested and rejected prototype-LOO environmental reconstruction as an adaptive support-width selector; it reverted to q=1 in 60/80 folds and lost the K=5 q10 advantage. Internal objectives must match downstream survey-set recovery.
- Added fully nested training-only support-policy selection, then tightened it before inspecting v1 output so every q/K comparison uses identical complete inner spatial folds; outer-held-out coordinates remain invisible during q selection.
- Added a component evidence ledger and architecture document. Future experiments must target one unresolved layer and may not silently reintroduce rejected complexity.
- Added a training-only domain gate because the historical kingdom-first surface inference can misclassify aquatic plants as terrestrial. Training land support can override coarse taxonomy in the research method.
- Audited the previously predeclared outside-Izu 24-pair cohort. Its occurrence outcomes remain untouched, but its taxon identities exposed aquatic taxa and motivated the domain gate, so it is no longer eligible as independent confirmation of that gate.

Features preserved:
- Production ACSP behavior, optional SDM/SSDM, maps, exports, and the frozen Practical Core are unchanged by this development line.
- The frozen 192-pair Practical Core confirmation cohort remains untouched and unconsumed.
- Campanula field coordinates do not enter inference-time candidate generation or cross-taxon support-policy selection.

Validation / current gates:
- Campanula development can recover all 19/19 field clusters at 1 km, but Campanula is development evidence only.
- The 16-taxon transfer failure and all subsequent negative development results remain in repository artifacts.
- Training-stability adaptive-support run 31944106155 completed green and was scientifically rejected as the support-width selector.
- Strict fully nested paired support-policy selection is the active scientific experiment; no new external confirmation cohort is consumed before method freeze.

Known risks / TODO:
- Support-policy selection remains unresolved until strict nested development finishes.
- If nested q selection fails, the next allowed change is ecological-support representation (multi-modal or scale-adaptive support), not K/r/q retuning on outer outcomes.
- The domain gate still requires prospective integration into a newly frozen external protocol.
- Route/equal-area field-budget output follows only after ecological support and set selection stabilize.
- Final cross-taxon/cross-island confirmation requires a new post-freeze cohort; inspected cohorts cannot be recycled as confirmation.

## 2026-08-14 - Claude (Anthropic) - Repository simplification and model-optional positioning

Changed files:
- research/ (new directory; 20 benchmark scripts, 12 research tests, 4 research reports moved from the root)
- research/README.md (new)
- .github/workflows/*.yml (11 workflows: research/ paths and PYTHONPATH)
- gbif_fieldmap_builder_app.py
- README.md, AGENTS.md, CHANGELOG_AI.md

Summary:
- Separated the survey-planning tool from the validation pipeline. The repository root is now the tool; benchmark runners, cohort samplers, comparator drivers, and their tests moved to `research/`. Root Python files went from 52 to 20 and root Markdown from 9 to 5.
- Frozen data artifacts (`validation/`, `benchmark_results/`, `benchmark_methods/`, `paper/`, `field_validation/`) were deliberately left at the root so protocol fingerprints and provenance records keep resolving.
- Updated every workflow that reaches into `research/` and split CI test discovery into a survey-tool suite and a research suite.
- Demoted the automatic-mode SDM and SSDM buttons from primary to secondary and rewrote their captions to state that the survey-zone proposal is complete without a model.
- Repositioned the README around survey-site selection, added an explicit "no fitted model required" section, and recorded that no superiority claim over established survey-design tools is supported until the frozen 192-pair confirmation runs.
- Added an AGENTS.md layout rule and a rule that the decision pathway must reach a complete proposal with no fitted classifier in the loop.

Features preserved:
- GBIF pagination, CSV upload, map-click occurrence exclusion, red QC excluded points
- Ensemble SDM, VIF stepwise filtering, spatial partition diagnostics, predict map
- SDM-high exploration candidates, genus/SSDM workflow
- Route planner, HTML/CSV/KML downloads
- Every research script, protocol fingerprint, and frozen cohort remains runnable and unmodified

Validation:
- 103 survey-tool tests and 42 research tests pass, matching the 145 collected before the move.
- No behavioral change to candidate generation, scoring, or zone aggregation; the SDM change is UI emphasis and copy only.

Known risks / TODO:
- The production ranking still applies a `macro_model` weight of 0.15 once SDM is enabled, and that component has no confirmatory support. Revisit after the 192-pair confirmation.
- `legacy/` still contains its own copies of superseded benchmark scripts; they were not touched.

## 2026-07-03 - Codex (OpenAI) - Mobile map rendering performance

Summary:
- Enabled Leaflet Canvas rendering on every Folium map without removing any occurrence, candidate, popup, layer, or drawing control.
- Clustered known-distribution points at broad zoom levels while retaining all individual records when users zoom in.
- Cached automatic distribution and recommended-zone map construction by their dataframe inputs so ordinary Streamlit reruns do not rebuild unchanged maps.
- Added regression tests for full occurrence/member retention, marker clustering, and Canvas configuration.

## 2026-07-02 - Codex (OpenAI) - Publication repository cleanup

Summary:
- Moved superseded Izu, initial SDM-accuracy, and pre-hierarchy national benchmark assets under `legacy/`.
- Extracted retry, radius-coverage, and fold-completion helpers into the supported `acsp.benchmarking` module so the current national benchmark has no legacy dependency.
- Removed temporary notes and completed patch notes from the publication root while preserving them in `legacy/notes/`.
- Kept only the final mixed and plant confirmation artifacts in the active `benchmark_results/` path.

## 2026-07-02 - Codex (OpenAI) - Five-kilometre precision ceiling audit

Summary:
- Added a per-candidate technical precision audit using grid half diagonal, environmental resolution, and coordinate uncertainty.
- Tested and rejected cross-species supervised rankers, Top-8 expansion, climate/covariance variants, and direct GSI point-tile extraction when they failed transferability or latency requirements.
- Retained the independently supported 10 km regional-zone model and documented why 5 km exact-site performance is not currently a defensible name-only claim.

Validation:
- The independent plant 5 km lift remained uncertain despite a useful same-pool oracle ceiling.
- Top-8 combined confirmation still crossed zero; supervised rankers were below random in leave-one-species-out development tests.
- Direct fine terrain extraction exceeded three minutes before completing one three-fold species benchmark and was removed.
- All 74 Python tests pass after adding precision-audit coverage.

## 2026-07-02 - Codex (OpenAI) - Cross-taxon hierarchical regional validation

Summary:
- Added automatic terrestrial, coastal, marine, and inland-aquatic candidate surfaces from GBIF taxonomy plus training-record land fraction.
- Added marine distance-to-land-band habitat evidence, spatially complementary aquatic candidate generation, and water-transit cautions.
- Fixed bird climate predictors being silently discarded when a DEM was available.
- Exported explicit 10 km regional-zone claim fields so representative coordinates are not presented as validated exact sites.
- Added mixed-scale and sensitivity endpoint artifacts, single-group confirmation sampling, and a peer-review-oriented validation report.

Validation:
- 73 unit tests pass.
- Hierarchical development: 24 pairs, 120/120 completed folds, mixed endpoint lift 0.0297 (95% CI 0.0103–0.0523; sign-flip p=0.0063).
- Independent mixed confirmation: 24 unseen taxa, 119/120 completed folds; animal 10 km lift 0.0408 (0.0031–0.0847).
- Independent plant extension: 24 further unseen taxa, 115/120 completed folds; plant 10 km lift 0.0215 (0.0002–0.0481).
- Pooled algorithm-compatible independent plant confirmations: 36 pairs, 10 km lift 0.0186 (0.0035–0.0374; p=0.0233).
- Five-kilometre plant recovery did not replicate. The supported cross-taxon claim is regional 10 km candidate-zone prioritization, not exact-site prediction.

## 2026-07-02 - Codex (OpenAI) - Two-stage recovery and complementary ranking

Summary:
- Added hierarchical regional candidate screening and a deterministic evidence-plus-geographic-complementarity Top-k selector.
- Separated ecological candidate recovery from downstream safety, legal-access, and short-trip screening; production planning still applies those hard constraints.
- Added reusable frozen samples, multiple excluded-cohort files, stored validation ranks, and plant/animal development policies without using confirmatory taxa for tuning.
- Passed resolved GBIF class metadata into the existing bird, mammal, reptile, arthropod, and fish survey-protocol hierarchy.

Validation:
- All 71 unit tests pass.
- On the 24-pair development cohort, 120/120 folds completed. Rankable rates rose to 93.3% for plants and 100% for animals. At 5 km, plant lift over random was 0.0119 (95% clustered CI 0.0007 to 0.0263); animal lift was 0.0190 (-0.0016 to 0.0455).
- A second independent 24-pair cohort excluded every taxon in both prior cohorts. Twenty-two pairs completed and two failed without replacement. At 5 km, plant lift replicated at 0.0442 (0.0045 to 0.1077), while animal lift remained unconfirmed at 0.0195 (-0.0033 to 0.0502).
- The global superiority gate therefore remains failed: evidence currently supports the plant candidate-ranking branch only, not one universal plant/animal model.

Known risks / TODO:
- Animal candidates require a habitat-domain hierarchy (terrestrial, freshwater, marine/coastal) before further weight fitting. A land-only candidate surface is invalid for sea turtles, seabirds, and aquatic taxa.
- Retrospective occurrence recovery does not validate access, detectability, abundance, phenology, or discoveries per field day.

## 2026-07-02 - Codex (OpenAI) - Independent retrospective confirmation

Changed files:
- acsp/validation.py
- acsp/__init__.py
- benchmark_general_random_taxa_regions.py
- test_benchmark_general.py
- RETROSPECTIVE_VALIDATION_PROTOCOL.md
- benchmark_results/general_random_taxa_regions_20260703_unseen_confirmatory/{benchmark_summary.json,predeclared_taxon_region_pairs.csv,pair_status.csv,cohort_summary.csv,fold_recovery.csv,robust_inference.csv}
- .gitignore
- CHANGELOG_AI.md

Summary:
- Added failure-inclusive intention-to-evaluate recovery, taxon-region clustered bootstrap intervals, and pair-level sign-flip tests.
- Added confirmatory taxon exclusion so a new seed cannot reuse any development taxon.
- Froze 5 km as the primary retrospective endpoint, with 2 and 10 km as sensitivity endpoints, before inspecting the independent cohort.

Validation:
- Seed `20260703` drew 24 balanced taxon-region pairs with zero taxon overlap with the development cohort.
- Twelve pairs completed all five folds, five were partial, and seven failed; only 17 pairs were evaluable.
- Fold completion was 58.3% for plants and 65.0% for animals. Rankable-fold rates were 26.7% and 21.7%, far below the predeclared 90% completion and 80% rankable gates.
- At the primary 5 km endpoint, animal ITE lift was -0.0041 (95% clustered CI -0.0130 to 0.0006) and plant lift was -0.0005 (-0.0014 to 0.0000).
- At 10 km, neither animal (-0.0026, CI -0.0130 to 0.0050) nor plant (0.0013, CI -0.0048 to 0.0082) showed confirmed superiority over random.
- The favorable 10 km animal development result did not replicate. No production-weight or superiority claim is justified.

Known risks / TODO:
- Candidate-generation stability, not only ranking, is the dominant blocker on unseen taxa.
- The next algorithm iteration must be developed outside this frozen confirmation set and tested on another excluded-taxon seed.
- Retrospective robustness cannot identify field access, detectability, or phenology weights; those remain explicitly unvalidated.

## 2026-07-02 - Codex (OpenAI) - Stratified national taxon-by-region validation

Changed files:
- acsp/planning.py
- gbif_fieldmap_builder_app.py
- benchmark_general_random_taxa_regions.py
- test_benchmark_general.py
- test_acsp_package.py
- benchmark_results/general_random_taxa_regions_20260702_v2/{benchmark_summary.json,predeclared_taxon_region_pairs.csv,pair_status.csv,cohort_summary.csv,fold_recovery.csv}
- .gitignore
- CHANGELOG_AI.md

Summary:
- Added a seeded general-performance benchmark that balances plant/animal taxa, northern/eastern/western/southern Japan, and four regional occurrence-count strata.
- Added a sparse-pool fallback: when the standard local search yields fewer than six cells, the redundant occurrence-cluster-centre buffer is relaxed while individual training-record separation remains enforced and the fallback stage is exported.
- Marked spatial distance-based habitat fallback scores as occurrence-derived and excluded them from distance-free retrospective scoring.
- Added explicit rankable-fold reporting when the candidate pool exceeds Top-k; folds selecting the entire pool no longer masquerade as evidence about ranking quality.
- Cached repeated GBIF species metadata and region sampling frames without changing the seeded sample.

Validation:
- The predeclared run used 24 fixed taxon-region pairs: 12 plants, 12 animals, three pairs in each taxon-group × geographic-stratum cell, and five spatial holdouts per pair.
- Version 2 completed all five repeats for 23 pairs; the remaining seabird pair failed hard-constraint screening and remains in the denominator. Version 1 had only 17 full, four partial, and three failed pairs.
- Median distance-free candidate-pool size increased from 3 in version 1 to 17.5 for plants and 20 for animals in version 2. Rankable folds were 41/60 for plants and 47/55 for animals.
- On rankable folds at 10 km, animal default recall was 0.135 versus random 0.075 and greedy pool ceiling 0.276. Plant default recall was 0.053 versus random 0.069 and pool ceiling 0.220.
- At 2 km both groups were effectively unrecoverable; at 5 km default and random were close. No global production-weight change is justified.
- All 69 Python tests passed.
- Added intention-to-evaluate inference that assigns zero recovery to failed/missing folds, clusters bootstrap uncertainty by taxon-region pair, and uses pair-level sign-flip tests rather than treating repeated folds as independent.
- At 5 km, neither group showed a robust lift: animal ITE lift 0.0023 (95% cluster-bootstrap CI -0.0042 to 0.0113) and plant lift 0.0005 (-0.0209 to 0.0203).
- At 10 km, animals showed lift 0.0475 (0.0138 to 0.0935; pair-level sign-flip p=0.0129), while plants showed -0.0114 (-0.0515 to 0.0173).
- Version 2 remains a development-set evaluation because its fallback was motivated by version 1 on the same fixed pairs. A new-seed confirmatory cohort is required before treating the 10 km animal result as replicated evidence.

Known risks / TODO:
- Plant and animal ranking performance diverged, so a single universal scoring model is not supported. The next model should branch by life history/mobility and distribution regime while keeping one-name input.
- The seabird failure shows that terrestrial land/access constraints cannot be transferred unchanged to marine or coastal life histories.
- External habitat-layer availability and caching can affect candidate-pool construction; future benchmark artifacts should pin layer versions and export source checksums.
- Recovery remains low at realistic 2-5 km radii. Candidate ranking and macro/local evidence need improvement before claiming superiority over random search.

## 2026-07-01 - Codex (OpenAI) - Full four-island distance-free recovery benchmark

Changed files:
- acsp/validation.py
- benchmark_random_species_models.py
- benchmark_izu_random_taxa.py
- test_acsp_package.py
- test_benchmark_izu.py
- test_benchmark_resilience.py
- benchmark_results/izu_random_taxa_20260701_full/{benchmark_summary.json,predeclared_taxon_sample.csv,taxon_status.csv}
- .gitignore
- CHANGELOG_AI.md

Summary:
- Ran the predeclared 20-taxon, five-repeat four-island benchmark with training-only candidate rebuilding, occurrence-supported candidate removal, occurrence/distance score exclusion, and held-out occurrence matching at 2/5/10 km.
- Distinguished fully completed, partially completed, failed, and evaluable taxa. Empty candidate checkpoints no longer count as successful taxa or break final aggregation.
- Added retry handling for transient GBIF TLS/HTTP failures and isolated failed species-name resolutions instead of aborting the sampling frame.
- Prevented retrospective GBIF recovery from fitting access or field-validation weights. Weight search now uses only varying local-habitat and macro-model evidence; missing components cannot absorb arbitrary nominal weight.
- Added a greedy same-pool recovery ceiling to distinguish candidate-pool limitations from ranking limitations.

Validation:
- Seed `20260701` predeclared 20 plant taxa across four occurrence-count strata: 16 fully completed, one partial, three failed, and 17 evaluable.
- On five completely held-out evaluation taxa, local-habitat Top-5 recall versus same-pool random recall was 0.195 versus 0.210 at 2 km, 0.344 versus 0.322 at 5 km, and 0.374 versus 0.380 at 10 km.
- Greedy same-pool recovery ceilings were 0.374, 0.460, and 0.489 at 2, 5, and 10 km, respectively, showing room to improve ranking as well as candidate generation.
- This run did not include macro SDM, so only local habitat varied retrospectively. The search was correctly classified as uninformative for relative weight fitting and no production-weight change is recommended.
- All 65 Python tests passed after the resilience, completion-audit, component-identifiability, and oracle-baseline changes.

Known risks / TODO:
- Three of 20 predeclared taxa were not fully evaluable, including hard-constraint or distance-free-candidate failures. These failures are part of algorithm performance, not taxa to replace after inspection.
- A separate checkpointed run with macro SDM enabled is required to estimate local-versus-macro weight allocation.
- Access, detectability, phenology, and field-validation weights require prospective standardized surveys and cannot be inferred from GBIF proximity.
- The four-island plant frame does not validate nationwide regions, narrow endemics outside these islands, or animal taxa; those require predeclared stratified benchmark cohorts.

## 2026-07-01 - Codex (OpenAI) - Random-species model accuracy benchmark

Changed files:
- acsp/validation.py
- acsp/__init__.py
- acsp/sdm.py
- benchmark_random_species_models.py
- benchmark_izu_random_taxa.py
- test_acsp_package.py
- test_benchmark_izu.py
- gbif_fieldmap_builder_app.py
- FIELD_VALIDATION_IZU.md
- README.md
- RESEARCH_POSITIONING.md
- CHANGELOG_AI.md

Summary:
- Separated model-accuracy validation from candidate-recovery validation instead of treating withheld candidate recovery as model accuracy.
- Added repeated spatial-block model validation with held-out predictions and ROC-AUC, PR-AUC, Brier, log loss, training-threshold TSS, calibration slope/intercept, and Boyce-style rank correlation for four algorithms and their equal-weight ensemble.
- Added a checkpointed, seeded, occurrence-count-stratified random-species benchmark runner and taxon-level bootstrap uncertainty.
- Added taxon-held-out ensemble weight and probability-shrinkage search. Fourteen taxa select settings and six unseen taxa evaluate them; the search cannot silently tune and report on the same species.
- Kept the equal-weight production ensemble because held-out improvement did not reach the predeclared change threshold. Relabeled SDM output as relative suitability rather than calibrated occupancy probability.
- Kept the four-island candidate-recovery runner as a separate validation track, with four independent island polygons, checkpointing, and predeclared 2/5/10 km sensitivity outputs.
- Added a prospective four-island field protocol using two frozen ACSP sites plus one matched control per island under standardized effort.

Validation:
- Seed `20260701` sampled 20 Japanese plant species across four occurrence-count strata; all 20 completed five valid spatial holdouts (100 folds total) with no post-result species replacement.
- The equal-weight ensemble had mean ROC-AUC 0.629, PR-AUC 0.341, Brier 0.160, log loss 0.499, TSS 0.121, calibration slope 0.525, and Boyce-style correlation 0.374.
- Taxon-bootstrap 95% intervals were 0.586-0.672 for ensemble ROC-AUC, 0.061-0.185 for TSS, and 0.344-0.699 for calibration slope.
- On six taxon-held-out evaluation species, searched weights plus 0.70 probability shrinkage changed log loss from 0.50184 to 0.49977, Brier from 0.16435 to 0.16263, and ROC-AUC from 0.65624 to 0.65699. This did not pass the required >0.01 log-loss improvement, so no production ensemble change was made.
- The benchmark exposed and fixed two performance issues: serial GBIF taxon-name resolution and repeated pandas grouping inside ensemble search.

Features preserved:
- The simple Streamlit workflow, occurrence/local candidates, optional ensemble SDM/SSDM, VIF, spatial partition choices, exploratory candidates, zone planning, and field exports remain available.

Known risks / TODO:
- The 20-species benchmark supports only modest macro-SDM geographic transferability and shows overconfident raw probabilities. Macro support should remain secondary to observed/local evidence.
- Random species were sampled from the top GBIF facet frame meeting the record threshold, so the frame represents recorded Japanese plants rather than all flora.
- The four-island trip is a pilot external validation. Universal scoring weights require more taxa, seasons, observers, regions, and matched controls.

## 2026-07-01 - Codex (OpenAI) - Taxon-held-out weight calibration

Changed files:
- acsp/validation.py
- acsp/__init__.py
- test_acsp_package.py
- README.md
- SURVEY_PLANNING_POLICY.md
- RESEARCH_POSITIONING.md
- CHANGELOG_AI.md

Summary:
- Kept the current 0.35 / 0.25 / 0.15 / 0.10 / 0.10 / 0.05 production weights unchanged and explicitly classified them as starting priors rather than fitted constants.
- Added candidate-level spatial-block benchmark output, including every held-out occurrence ID and each candidate's recovered IDs, so alternative weight vectors can be audited without regenerating environmental layers.
- Added seeded occurrence-count-stratified taxon sampling and a multi-taxon benchmark runner that retains failed taxa instead of replacing them after seeing outcomes.
- Added nested taxon-held-out weight search. Weights are selected only on calibration taxa and evaluated on unseen taxa against current defaults, same-pool random Top-k, local-only, and macro-model-only baselines.
- Added a conservative recommendation gate requiring at least ten successful taxa, more than 0.02 held-out recall lift over defaults, and performance above random. The API never edits production weights automatically.
- Fixed a benchmark denominator bug found during implementation: held-out occurrences recovered by no candidate are now retained in the recall denominator.
- Fixed the first real-taxon pilot failure by auto-detecting the app's `_latitude` / `_longitude` columns and common GBIF/CSV coordinate names in both spatial-validation APIs.

Validation:
- All Python tests passed, including deterministic taxon sampling, training-only candidate rebuilding, unseen-taxon calibration, same-pool controls, insufficient-sample safeguards, and retained taxon failures.
- A seeded (`20260701`) fixed-Izu-extent pilot sampled `Plagiogyria japonica`, `Selliguea hastata`, `Diplopterygium glaucum`, and `Aucuba japonica` across three occurrence-count strata. All four rebuilt from training-only blocks after the coordinate-column fix.
- With one pilot fold per taxon, Top-5 (or the full smaller pool) and a predeclared 2 km recovery radius, default, local-only, macro-only, and same-pool random recall were all 0. This is an uninformative pilot, not support for a weight change. The calibration API now labels flat searches `uninformative` rather than presenting an arbitrary tied vector as evidence.

Features preserved:
- The simple app workflow, integrated production score, occurrence/local candidates, optional SDM/SSDM, model-only exploration, zones, route outputs, and exports are unchanged.

Known risks / TODO:
- No production weight change is justified yet. A predeclared real-taxon benchmark and prospective field results are still required.
- The pilot used only four taxa and one fold each. The next registered run should include at least ten successful taxa, repeated blocks, and predeclared 2/5/10 km sensitivity reporting; radius selection must not be changed after inspecting which value looks favorable.
- GBIF holdout recovery cannot estimate accessibility, detectability, flowering, or survey-effort effects; those weights must be evaluated with field-validation data.

## 2026-07-01 - Codex (OpenAI) - Unified evidence scoring and spatial recovery validation

Changed files:
- acsp/planning.py
- acsp/validation.py
- acsp/__init__.py
- acsp_discover.py
- gbif_fieldmap_builder_app.py
- test_acsp_package.py
- test_acsp_discover.py
- test_automatic_hierarchy.py
- test_zone_planning.py
- README.md
- SURVEY_PLANNING_POLICY.md
- RESEARCH_POSITIONING.md
- CHANGELOG_AI.md

Summary:
- Replaced separate internal `with SDM` / `without SDM` pools and zones with one canonical `candidate_pool`, `zones`, and `recommended_zones` product that is updated when optional SDM/SSDM evidence becomes available.
- Added available-weight-normalized integrated scoring across observed support, local habitat, macro model, survey gap, access, and field validation. Missing SDM/SSDM evidence is unavailable rather than zero.
- Added explicit evidence agreement, divergence, consensus/local-only/macro-only evidence classes, agreement bonus, and a small divergence bonus restricted to exploratory candidate types.
- Removed independent zone-component maxima from the zone score. Zone priority is now 90% the strongest integrated candidate score plus 10% evidence agreement; candidate count and diagnostic component maxima do not increase priority.
- Connected the same integrated support score to ACSP discovery utility while keeping distance redundancy, candidate-to-candidate route insertion cost, spatial-area coverage, and hard constraints.
- Added `spatial_block_recovery_validation()`: repeated random spatial-block holdout with training-only candidate rebuilding, direct occurrence/distance evidence exclusion, and random Top-k controls drawn from the same candidate pool.
- Added integrated component, agreement, divergence, availability, and explanation fields to candidate CSV output and the zone display.

Validation:
- All 54 Python tests passed, including missing-model renormalization, distance-excluded scoring, reproducible spatial-block holdout, canonical bundle keys, zone coherence, and existing SDM/SSDM safeguards.
- `Campanula microdonta`: 31 base candidates / 26 zones / 8 recommendations; automatic SDM updated the same pool to 33 candidates / 28 zones / 7 recommendations in 19.6 seconds. Evidence classes were 27 cross-scale consensus, four known-record anchors, and two macro-model exploration candidates.
- `Cirsium`: 299 fetched records produced 20 observed candidates; SSDM modeled three species and updated the same pool to 40 candidates, with six cross-scale consensus and 20 macro-model exploration candidates.
- A 10-repeat synthetic spatial-block smoke test returned distance-excluded Top-3 recall 0.600 versus random same-pool recall 0.665 (lift -0.065). This deliberately makes no positive performance claim; it confirms that the validation reports unfavorable results rather than guaranteeing apparent improvement.

Features preserved:
- Occurrence/local candidates without SDM, optional ensemble SDM/SSDM, VIF and spatial validation, model-only exploration, zone member points, multiple survey areas, route-cost diagnostics, prediction maps, and exports remain available.

Known risks / TODO:
- The spatial-block validation API enforces a training-only callback contract, but ecological performance claims still require real taxon-specific candidate rebuilding and matched field/retrospective benchmarks. Unit simulations validate mechanics only.
- Integrated weights and the 10% agreement contribution are transparent starting values, not fitted universal constants. Compare component ablations, spatial-block recovery, and field detection before publication claims.

## 2026-07-01 - Codex (OpenAI) - Zone auditability and survey-area clarity

Changed files:
- acsp/planning.py
- acsp_discover.py
- gbif_fieldmap_builder_app.py
- README.md
- test_acsp_discover.py
- test_automatic_hierarchy.py
- test_zone_planning.py
- CHANGELOG_AI.md

Summary:
- Fixed polygon survey-area selection so records are tested against the actual polygon instead of only its bounding box.
- Fixed automatic survey-area maps to read remote-noise classifications from the region audit, show those excluded points in red, focus initially on the active working area, and keep alternative occurrence regions in an optional layer.
- Replaced the inaccurate `diameter / 2` display radius with the actual maximum medoid-to-member radius so the suggested-area circle covers its assigned records.
- Kept every candidate point belonging to a recommended zone visible on the zone map, with representative and alternative points distinguished, while retaining full point CSV exports.
- Added zone merge thresholds, score-method text, evidence-source site IDs, and an explicit warning when evidence maxima come from different points in the same zone.
- Simplified the first map wording to `Known distribution and survey area` and clarified that this area affects observed-data candidates but not the independent SDM/SSDM extent.

Features preserved:
- Occurrence-supported candidates, high-resolution habitat candidates, optional SDM/SSDM re-ranking, model-only exploration, complete-link zone aggregation, multi-area logistics, raw and working records, VIF/spatial validation, prediction maps, and exports remain available.

Known risks / TODO:
- Zone scoring remains an interpretable density-neutral heuristic based on component maxima. It is now auditable, but representative-point scoring, robust quantiles, and the current approach still require retrospective and field comparison.
- Deterministic greedy complete-link assignment prevents chain zones but is not a globally optimal clustering solution; sensitivity to merge thresholds should be included in method validation.

## 2026-06-30 — Issue #25 zone-level proposals

- Consolidated nearby candidate points into deterministic complete-link survey zones before final ranking.
- Added representative sites, practical footprints, plain-language zone roles, and density-neutral evidence aggregation.
- Added stable initial/model ranks, rank changes, agreement scores/classes, and compact SDM/SSDM agreement summaries.
- Replaced the automatic split candidate panels with one Recommended survey zones surface.
- Added zone CSV/API/CLI/R outputs and made the GitHub Action emit zone-level recommendations.
- Replaced the fixed two-day assumption with an internal one-to-five-day feasibility curve and automatic knee selection.
- Added candidate-to-candidate route insertion cost to final plan utility while retaining ecological complementarity.
- Fixed multi-island planning so one field day cannot mix separate survey areas, every selected area receives coverage before duplicates, and local distance uses an area-level hub.
- Multi-island outputs now report unmodeled ferry/flight transfers and very-low routing confidence instead of treating sea crossings as roads.

## 2026-06-30 - Codex (OpenAI) - Fast cached macro-climate SDM/SSDM

Changed files:
- gbif_fieldmap_builder_app.py
- test_automatic_hierarchy.py
- README.md
- CHANGELOG_AI.md

Summary:
- Replaced the one-click SDM/SSDM dependency on slow remote CHELSA strip reads with cached NASA POWER MERRA-2 1981-2010 temperature and precipitation normals.
- Derive BIO1, BIO4, BIO12, BIO14, and BIO15 from monthly normals, retrieve large regions in bounded tiles, retry transient requests, and preserve the existing CHELSA/WorldClim choices in advanced/manual SDM.
- Interpolate the coarse macro-climate normals to a bounded display/prediction grid, then clip it to the independent QC-derived prediction geometry and land mask. The UI and method record explicitly report the native coarse climate resolution.
- Reused the same environment path for species SDM and genus SSDM without changing ensemble algorithms, spatial validation, variable selection/VIF, observed candidates, model-supported re-ranking, or model-only exploration candidates.

Validation:
- `Lilium auratum` (Japan): 299 GBIF records; occurrence and habitat candidates in 16.6 seconds; four-model automatic SDM in 20.3 seconds; 6,659 prediction cells and 20 model-only exploration candidates; 41.3 seconds total including GBIF retrieval.
- `Cirsium` (Japan): 569 fetched genus records; 20 observed-richness candidates; six species modeled; 4,832 SSDM cells and 20 model-only richness exploration candidates; SSDM completed in 55.7 seconds.
- Izu-island test extent produced 327 valid land prediction cells, including small-island areas, instead of depending on coarse source-cell centers falling on land.
- `python -m unittest test_automatic_hierarchy.py test_gbif_fetch_resilience.py test_acsp_package.py test_acsp_cli.py test_acsp_discover.py` passed 36 tests.
- `python -m py_compile gbif_fieldmap_builder_app.py` passed.

Scientific limitation:
- NASA POWER is a fast macro-climate filter, not a high-resolution habitat layer. The interpolated prediction grid must not be interpreted as adding climate detail beyond the native POWER grid; fine-scale site discrimination remains the role of GSI terrain, habitat analogue, access, occurrence support, and field validation.

## 2026-06-30 - Codex (OpenAI) - Model-connected recommendations and clearer evidence maps

Changed files:
- gbif_fieldmap_builder_app.py
- test_automatic_hierarchy.py
- README.md
- CHANGELOG_AI.md

Summary:
- Added explicit observed/model agreement scoring so existing candidates supported by both occurrence evidence and SDM/SSDM move upward transparently.
- Added spatial non-maximum suppression for model-only exploration cells, avoiding the previous single-link DBSCAN behavior that could collapse a continuous high-suitability region into one candidate.
- Added model-connected recommendation quotas: ordinary priority ranking remains primary, with one best model-only exploratory site retained when at least three slots are available.
- Rebuilt automatic SSDM exploratory candidates from the full richness grid and applied a final global re-ranking after observed and model-only candidates are combined.
- Removed the second CHELSA extraction pass for existing candidate coordinates by sampling suitability from the completed SDM prediction grid.
- Split result-map layers into observed/local points, model-only exploratory points, and recommended 500 m survey ranges; added a compact evidence legend.
- Added export fields for candidate evidence, model agreement, agreement bonus, exploration bonus, and recommendation basis.

Validation:
- Reproducible random seed `20260630` selected species `Lilium auratum` and genus `Viola`.
- Random species extent `(138.73423, 36.92800, 140.13423, 38.32800)` retained 17 records and produced 13 candidates / 3 recommendations without SDM.
- Random genus extent `(139.12806, 35.43241, 139.42806, 35.73241)` retained 94 records and produced 16 observed-richness cells / 3 recommendations without SSDM.
- Unit coverage verifies agreement re-ranking, idempotent re-ranking, model-only quota retention, spatially separated SDM/SSDM exploration, completed-grid candidate support, and separated map layers.
- End-to-end remote SDM attempts did not finish within eight minutes. Inspection found the current CHELSA GeoTIFF endpoint exposes full-width strips and no internal overviews, so remote regional reads remain an external performance risk. No successful AUC claim is made for this validation run.

Features preserved:
- Occurrence-only candidates, optional independent SDM/SSDM, automatic QC, variable selection/VIF, spatial validation, raster prediction maps, model-only exploration, full candidate downloads, and field-validation exports remain available.

Known risks / TODO:
- Replace or pre-cache the current remote CHELSA source with a genuinely tiled/overviewed regional source before claiming consistently fast one-click SDM on Streamlit Cloud.
- Model-only recommendation reservation is a transparent heuristic and should be compared with pure top-ranked selection during field validation.

## 2026-06-30 - Codex (OpenAI) - Automatic SDM read-only fix, clearer candidate maps, and package extents

Changed files:
- gbif_fieldmap_builder_app.py
- acsp/__init__.py
- acsp/planning.py
- acsp/cli.py
- r-acsp/R/recommend.R
- r-acsp/man/acsp_recommend.Rd
- test_acsp_package.py
- test_acsp_cli.py
- test_automatic_hierarchy.py
- README.md
- CHANGELOG_AI.md

Summary:
- Fixed automatic SDM/SSDM variable selection under pandas copy-on-write by zeroing the correlation-matrix diagonal on an explicit writable NumPy copy.
- Changed automatic result maps to show the full candidate pool as points while drawing green 500 m survey buffers only around recommended sites.
- Added inclusive rectangular extent filtering to the Python and R recommendation APIs, ordered as west, south, east, north.
- Added Python CLI support through `--extent WEST SOUTH EAST NORTH` and documented package examples.

Validation:
- `python -m py_compile gbif_fieldmap_builder_app.py` passed.
- All 29 Python unit tests passed, including pandas copy-on-write, extent API/CLI, and candidate-map buffer regression tests.
- The updated Streamlit app booted locally with no browser console errors.

Features preserved:
- Full candidate pools remain visible and downloadable; recommended-site identity, optional SDM/SSDM, independent model extents, VIF/variable selection, prediction maps, exploratory candidates, and exports remain available.

Known risks / TODO:
- Package extent filtering currently supports non-dateline-crossing rectangles; polygon and antimeridian extents are not yet exposed as package APIs.

## 2026-06-30 - Codex (OpenAI) - Four-model ensembles and publication-ready repository metadata

Changed files:
- gbif_fieldmap_builder_app.py
- acsp/__init__.py
- acsp/modeling.py
- pyproject.toml
- r-acsp/R/modeling.R
- r-acsp/NAMESPACE
- r-acsp/man/acsp_default_algorithms.Rd
- r-acsp/README.md
- r-acsp/inst/CITATION
- test_acsp_package.py
- README.md
- LICENSE
- CITATION.cff
- .github/workflows/package-checks.yml
- CHANGELOG_AI.md

Summary:
- Expanded automatic species SDM and per-species SSDM from two tree ensembles to four model families: Logistic regression, Random forest, ExtraTrees, and Gradient boosting.
- Final suitability remains an explicit equal-weight probability ensemble; diagnostics identify the best individual model without replacing the ensemble.
- Moved supported classifier construction and equal-weight prediction into the reusable Python package and made the Streamlit compatibility factory use that API.
- Added the matching default algorithm specification to the R package.
- Expanded Python package metadata with scikit-learn dependency, MIT license, repository URLs, development extras, and publication classifiers.
- Added root MIT license, `CITATION.cff`, R package citation metadata, and GitHub Actions checks for Python 3.10-3.12 plus R package checking.
- Rewrote the GitHub README to describe the current two-result workflow, full candidate maps, four-model 30-second SDM, reporting outputs, Python/R package APIs, validation status, citation, and publication path.
- Added shared remote-raster open retries for transient CHELSA COG DNS/HTTP failures.

Validation:
- Python editable package build/install succeeded with the expanded four-model API.
- Local classifier tests fit Logistic regression, Random forest, ExtraTrees, and Gradient boosting and verified equal-weight ensemble probabilities.
- `python -m py_compile gbif_fieldmap_builder_app.py` passed and all 24 Python tests passed.
- The `Campanula microdonta` end-to-end rerun reached environmental extraction but could not complete the new four-model AUC comparison because the external CHELSA COG endpoint remained unavailable after four retries. The previously completed two-model validation remains documented below; no unverified four-model AUC is reported.
- R is not installed in the current Windows environment, so R package checking is delegated to the added GitHub Actions workflow.

Features preserved:
- Occurrence-only candidates, independent optional SDM/SSDM, QC, variable selection/VIF, spatial partition diagnostics, full candidate maps, model-high exploration candidates, exports, and field-validation outputs remain available.

Known risks / TODO:
- Four algorithms increase optional SDM/SSDM runtime relative to the previous two-model ensemble.
- PyPI/CRAN/Zenodo publication still requires final author metadata, release review, and repository-owner credentials.
- R CMD check is delegated to GitHub Actions because R is not installed in the current Windows environment.

## 2026-06-30 - Codex (OpenAI) - Full candidate maps, publication metadata, and Python/R packages

Changed files:
- gbif_fieldmap_builder_app.py
- acsp/__init__.py
- acsp/planning.py
- acsp/sdm.py
- pyproject.toml
- r-acsp/DESCRIPTION
- r-acsp/NAMESPACE
- r-acsp/LICENSE
- r-acsp/R/recommend.R
- r-acsp/R/sdm.R
- r-acsp/man/*.Rd
- r-acsp/README.md
- README.md
- .gitignore
- test_acsp_package.py
- CHANGELOG_AI.md

Summary:
- Changed both without-model and with-model maps to display the complete eligible candidate pool. Recommended sites remain distinguishable with the existing green selected-site outline.
- Added model-performance reporting for each ensemble member, equal ensemble weights, the best individual model, validation AUC, and AUC warnings.
- Added a manuscript-ready SDM method record containing occurrence counts before/after QC, background count, automatically selected partition and reason, predictors, 30-second CHELSA source, independent prediction extent, ensemble definition, best model, AUC, and a methods-text paragraph.
- Added CSV downloads for the SDM method record and model-performance table.
- Added the installable `acsp-survey` Python package with candidate recommendation, spatial-partition selection, ensemble-performance summarization, and method-record APIs. The Streamlit app now uses these package functions through compatibility wrappers.
- Added the initial base-R `acsp` package under `r-acsp`, with matching recommendation, partition, and method-record functions plus package metadata and manual pages.
- Updated README instructions for Python and R development installs and the simplified two-result app workflow.

Validation:
- Python editable package build/install succeeded as `acsp-survey 0.1.0`.
- `Campanula microdonta` four-area rerun retained candidate pools of 22/18/20/21 without SDM and 23/18/20/21 with SDM; each area retained three recommendations.
- The fitted ensemble used Random forest and ExtraTrees at equal 0.5 weights. Random forest was the best individual model (AUC 0.970); ExtraTrees AUC was 0.926.
- Automatic validation selected random 75/25 holdout because 86 post-QC records had a minimum SDM extent span of 1.80 degrees. High/random-split AUC cautions are exported.
- `python -m py_compile gbif_fieldmap_builder_app.py` passed and all 22 Python tests passed.
- R is not installed in the current environment, so `R CMD check` could not be run; the R package uses base R only and received static structure/documentation checks.

Features preserved:
- Full observed candidate generation, optional independent SDM/SSDM, 30-second COG prediction maps, spatial QC, VIF/variable selection, model-only exploration candidates, map exports, and field-validation outputs remain available.

Known risks / TODO:
- The initial R package mirrors the reusable ranking and reporting core; GBIF retrieval, raster SDM fitting, and full SSDM fitting are not yet exposed as R package APIs.
- AUC 0.970 from random holdout is potentially optimistic and must be reported with the exported validation warning rather than treated as definitive transferability evidence.

## 2026-06-29 - Codex (OpenAI) - Four-area planning, 30-second COG SDM, and two-result workflow

Changed files:
- gbif_fieldmap_builder_app.py
- test_automatic_hierarchy.py
- CHANGELOG_AI.md

Summary:
- Simplified the automatic product surface to the actual user decisions: enter a species/genus name, optionally draw one or more survey areas, and optionally generate model-supported candidates.
- Removed the visible Balanced / Discovery / Learning outputs. The automatic workflow now shows only `Candidates without SDM/SSDM` and, after the optional model run, `Candidates with SDM/SSDM`.
- Added equal, transparent top-ranked quotas: three recommended sites per drawn survey area. Full candidate pools remain downloadable.
- Treats multiple rectangles/polygons as independent survey areas. Candidate grids, GSI terrain retrieval, habitat profiles, ranking quotas, and area IDs are calculated separately, avoiding candidate concentration in the record-richest island and excluding the sea/gaps between rectangles.
- Replaced the automatic SDM/SSDM dependency on the 628 MB global WorldClim 2.5-minute ZIP with CHELSA V2.1 BIOCLIM 30-second Cloud-Optimized GeoTIFFs.
- The app now derives the independent SDM extent after automatic occurrence QC and reads only the required raster windows via HTTP range requests; it does not download a global climate archive.
- Automatic macro models use BIO1, BIO4, BIO12, BIO14, and BIO15 before ecological representative variable selection. Local 100 m terrain discovery remains a separate GSI-based step.
- When survey areas are drawn, model-high exploration candidates are clipped back to those areas before recommendation.
- Applied the same simplified output structure and 30-second COG source to genus/SSDM mode.
- Hid legacy automatic-region choice cards; the default region is automatic and the only range interaction is optional map drawing.

Four-island validation (`Campanula microdonta`):
- GBIF total 300; cleaned records 87; four-area selected records 26.
- Automatic SDM QC excluded the remote point at 33.635783, 134.493324 and retained 86 SDM records.
- Without SDM candidate pools by area: Izu Oshima 22, Toshima 18, Niijima 20, Kozushima 21; three recommendations per area.
- With SDM candidate pools by area: Izu Oshima 23, Toshima 18, Niijima 20, Kozushima 21; three recommendations per area.
- The 12 recommended site IDs changed from `[1,6,7] / [28,31,32] / [44,46,47] / [63,64,65]` without SDM to `[1,12,11] / [37,38,28] / [55,56,45] / [67,71,80]` with SDM.
- The full automatic SDM completed successfully with 2,145 land prediction cells. Ecological representative selection retained BIO1 and BIO12 for this run.
- `python -m py_compile gbif_fieldmap_builder_app.py` passed and all 20 unit tests passed.

## 2026-06-29 - Codex (OpenAI) - Revalidate four-island plans and preserve one-day drawn-area missions

Changed files:
- gbif_fieldmap_builder_app.py
- test_automatic_hierarchy.py
- CHANGELOG_AI.md

Summary:
- Treat an explicitly drawn reachable survey area as a one-day mission; the automatic recommended region remains a two-day proposal.
- Preserve that target-day choice after optional SDM/SSDM support re-ranks candidates.
- Added `Eligible candidate pool` to the species proposal metrics so users can see the full usable pool separately from the selected one-day priority plan.
- Applied the same one-day drawn-area rule to the mirrored genus workflow.

Validation:
- `Campanula microdonta` matched 300 GBIF coordinate records and retained 87 cleaned records.
- Automatic SDM QC excluded one remote point at 33.635783, 134.493324; 86 records remained for the independent SDM workflow.
- Izu Oshima: 22 eligible candidates; one-day Balanced plan 3 sites.
- Toshima: 20 generated, 19 eligible candidates; one-day Balanced plan 3 sites.
- Niijima: 20 eligible candidates; one-day Balanced plan 3 sites.
- Kozushima: 21 eligible candidates; one-day Balanced plan 3 sites.
- Every one-day Balanced plan selected one occurrence-supported anchor, one Survey-gap site, and one Environmental-test site.
- All four areas used 100 m discovery cells and app-provided GSI terrain (DEM10B on the tested Oshima extent; DEM5A on Toshima, Niijima, and Kozushima).
- Full SDM execution reached environmental-raster retrieval, then the external WorldClim host timed out; observed candidates and the verified automatic QC result remained available.
- `python -m py_compile gbif_fieldmap_builder_app.py` and all 18 unit tests passed.

## 2026-06-29 - Codex (OpenAI) - Unified taxon-name workflow with automatic Species/Genus routing

Changed files:
- gbif_fieldmap_builder_app.py
- test_automatic_hierarchy.py
- CHANGELOG_AI.md

Summary:
- Removed the visible `Species name only` versus `Advanced / manual` workflow choice. The app now has one taxon-name-first surface.
- Renamed the sole input to `Species or genus scientific name` and uses the matched GBIF rank to route species-level taxa to occurrence/SDM planning and genera to observed-richness/SSDM planning.
- Kept survey-area drawing optional. Without a drawing, ACSP uses its recommended compact region; a drawn reachable area rebuilds observed-data candidates inside that area.
- Retained the advanced algorithms as automatic internals rather than deleting them: representative occurrence subsets, remote-outlier QC, environmental selection, spatial validation, ensemble SDM/SSDM, model-supported re-ranking, model-high exploration candidates, ACSP set selection, routing, and field-validation exports remain available.
- Added one-click optional species SDM support with fixed lightweight defaults: at most 300 spatially representative presences, automatic remote-outlier QC, ecological representative variable selection, automatic spatial validation, Random Forest plus ExtraTrees, and a 40,000-cell prediction cap.
- Added the mirrored automatic genus workflow: observed richness hotspots first, optional one-click SSDM, predicted-richness re-ranking, SSDM-high exploration hotspots, plan CSV, field-validation CSV, Google Maps routes, and the richness/candidate maps.
- Kept SDM/SSDM optional so ordinary occurrence-supported planning remains fast and usable without modeling.

Validation:
- `python -m py_compile gbif_fieldmap_builder_app.py` passed.
- 18 unit tests passed, including new synthetic genus richness and plan generation coverage.
- `Campanula microdonta` matched `SPECIES`: 87 cleaned Japan records, 31 total observed/habitat candidates, and 5-site Balanced, Discovery, and Learning plans.
- `Cirsium` matched `GENUS`: a 900-record retrieval produced 742 cleaned records, 6 modeled species labels, 53 observed-richness c…21943 tokens truncated…er the Performance summary block.

Features preserved:
- `sl_selected_site_ids` session state unchanged.
- Auto/Manual/rectangle selection logic fully preserved inside `route_planner_panel`.
- Google Maps links, CSV, HTML, KML downloads preserved.
- Phase 1, Phase 2, SDM expander, VIF, prediction map, performance summary, methods text untouched.
- `add_priority_rank`, `order_sites`, candidate generation unchanged.
- `layers` dict controlling occurrences/predict overlay/candidate_circles preserved.

Known risks / TODO:
- `html_bytes` (used by "Download sampling HTML map") now comes from the map built inside the merged section; verify the reference is still in scope.

## 2026-06-04 - Claude (claude-sonnet-4-6) — Add SDM record-count guidance and candidate-type labels

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:

**SDM record-count guidance (above "Optional: Build SDM" subheader)**
Added `st.info(...)` block using `min(len(occ_raw), sdm_working_records)` as the preview presence-point count. Four tiers: very few (<20), few (20–49), moderate (50–299), abundant (≥300/cap). Guidance helps users understand when SDM adds the most value relative to occurrence density.

**Candidate-type captions**
Added `📍 Occurrence-supported candidates` caption above the SDM-high exploration expander, and `🔭 SDM-high exploration candidates` caption inside the "Create SDM-high exploration ranges" expander, clarifying confidence levels and the need for field validation.

**SDM cap explanation caption**
Added `st.caption(...)` immediately after the `sdm_ind_max_presence` number_input explaining that SDM uses a spatially representative subset regardless of record count, and that the cap is most relevant for abundant-record species.

No Phase 1 or Phase 2 logic was changed. No SDM pipeline order or `auto_sdm_partition` logic was modified.

---

## 2026-06-04 - Claude (claude-sonnet-4-6) — Merge Phase 1 and Phase 2 maps; remove sidebar caption

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:

**Draw rectangle directly on Phase 1 national distribution map**
- Added `folium.plugins.Draw` (rectangle only) to `make_macro_cluster_map` so users can draw the survey area rectangle on the Phase 1 overview map instead of needing a separate Phase 2 map.
- Phase 1 `st_folium` now returns `["all_drawings", "last_active_drawing"]` and handles draw state (stores to `target_rect_features` / `target_last_draw_sig`).
- Added "Clear survey rectangle" button next to the Phase 1 map.
- `target_occurrence_set_panel` gained a `show_map: bool = True` parameter; called with `show_map=False` in species mode to suppress its previously separate rectangle-selection map.
- Phase 2 caption updated from "map below" to "map above".

**Remove "Raw GBIF records are kept..." sidebar caption**
- Removed the four-value sidebar caption (fetch / map / candidate / SDM record counts) from the main species workflow.

Features preserved:
- Genus mode still uses `target_occurrence_set_panel` with its own map (`show_map=True`, default).
- All rectangle-based survey area selection logic (include / exclude / clear), Phase 2 radio buttons, and metrics unchanged.
- All SDM, VIF, route planner, and download features preserved.

## 2026-06-04 - Claude (claude-sonnet-4-6) — SURVEY_PLANNING_POLICY: transparency, consolidated SDM map, label clarity, country filter

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:

**1. Show all analysis points (no cap)**
- Main candidate map now uses `occ_candidate_input` (all analysis points, uncapped) instead of `occ_map_display` (capped display subset).
- SDM setup map shows all `occ_sdm_train` final presence points (blue) without cap. Only unused excluded QC records are capped at 500.

**2. Clarify record-count labels**
- SDM preprocessing metrics: "Raw records" → "Fetched records (SDM source)"; "After QC exclusion" → "After SDM QC exclusion"; "After exact dedup" → "After deduplication"; "After thinning" → "After spatial thinning"; "Final SDM presence pts" → "Final SDM presence points". Delta values added showing reduction at each stage.
- Target-occurrence panel metric: "Raw records" → "Active survey-area records"; "Active target records" → "Selected for candidates".
- Performance summary: "Raw valid records" → "GBIF fetched records". Genus: "Raw records" → "Active survey-area records".

**3. Consolidated SDM setup map**
- Added `make_sdm_setup_map(occ_sdm_final, excluded_raw, extent_geom, area_mode)` function that combines: SDM prediction extent outline (orange), included analysis points (blue, all shown), excluded QC points (red), and rectangle draw tool for bulk SDM QC exclusion.
- Replaced three separate SDM maps (`sdm_rectangle_qc_panel`, `make_sdm_extent_preview_map`, `make_exclusion_review_map` inside SDM expander) with this single map.
- Reorganized SDM expander: preprocessing controls → extent controls → consolidated setup map → environmental variables → run.
- Removed duplicate "SDM bias-reduction preprocessing" section left over from previous edits.

**4. Remove "Advanced country filter" expander**
- Species and genus GBIF fetch: removed `with st.sidebar.expander("Advanced country filter")` and custom_country text_input.
- Kept only the compact country-code dropdown selectbox.

Features preserved:
- Step 2 survey area for observed candidates only; independent SDM QC and extent; representative GBIF fetch; SDM bias reduction; VIF stepwise threshold 10; block/checkerboard/random/jackknife validation; weighted observed + model scoring; downloads and selected survey site lists.


## 2026-06-04 - Codex (OpenAI) - Apply lightweight survey-planning policy UI

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:
- Read `AGENTS.md`, `CHANGELOG_AI.md`, and `SURVEY_PLANNING_POLICY.md`, then used the latest GitHub `main` as the baseline.
- Removed the main species/genus `Survey planning mode` selectors and fixed the default working policy to species fetch 1,000, genus fetch 3,000, map 500, candidate input 800, SDM 300, and SSDM 150 per species.
- Restored compact country-code filters (`JP`, `US`, etc.) for species and genus workflows, with optional custom two-letter code fields under Advanced.
- Replaced SDM/SSDM environmental preset selectors with editable multiselects prefilled by the balanced ecology variables.
- Made VIF stepwise with threshold 10 the default SDM/SSDM variable-selection behavior while keeping threshold/alternative strategies inside Advanced.
- Restored the single-species validation method selector to the original partition methods, defaulting to `block`; k-fold and checkerboard inputs now appear only when relevant.

Features preserved:
- Step 2 remains observed-data candidate/hotspot selection only.
- Optional SDM retains independent SDM-only QC, bias reduction, prediction extent, predict map, VIF diagnostics, and weighted model-support scoring.
- Optional SSDM remains manual-run only and keeps observed richness separate from predicted stacked richness support.

Verification:
- `python -m py_compile gbif_fieldmap_builder_app.py`
- `git diff --check`

## 2026-06-04 - Codex (OpenAI) - Separate Step 2 observed candidates from optional SDM QC/extent

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:
- Read `AGENTS.md`, the latest `SURVEY_PLANNING_POLICY.md`, and `CHANGELOG_AI.md`; fast-forwarded to the latest GitHub `main` (`fc0bc00`) before editing.
- Removed coordinate QC from the species Step 2 workflow so Step 2 now selects only the observed-data survey area for candidate generation.
- Changed species SDM to start independently from fetched occurrence records, then apply SDM-only rectangle QC, SDM-only bias-reduction preprocessing, and SDM-only prediction extent generation inside `Optional: Build SDM`.
- Prevented the Step 2 survey-area selection from automatically becoming the SDM training set or prediction extent.
- Removed genus Step 2 coordinate QC and kept genus Step 2 as observed richness hotspot area selection only.
- Changed optional SSDM fitting to start from fetched genus records instead of the Step 2 observed-richness target set.

Features preserved:
- Count-first representative GBIF fetching, full-name country selector, observed-data candidates, optional SDM/SSDM, weighted model support, prediction maps, VIF/variable diagnostics, and downloads remain available.
- Step 2 survey-area rectangle remains available for observed-data candidate/hotspot generation.
- SDM rectangle QC remains available, but now inside the optional SDM workflow.

Known risks / TODO:
- The older rectangle QC helper remains in code for compatibility but is no longer called from Step 2.
- SSDM has been decoupled from Step 2 selection, but a fuller SSDM-specific rectangle QC UI can still be added later if needed.

## 2026-06-04 - Codex (OpenAI) - Count-first representative GBIF fetching and rectangle QC workflow

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:
- Read `AGENTS.md`, `SURVEY_PLANNING_POLICY.md`, and `CHANGELOG_AI.md`, then used the latest GitHub `main` as the baseline.
- Changed GBIF species and genus downloads to a count-first workflow: taxon match plus `limit=0` count is shown before occurrence download.
- Made survey-planning mode control GBIF fetch caps as well as downstream working subsets: species Fast defaults to 1,000 records, species Detailed to 3,000, genus Fast to 3,000, and genus Detailed to 10,000.
- Added representative GBIF retrieval when totals exceed the cap by sampling evenly spaced result offsets instead of simply taking the first N records, followed by GBIF ID / coordinate deduplication and spatial capping.
- Replaced sidebar country-code entry with a full-name country selector shared by species and genus workflows.
- Added rectangle-based coordinate QC to the main Step 2 workflow and genus workflow; QC exclusions are red on the QC map and removed from downstream candidate generation, SDM/SSDM, extents, and survey-site lists.
- Kept the survey-area rectangle separate from QC rectangles: the survey-area rectangle selects the active target occurrence set, while SDM/SSDM prediction extents are still generated inside the optional model expanders from that active set.
- Simplified environmental variable choices to Recommended variable set or Custom variables; Custom exposes an automatic high-correlation removal checkbox while VIF and detailed settings remain under Advanced.
- Simplified species SDM validation to Recommended spatial validation, Fast random split, or Advanced; k-fold, checkerboard size, and max predict-map pixels are no longer main-screen controls.

Features preserved:
- Raw GBIF records are kept for summary/download while maps, candidates, SDM, and SSDM use representative working subsets by default.
- GBIF taxon matching, paginated occurrence requests, CSV upload, target occurrence set selection, occurrence candidates, genus richness hotspots, optional SDM/SSDM, weighted scoring, NoData cleaning, prediction maps, downloads, and route/site list remain available.
- VIF stepwise and spatial partition diagnostics remain available under advanced settings.

Known risks / TODO:
- GBIF representative retrieval reduces ordering bias but still depends on GBIF result ordering within sampled pages; future validation should compare candidate rankings against all-record downloads.
- SSDM validation is still limited to the existing random-holdout/training-only implementation; full spatial SSDM partitions remain a future enhancement.

## 2026-06-04 - Codex (OpenAI) - Survey-planning representative subset defaults

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:
- Based the edit on the latest GitHub `main` after fast-forwarding to `9193bb4`.
- Read `AGENTS.md`, `SURVEY_PLANNING_POLICY.md`, and `CHANGELOG_AI.md` before editing.
- Added explicit survey-planning mode controls for species and genus workflows: Fast survey planning (recommended), Detailed analysis, and Custom.
- Set Fast survey planning defaults to spatially representative working subsets: map display about 500 records, candidate input about 800 records, SDM presence about 300 records, and SSDM about 150 per species.
- Kept Detailed analysis higher but still bounded: map about 1000, candidate input about 1500, SDM about 500, and SSDM about 300 per species.
- Custom mode exposes manual caps without making all-record map/model/candidate processing the default.
- Updated `prepare_large_dataset_inputs` so candidate generation and SDM presence inputs are capped spatially representative subsets by default, not only when large dataset mode is active.
- Updated genus occurrence-richness hotspot generation to use a spatially representative working subset while preserving raw/active records for summaries.

Features preserved:
- Raw GBIF records remain preserved for transparency, summaries, and downloads.
- Observed-data candidates remain available before SDM/SSDM.
- SDM/SSDM remain optional model support for prioritization, not prerequisites.
- Existing GBIF download, CSV upload, target occurrence selection, SDM, SSDM, variable selection, route/site list, and downloads remain available.

Known risks / TODO:
- Representative subset defaults intentionally change candidate rankings compared with all-record processing; this matches the survey-planning policy and should be evaluated in planned subset-vs-all-record validation.

## 2026-06-03 - Claude (claude-sonnet-4-6) — Simplify Step 2 / Sampling design UI; move SDM extent inside expander

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:

**Step 2 heading renamed**
- `"2 — Prepare records"` → `"2 — Prepare records and choose survey range"`.

**Coordinate QC expander relabeled**
- `"Optional: Coordinate quality check"` → `"Advanced: coordinate QC — click points to exclude suspicious records"` (shows count when points are excluded). Functionally unchanged; click-to-exclude, rectangle draw, clear button, and red excluded points all preserved.

**Sidebar sampling design simplified**
- Always-visible controls reduced to two: **Survey range radius (m)** and **Candidate grouping scale (m)** (renamed from "DBSCAN cluster distance").
- All technical controls moved into a collapsed **"Advanced sampling settings"** expander: spatial thinning, large dataset mode, max map points, exact dedup, grid thinning, candidate center method, min records per cluster.
- "Occurrence record-count weight" renamed to **"Record-density bonus"** and moved into advanced settings.
- "Occurrence image popups" moved into advanced settings.
- Candidate scoring (Observed-data weight + SDM model weight) remains always-visible.

**SDM prediction extent moved inside "Optional: Build SDM" expander**
- Area mode, buffer/hull/bounding-box controls, hard exclusion radius, and the extent preview map are now inside the "Build SDM and predict map" expander.
- Users see occurrence-based survey candidates without any SDM extent section appearing on the page.
- Variables (`area_mode`, `buffer_km`, `rectangle_margin_km`, `exclusion_buffer_km`, `excluded_occ`, `extent_geom`) remain accessible to the `if run_sdm:` block via Python scope (Streamlit `with` blocks do not create new Python scope).

Features preserved:
- Target occurrence set selection, coordinate QC, large dataset caps, SDM/SSDM, VIF, variable presets, weighted scoring, route planner, downloads all unchanged.

## 2026-06-03 - Claude (claude-sonnet-4-6) — Weighted model support: fix model_support_score refresh bug + UI status banners

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:

**Bug fix: model_support_score not updated after SDM runs (species mode)**
- After `predict_suitability` populates `sdm_suitability`, code now explicitly writes `model_support_score = sdm_suitability.clip(0,1)` before the final `add_priority_rank` call. Previously the column stayed at 0.0 from the first call.

**Improved `add_priority_rank` fallback logic**
- When `model_support_score = 0.0` but `sdm_suitability` is non-NaN (meaning SDM ran after the score was initialised), `sdm_suitability` is used instead. Docstring added.

**Model support status banners**
- Species mode: info/success banner in "3 — Occurrence-based survey site suggestions" showing weights and SDM status.
- Genus mode: info/success banner in "4 — Selected hotspot sites" showing weights and SSDM status.

Features preserved:
- Observed-data candidates available without SDM/SSDM. All scoring columns preserved.


## 2026-06-03 - Claude (claude-sonnet-4-6) — Simplify environmental variable selection with presets; add Balanced ecology preset

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:

**New constants**
- `BALANCED_ECOLOGY_PRESET = ["bio1", "bio4", "bio12", "bio15", "bio14", "elevation"]` — 6 interpretable variables: temperature level (bio1), temperature seasonality (bio4), annual precipitation (bio12), precipitation seasonality (bio15), driest month precipitation / dryness (bio14), and elevation (topography).
- `ENV_VARIABLE_PRESETS = ["Balanced ecology preset", "Climate only preset", "Topography only preset", "Custom variables"]` — list of preset options.

**SDM variable selection UI (species mode, inside "Optional: Build SDM" expander)**
- Replaced raw topography/climate multiselects + variable-strategy selectbox with a clean **"Environmental variable preset"** selectbox as the main UI.
- Default preset is **"Balanced ecology preset"** — users get a sensible 6-variable set without needing to know bio variable numbers.
- "Climate only preset" selects all 19 WorldClim BIO variables with a caption recommending variable selection for large sets.
- "Topography only preset" selects elevation, slope, roughness.
- "Custom variables" shows the manual multiselects (topography + climate).
- Advanced variable selection (strategy, VIF/correlation threshold, custom final selection) moved into a **collapsed "Advanced variable selection" expander** — not required and not shown by default.

**SSDM variable selection UI (genus mode, inside SSDM expander)**
- Same preset-based redesign applied symmetrically to SSDM.
- Default is "Balanced ecology preset".
- Advanced variable selection (shared VIF strategy, thresholds) collapsed inside "Advanced variable selection" expander.
- All existing variable-selection strategies (No VIF, Correlation filter, VIF stepwise, Advanced custom) preserved in the advanced expander.

Features preserved:
- All variable-selection strategies (No VIF, Correlation filter, VIF stepwise, Ecological preset, Advanced custom) preserved.
- VIF stepwise is not the default (No VIF is default inside the expander); preset selection is the primary interface.
- Single-species SDM, SSDM, occurrence candidates, and route planner unchanged.

Known risks / TODO:
- Sessions that previously had custom variable selections will default to Balanced ecology preset on next load; users should re-select Custom if needed.

## 2026-06-03 - Codex (OpenAI) - Issue #10 optional model-support scoring and variable-selection strategies

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:
- Made the shared species/genus workflow explicit: observed occurrence data generate the base survey candidates, while SDM/SSDM adds optional model support for prioritization.
- Added candidate scoring controls for species and genus modes: observed-data weight and SDM/SSDM model weight, defaulting to 0.7 and 0.3.
- Standardized output scoring columns: `occurrence_support_score`, `model_support_score`, `observed_weight`, `model_weight`, `priority_score`, and `score_explanation`.
- Updated candidate ranking so `priority_score = observed_weight * occurrence_support_score + model_weight * model_support_score + optional bonuses`.
- Species mode uses observed occurrence support plus optional SDM suitability-derived model support.
- Genus mode uses observed richness/record support plus optional SSDM predicted richness-derived model support; observed richness hotspots can be re-ranked with SSDM support after SSDM runs.
- Replaced default-on VIF controls with variable-selection strategy options: No VIF, Correlation filter, VIF stepwise, Ecological preset / representative climate set, and Advanced custom selection.
- Added ecological preset / correlation-cluster representative variable selection and richer diagnostics fields including `final_status`, `reason`, `protected_by_group`, `fallback_kept`, and `vif_stage`.
- Kept raster NoData/fill-value cleaning safeguards before SDM and SSDM variable selection/modeling.

Features preserved:
- Observed occurrence candidates remain available without SDM/SSDM, and SDM/SSDM never replaces or becomes required for candidate generation.

## 2026-06-03 - Codex (OpenAI) - Issue #10 target occurrence rectangle selection

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:
- Added Step 2 target occurrence set controls: use all cleaned records, use only records inside a drawn rectangle, or exclude records inside a drawn rectangle.
- Clarified that the rectangle is not the final SDM/SSDM extent; it only selects which occurrence records are used to derive candidates and prediction extents.
- Added shared target-selection map/helper and separate active target sets for species mode and genus mode.
- Derived single-species occurrence candidates, SDM train inputs, and buffer/convex-hull/bounding-box prediction extents from the selected target occurrence set.
- Derived genus observed richness grids/hotspots and optional SSDM inputs/extents from the selected target occurrence set.
- Added count metrics for raw records, records inside rectangle, records excluded by rectangle, active target records, candidate inputs, and SDM/SSDM inputs.

Features preserved:
- Coordinate red-point exclusion, large dataset caps, GBIF downloads, single-species SDM/VIF/predict maps, genus richness, optional SSDM, route planning, and downloads remain available.

## 2026-06-03 - Codex (OpenAI) - GBIF retry handling for connection resets

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:
- Added a shared GBIF JSON request helper with retry/backoff for temporary HTTP 429/5xx, timeout, and connection-reset failures.
- Routed species and genus GBIF match/search/occurrence requests through the retry helper.
- Prevented single-species GBIF downloads from crashing the app when a request fails, matching the safer genus-mode behavior.
- Improved user-facing GBIF failure messages with guidance to retry, lower the record cap, or clear filters.

Features preserved:
- GBIF paginated downloads, large dataset caps, genus richness/SSDM, single-species SDM/VIF/predict maps, exclusion, route planning, and downloads remain available.

## 2026-06-03 - Codex (OpenAI) - Issue #10 large GBIF dataset auto-capping

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:
- Automatically enables effective large dataset handling when more than 1,000 valid occurrence records are loaded, even if the sidebar checkbox was left off.
- Keeps `occ_raw` as the full coordinate-cleaned record set, while using capped/thinned `occ_map_display`, `occ_candidate_input`, and `occ_sdm_train` datasets for interactive maps, candidate clustering, and SDM.
- Caps interactive occurrence maps to at most 1,000 points in large dataset mode and disables occurrence image popups by default when raw valid records exceed 500.
- Uses spatially balanced capping so candidate generation is limited to about 1,000 records and SDM training is limited to about 500 records in large dataset mode.
- Shows a large dataset summary and performance metrics so users can see which record set is used for raw data, map display, candidate generation, and SDM.
- Updated optional SDM presence caps so raw GBIF records are not accidentally forced into SDM when large datasets would freeze the app.

Features preserved:
- Coordinate exclusion, occurrence candidate ranges, SDM/VIF/spatial partition diagnostics, predict maps, SSDM workflows, route planning, and HTML downloads remain available.

## 2026-06-03 - Codex (OpenAI) - Issue #10 VIF NoData cleaning and SSDM UI consistency

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:
- Based the change on the latest GitHub main state (`bd96628`, Issue #4c merged).
- Added shared raster/environment cleaning helpers for SDM and SSDM workflows.
- Converted raster `src.nodata`, non-finite values, and extreme fill/sentinel values below `-1e20` or above `1e20` to NaN.
- Applied environment-table cleaning before single-species SDM VIF/model fitting and before SSDM shared VIF/model fitting.
- Dropped rows with invalid environmental values and reported drop counts in SDM VIF tables and SSDM VIF diagnostics / model summaries.
- Added guards so VIF stops with a clear error if extreme raster sentinel values remain after cleaning.
- Updated SSDM bias-reduction UI to default to `Auto (Recommended)` and moved detailed thinning controls under `Advanced / Custom`.
- Made SSDM bias-reduction wording parallel with the species SDM bias-reduction preprocessing panel.

Features preserved:
- Single species SDM, SSDM, shared SSDM VIF, occurrence richness, large dataset controls, spatial partition diagnostics, predict maps, route planner, and downloads remain available.

Known risks / TODO:
- Rows outside valid raster coverage are now dropped before VIF/SDM. Very sparse datasets may need broader extents, lower-resolution rasters, or fewer selected variables.

## 2026-06-03 - Claude (claude-sonnet-4-6) — Issue #4 follow-up: SDM bias-reduction preprocessing + SSDM per-species thinning

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:

**SDM bias-reduction preprocessing (species mode)**
- Added a "SDM bias-reduction preprocessing" section at the top of the "Optional: Build SDM" expander with four controls: exact coordinate deduplication (default on), grid thinning in degrees (default 0.05°), distance thinning / spThin-like (default 1 000 m, 0 = off), maximum SDM presence points cap (default 0 = no cap).
- Caption explains the purpose: GBIF records cluster near roads/cities/trails; spatial thinning reduces sampling bias before SDM fitting. Explicitly notes these settings apply only to SDM training and do not affect occurrence-based survey candidates.
- After the expander, a new `occ_for_sdm` pipeline applies these settings to `occ_after_exclusion` (QC-cleaned but not otherwise pre-processed), keeping the SDM preprocessing pipeline independent of the occurrence-candidate clustering pipeline.
- Five-column preprocessing metrics panel displayed (always visible, outside the expander): Raw records → After QC exclusion → After exact dedup → After thinning → Final SDM presence points.
- SDM training (`build_presence_background`, `build_predict_map`, `make_sdm_exploration_candidates`) now use `occ_for_sdm` instead of `occ_sdm_train`.
- `current_sdm_occurrence_row_ids` now tracks `occ_for_sdm` row IDs; SDM cache invalidation triggers when preprocessing settings or QC exclusions change.
- `occ_sdm_train` (sidebar-preprocessed set) remains as the basis for occurrence-candidate clustering and SDM extent preview — unchanged behavior for occurrence candidates.

**SSDM per-species bias-reduction preprocessing (genus mode)**
- Added `per_species_grid_thin_deg` and `per_species_distance_thin_m` parameters to `fit_stacked_species_sdms`.
- Per-species preprocessing order: exact coordinate dedup → grid thinning → distance thinning → presence cap. Applied before each species SDM fit.
- Exposed as UI controls in the SSDM expander: "Per-species grid thinning (degrees, 0 = off)" (default 0.05°) and "Per-species distance thinning (m, 0 = off)" (default 0).

Features preserved:
- Occurrence-based survey candidates and richness hotspots unchanged and always available before SDM/SSDM.
- Single-species SDM VIF, partition, predict map, exploration candidates, route planner unchanged.
- Genus richness grid, SSDM shared VIF, SSDM partition, downloads unchanged.

## 2026-06-03 - Claude (claude-sonnet-4-6) — Issue #4 follow-up: fix widget key conflict, non-blocking QC, symmetric headings

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:

**Fix `restore_excluded_row_ids` widget key conflict**
- Removed `restore_excluded_row_ids` from `init_session_state` defaults and from `clear_loaded_data`.
- Removed the `st.multiselect("Excluded row IDs", ..., key="restore_excluded_row_ids")` widget and its associated "Recover selected excluded rows" button from `coordinate_exclusion_panel`. This eliminates the Streamlit widget-state conflict reported in the issue.
- Click-to-restore still works: clicking an already-excluded point on the QC map toggles it back to included.

**Non-blocking, collapsed QC panel**
- `coordinate_exclusion_panel` expander changed from `expanded=True` to `expanded=False`. The QC section is now clearly optional and does not block the occurrence candidate section.
- Expander label shows the current excluded count: "Optional: Coordinate quality check (N excluded)" when exclusions are active.
- Added a large-dataset hint: when `occ_raw > 500` records, a note recommends using rectangle drawing for bulk exclusion.

**Symmetric numbered section headings (species and genus modes)**
- Species mode: `2 — Prepare records` → `3 — Occurrence-based survey site suggestions` → `4 — Selected survey sites` (route planner) → `Optional: Build SDM`.
- Genus mode: `2 — Prepare records and species summary` → `3 — Occurrence-based richness hotspots` → `4 — Selected hotspot sites` → `Optional: Run SSDM`.
- Both modes now follow a parallel 1–4 + optional structure as requested.

**Genus panel restructure**
- The previous top-level `st.subheader("Genus diversity — occurrence richness hotspots")` (before data-load check) was replaced with numbered section subheaders placed after data loads, keeping the same data-guard logic.
- Step 4 "Selected hotspot sites" now uses the hotspot candidates table (previously "Richness hotspot candidates") with the same data and downloads.

Features preserved:
- All exclusion logic (click, rectangle, clear), SDM/SSDM, VIF, route planner, downloads unchanged.

## 2026-06-03 - Claude (claude-sonnet-4-6) — Issue #2 follow-up: shared SSDM VIF, BIO protection, VIF diagnostics, partition settings

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:

**Shared SSDM VIF (run once, not per species)**
- Removed per-species VIF from `fit_stacked_species_sdms`. VIF is now run **once** on a pooled sample (up to 1,000 genus occurrence records + shared background grid points) before the species loop.
- The same retained variable set (`kept_vars`) is used for every per-species model, preventing inconsistent variable sets and the BIO-variable disappearance bug reported by the user.
- Added `ssdm_variable_diagnostics(env_df, variables)` — computes diagnostic table before VIF: variable, group (climate/topography/other), min, max, sd, unique_values, missing_fraction, max_abs_corr, VIF, status.
- Added `run_ssdm_shared_vif(env_df, variables, vif_threshold)` — wraps `vif_step` with BIO-variable protection: if VIF removes all `bio1`–`bio19` variables, the least-correlated BIO variable is automatically restored and marked `fallback-kept (BIO protection)`.

**SSDM partition settings exposed**
- `fit_stacked_species_sdms` now accepts `ssdm_partition_method` (default `"random holdout"`) and `ssdm_test_split` (default `0.20`). Passes `holdout_test_size` through to `fit_sdm`.
- `fit_sdm` gains `holdout_test_size=0.25` parameter (used by random holdout); single-species SDM callers are unchanged and keep the existing 0.25 default.
- UI: added `SSDM partition method` selectbox (`random holdout` / `none (training only)`) and `SSDM holdout test split proportion` number input. `none` skips validation for fastest exploratory runs.
- UI caption clearly states: "Spatial block/checkerboard partitions are available in single-species SDM but not yet implemented for SSDM."

**VIF diagnostics table in UI**
- After SSDM runs with VIF enabled, displays `Shared VIF diagnostics` table showing per-variable stats, max_abs_corr, VIF, and final status (kept/removed/fallback-kept).
- If BIO fallback was triggered, a `st.warning` is shown explaining which variable was restored.
- Added `ssdm_vif_diagnostics.csv` download button.

**UI label update**
- Checkbox label changed from "Apply VIF stepwise filtering for each species SDM" → "Apply shared VIF for SSDM (run once on pooled data)".
- Updated caption to explain shared VIF behavior and BIO protection.

**Single-species SDM unchanged**
- VIF, spatial partition, and all single-species SDM workflow are unmodified.

Features preserved:
- Genus occurrence richness, hotspots, SSDM maps, SSDM downloads, large-dataset mode, exclusion/QC, route planner unchanged.

## 2026-06-03 - Claude (claude-sonnet-4-6) — Issue #4: Unify species/genus workflows; make SDM/SSDM optional

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:
- **Mode switching fix**: Added `_last_analysis_mode` to session state. On every mode switch between "Single species survey planning" and "Genus diversity / SSDM", widget-collision-prone state (map-click signatures, selected site IDs, draw signatures, QC rectangle IDs) is reset. This prevents Streamlit session-state inconsistencies when users freely alternate between modes.
- **Species mode — occurrence candidates before SDM**: Added "Occurrence-supported survey candidates" section immediately after DBSCAN clustering, before the SDM section. Shows candidate table with priority scores, plus CSV/KML download buttons. Users can plan surveys from raw occurrence data without running SDM.
- **Species mode — SDM is optional**: Changed SDM expander from `expanded=True` to `expanded=False` and relabeled from "Build SDM and predict map" to "Optional: Build SDM and predict map". Relabeled the subheader to "SDM (optional enhancement)". SDM exploration candidates and suitability scoring are still fully available when the user chooses to run SDM.
- **Genus mode — hotspots before SSDM**: Updated heading and caption to emphasize that occurrence richness hotspots are the primary output (no modeling required). The optional SSDM expander was already collapsed; caption now explicitly points users to it as an enhancement-only section.
- **Large datasets**: Occurrence candidates are always computed from spatially thinned clusters regardless of dataset size, consistent with existing large-dataset-mode behavior.

Features preserved:
- All existing species SDM, VIF, spatial partition, predict map, exclusion/QC, and route planner features unchanged.
- All genus richness grid, hotspot, SSDM, and download features unchanged.

## 2026-06-03 - Claude (Anthropic) — Issue #2 follow-up: SSDM eligibility label and map legends

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:
- Renamed sidebar label "Minimum records flag for future SSDM" → "Minimum records for SSDM eligibility". Added help text: species below this threshold can still appear in the occurrence-based richness map but will be skipped in SSDM.
- Added add_richness_legend() helper: yellow-green gradient legend for occurrence richness maps. Title is metric-aware ("Observed species richness", "Occurrence record count", "Species meeting min. records threshold"). Note clarifies this is based on GBIF records, not modeled suitability.
- Added add_ssdm_richness_legend() helper: blue-red gradient legend for SSDM maps. Continuous variant shows "Predicted richness (suitability sum)" with note that values are not integer species counts. Binary variant shows "Predicted species richness" with note that values are the count of species above the suitability threshold.
- make_richness_map() now calls add_richness_legend() after drawing the grid.
- make_ssdm_map() now calls add_ssdm_richness_legend() using the actual min/max values from the grid, dispatching on value_col to choose the correct legend variant.

Features preserved:
- All genus/SSDM features, single-species SDM, VIF, spatial partition, predict map, route planner, downloads unchanged.

## 2026-06-03 - Codex (OpenAI) - Add VIF filtering to optional SSDM

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:
- Added per-species VIF stepwise filtering to the optional SSDM workflow.
- Added SSDM UI controls for applying VIF filtering and setting the VIF threshold.
- Each species SDM now fits using its own VIF-filtered variable set when enabled.
- Added VIF status, threshold, kept variables, and removed variables to ssdm_species_model_summary.csv.

Features preserved:
- Genus occurrence richness, optional SSDM maps, large dataset controls, single species SDM, VIF, spatial partition diagnostics, predict map, route planner, and downloads remain available.

Known risks / TODO:
- Different species may keep different environmental variables after VIF filtering, which is expected for per-species SDMs but should be reviewed in the summary CSV.

## 2026-06-03 - Codex (OpenAI) - Issue #2 follow-up: optional stacked species SDM

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:
- Added an explicit "Optional SSDM: stack species SDMs" section in Genus diversity / SSDM mode.
- SSDM does not run automatically; it runs only when the user clicks Run SSDM.
- Added per-species SDM fitting for species with enough occurrence records.
- Added a shared environmental prediction grid for all modeled species.
- Added continuous SSDM richness as the sum of predicted suitability values.
- Added binary SSDM richness as the sum of species predictions above the user-defined suitability threshold.
- Added continuous and binary SSDM richness maps.
- Added SSDM outputs: ssdm_species_model_summary.csv, ssdm_richness_grid.csv, and ssdm_hotspot_candidates.csv.
- Added safeguards for max species to model, max presence points per species, shared background cells, progress per species, and skipping species with too few records.
- Clarified that occurrence richness is observed richness while SSDM richness is predicted stacked richness.

Features preserved:
- Occurrence richness grid, genus downloads, single species planning, coordinate exclusion, large dataset controls, SDM, VIF, spatial partition diagnostics, predict map, route planner, and downloads remain available.

Known risks / TODO:
- SSDM can still be computationally heavy when many species, variables, or prediction cells are selected; defaults are conservative and the run is manual.

## 2026-06-03 - Codex (OpenAI) - Issue #3 large dataset mode

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:
- Added Large dataset mode controls and a Max occurrence points shown on map setting.
- Separated the single-species data flow into occ_raw, occ_analysis, occ_map_display, and occ_sdm_train.
- Limited occurrence maps to a display subset while keeping raw records available for exclusion state and counts.
- Disabled occurrence image popups by default when raw valid records exceed 500.
- Added exact coordinate deduplication and optional grid thinning before clustering and SDM.
- Moved clustering, candidate generation, SDM extent, background generation, SDM fitting, predict map, and SDM-high exploration to the reduced occ_sdm_train set instead of all raw GBIF records.
- Added performance summary metrics for raw records, after exclusion, analysis records, SDM training records, map points, dedupe removals, and grid-thinning removals.

Features preserved:
- GBIF paginated occurrence download, CSV upload, map-click exclusion, candidate generation, ensemble SDM, VIF, spatial partition diagnostics, predict map, SDM-high candidates, route planner, and downloads remain available.

Known risks / TODO:
- In very large datasets, only displayed map points can be toggled by clicking; increase Max occurrence points shown on map to inspect more points.

## 2026-06-03 - Codex (OpenAI) - Fix genus GBIF backbone key selection

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:
- Fixed genus-mode GBIF taxon resolution to use exact GENUS matches from species/match when available.
- Fixed species/search fallback to use GBIF backbone nubKey instead of checklist-specific dataset keys.
- Prevented unrelated or unranked matches such as Campanulae fungi names from being used as genus occurrence taxon keys.
- Updated genus download status text to show the GBIF backbone taxonKey.

Features preserved:
- Genus occurrence richness outputs, single species planning, coordinate exclusion, SDM, VIF, spatial partition diagnostics, predict map, route planner, and downloads remain unchanged.

Known risks / TODO:
- Homonymous or highly ambiguous genus names may still need manual verification in future UI.

## 2026-06-03 - Codex (OpenAI) - Fix genus zero-record coordinate detection

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:
- Preserved the expected GBIF genus occurrence columns even when a genus download returns zero records.
- Added a genus-mode warning for zero coordinate records before latitude/longitude auto-detection runs.

Features preserved:
- Single species planning, CSV upload, coordinate exclusion, SDM, VIF, spatial partition diagnostics, predict map, route planner, and genus richness outputs remain unchanged.

Known risks / TODO:
- If GBIF returns zero records because of a strict country/year filter, the user still needs to loosen the filter or choose another genus.

## 2026-06-03 - Codex (OpenAI) - Issue #2 first step: genus occurrence richness mode

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:
- Added an Analysis mode selector with Single species survey planning and Genus diversity / SSDM.
- Added Genus diversity / SSDM mode with a separate genus input, country filter keys, GBIF paginated genus occurrence download, species grouping, species summary table, occurrence-based richness grid map, hotspot candidates, and CSV/HTML downloads.
- Kept full SSDM out of this step; the genus mode is occurrence-richness only until this map is stable.
- Added GBIF genus-name fallback matching through species search and catches genus download errors in the UI so a failed genus lookup does not crash the app.
- Used a lighter default genus fetch cap to reduce Streamlit Cloud blocking risk while preserving the 300-record GBIF pagination behavior.

Features preserved:
- Single species GBIF download, CSV upload, coordinate exclusion, clustering, SDM, VIF, spatial partition diagnostics, predict map, SDM-high candidates, route planner, and HTML download remain unchanged.

Known risks / TODO:
- Full SSDM is intentionally not implemented yet.
- Very large genus downloads can still take time because GBIF is paginated at 300 records per request.

## 2026-06-02 - Claude (Anthropic) — Issue #1 follow-up: simplify map layers and remove Priority table

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:
- Removed "Priority survey ranges" table from main UI bottom. Candidate site info still visible on the map and in the Survey site list section.
- Removed "Daily sampling route layers" checkbox from sidebar and daily-routes drawing from build_map(). App does not crash when route_plan is empty.
- Removed "Occurrence buffers" layer checkbox and drawing block from build_map().
- Renamed "Survey ranges" layer to "Candidate circles" (key: candidate_circles). One unified circle layer around candidate sites using survey_range_m as radius; color green for SDM-high, red for occurrence-supported, same as before.
- Removed "Occurrence display buffer radius" sidebar number_input (no longer needed); build_map() receives 0.0 for that param.
- Sidebar Layers now shows only: SDM predict map, Occurrences, Candidate circles.

Features preserved:
- SDM, VIF, spatial partition, predict map features all unchanged.
- Candidate site generation, priority scoring, occurrence exclusion all unchanged.
- build_map() signature unchanged (occurrence_buffer_m param kept, passed as 0.0).

## 2026-06-02 - Claude (Anthropic) — Issue #1 follow-up: hide day-split, unified selected list only

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:
- Removed "Optional: split selected sites by survey day" expander entirely from the UI. Day 1 / Day 2 / survey_day_lists UI is no longer shown.
- Main output is now a single unified "Selected survey sites" list only.
- Return value always uses survey_day=1 for selected sites so the map route layer still renders.
- Clear selected sites uses sl_reset_token (from previous commit) to fully clear the multiselect widget.
- Auto, Manual map click, and rectangle selection all unchanged.
- survey_day_lists session state key and helper functions (_make_day_gmaps_urls, make_survey_day_csv, make_survey_day_html) kept in code for future re-use but not exposed in UI.

Features preserved:
- All SDM/VIF/spatial partition/predict map features unchanged.
- All selection logic unchanged.

## 2026-06-02 - Claude (Anthropic) — Issue #1 follow-up: fix clear-selected and simplify day split

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:
- Fix 1: "Clear selected sites" now fully clears the Selected site IDs multiselect widget. Added sl_reset_token to session state; each Clear action increments the token, which changes the multiselect widget key (key=f"sl_manual_ids_{token}"), forcing Streamlit to create a fresh widget instance. Token also incremented in clear_loaded_data.
- Fix 2: Replaced the "Optional: split selected sites by survey day" expander contents with a st.data_editor approach. Selected sites are shown in an editable table with a survey_day SelectboxColumn (options: Day 1, Day 2, ..., Unassigned). User edits the survey_day column directly, then clicks "Apply day assignments" to write back to survey_day_lists. Removed all staging "Copy to Day X" buttons. Add day / Remove last day controls remain. Per-day Google Maps links and CSV/HTML downloads still shown after assignment.

Features preserved:
- All selection logic (auto, manual map click, rectangle Draw) unchanged.
- All SDM/VIF/spatial partition/predict map features unchanged.
- survey_day_lists session state and day-list downloads preserved.

## 2026-06-02 - Claude (Anthropic) — Issue #1 follow-up: Survey site list UI simplification

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:
- Renamed main heading from "Survey day site lists" to "Survey site list".
- Primary output is now "Selected survey sites" — a single unified list from sl_selected_site_ids.
- Auto / Manual / rectangle selection logic is unchanged.
- "Selected survey sites" table shown immediately after selection with per-site 📍 Google Maps links, "Open all in Google Maps", CSV download, HTML download, and "Clear selected sites" button.
- Day management (Add/Remove day, Copy to Day X, per-day tables and Google Maps links, day-list downloads) moved into a collapsed expander "Optional: split selected sites by survey day" — not shown unless the user opens it.
- Day assignment now uses "Copy to Day X" (copies from selected list; selected list is not cleared).
- Empty Day 1 / Day 2 lists are no longer visible as the main output.
- Return value: prefers day-list rows when any day has sites; otherwise returns selected sites with survey_day=1 so the map route layer still renders.
- Renamed "Clear staging" / "Staging selection" labels to "Clear selected sites" / "Selected site IDs".

Features preserved:
- All selection logic (auto, manual map click, rectangle Draw) unchanged.
- Day list state (survey_day_lists) preserved and still functional inside the expander.
- All SDM/VIF/spatial partition/predict map features unchanged.

## 2026-06-02 - Claude (Anthropic) — Fix StreamlitAPIException in coordinate_exclusion_panel

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:
- Removed two direct assignments to st.session_state.restore_excluded_row_ids that caused StreamlitAPIException: the pre-widget guard (checking stale IDs) and the post-recover-button reset. Both were unnecessary because the multiselect widget's options= already restricts valid choices, and st.rerun() after recovery naturally leaves the selection empty on the next render.
- Click exclusion behavior and rectangle exclusion behavior unchanged.

Features preserved:
- All existing features unchanged.

## 2026-06-02 - Claude (Anthropic) — Issue #1 follow-up: simplify QC rectangle workflow

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:
- Simplified QC rectangle workflow: drawing a rectangle now immediately excludes all occurrence points inside (no staging, no Exclude/Restore/Clear buttons).
- Removed "Exclude rectangle-selected", "Restore rectangle-selected", and "Clear rectangle selection" buttons from coordinate_exclusion_panel.
- Existing click-to-exclude/restore behavior is unchanged.
- "Clear excluded coordinates" button remains as the reset/undo fallback.
- Candidate site rectangle selection already added to staging immediately — no change needed.
- Excluded points remain red QC points and are not used for SDM, prediction extent, candidates, or survey day lists.

Features preserved:
- All existing SDM/VIF/spatial partition/predict map features.
- Existing point-click exclusion/restore behavior.
- Survey day site lists, HTML/CSV downloads.

## 2026-06-02 - Claude (Anthropic) — ROUTE_QC_PATCH_NOTES: rectangle selection fixes

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:
- Removed "Blue = included, red = excluded..." caption from coordinate_exclusion_panel (per patch note §1). Existing click-based exclusion/restore behavior unchanged.
- Added extract_drawn_features() helper: normalises all_drawings / last_active_drawing from streamlit-folium regardless of dict or list format.
- Added ids_inside_drawn_rectangles() helper: returns IDs inside any drawn Polygon/Rectangle feature.
- coordinate_exclusion_panel: added Draw plugin (add_draw=True), added "all_drawings" and "last_active_drawing" to returned_objects, added rectangle batch QC actions — Exclude / Restore / Clear rectangle-selected occurrence points. Red QC points remain visible and excluded from SDM/extent/candidates/routes.
- make_exclusion_review_map: restored add_draw parameter and fg_ex.add_to(fmap) so excluded red points are visible on the map.
- route_planner_panel manual mode: replaced ad-hoc dict-only feature parsing with extract_drawn_features() + ids_inside_drawn_rectangles(); added "last_active_drawing" to returned_objects so rectangle selection works even when all_drawings returns a list.

Features preserved:
- GBIF pagination, CSV upload, existing map-click exclusion/restore, red QC excluded points
- Ensemble SDM, VIF, spatial partition, predict map, SDM-high exploration candidates
- Survey day site lists, HTML/CSV downloads

Known risks / TODO:
- streamlit-folium < 0.13 may not return all_drawings; last_active_drawing fallback mitigates this.

## 2026-06-02 - Claude (Anthropic) — Issue #1: survey day site lists + rectangle selection

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:
- Implements Issue #1: Replace route splitting with manual day lists and box selection.
- Renamed section to "Survey day site lists".
- Added manual day-based site grouping: Day 1 / Day 2 / ... expanders with per-day site tables, remove-site controls, and Google Maps route buttons per day (split into Part 1 / Part 2 for >10 sites, i.e. >8 waypoints).
- Added staging area workflow: select sites → assign to survey day.
- Auto mode: filter by top_n, min_priority, min_suitability, site type → confirm to staging.
- Manual mode: map click toggle + rectangle Draw selection (folium.plugins.Draw) → adds sites inside drawn rectangle to staging.
- Added rectangle batch QC selection in coordinate_exclusion_panel: draw rectangle → Exclude / Restore / Clear rectangle points.
- Fixed bug: fg_ex (excluded red points) was not added to make_exclusion_review_map; now correctly added so red QC points are visible.
- Added Draw plugin to make_exclusion_review_map (add_draw=True) and make_route_selection_map (add_draw=True).
- New helpers: _make_day_gmaps_urls, make_survey_day_csv, make_survey_day_html, SURVEY_DAY_CSV_COLS.
- CSV columns: survey_day, order_within_day, site_id, candidate_type, priority_rank, priority_score, sdm_suitability, occurrence_support_score, n_occurrences, latitude, longitude, google_maps_url, access_note.
- HTML download: self-contained per-day tables with 📍 Google Maps links.
- New session state keys: survey_day_lists, survey_day_count, sl_selected_site_ids, sl_last_draw_sig, qc_rect_selected_ids, qc_last_draw_sig.
- clear_loaded_data resets all new day-list state.
- Preliminary straight-line day splitting (split_route_into_days) preserved in codebase but removed from main UI per Issue #1.

Features preserved:
- GBIF pagination, CSV upload, map-click occurrence exclusion, red QC excluded points
- Ensemble SDM, VIF stepwise filtering, spatial partition diagnostics
- Raster-style SDM predict map, SDM-high exploration candidates
- HTML/CSV downloads

Known risks / TODO:
- folium.plugins.Draw requires streamlit-folium >= 0.13 for all_drawings return; older versions silently ignore rectangle selection.
- Day list state persists across SDM rebuilds; stale site IDs are pruned but day numbers are not reset.

## 2026-06-02 - Claude (Anthropic) — survey site list

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:
- Renamed section to "Survey site list".
- Two modes: 1. Auto (top-ranked with top_n, min_priority, min_suit, type filters); 2. Manual (map-click toggle, order preserved).
- Site list table shows: site_id, priority_rank, priority_score, sdm_suitability, occurrence_support_score, n_occurrences, latitude, longitude, candidate_type, and a clickable "📍 Open" Google Maps link per site (via st.column_config.LinkColumn).
- Action buttons: "🗺️ Open all sites as Google Maps route", "⬇ Download shareable HTML", "📋 Copy shareable text list" (popover with st.code block).
- CSV download demoted to optional collapsed expander.
- Shareable HTML (make_shareable_html) generates a self-contained page with table and per-site Google Maps links.
- Shareable text list (_make_shareable_text) shown in st.code block with built-in copy button.
- Warning text added as caption below the subheader.
- Advanced day splitting expander retained (AGENTS.md compliance).

Features preserved:
- GBIF pagination, CSV upload, map-click occurrence exclusion, red QC excluded points
- Ensemble SDM, VIF, spatial partition, predict map, SDM-high exploration candidates
- Day-by-day route planner (Advanced expander)
- HTML/CSV downloads

Known risks / TODO:
- st.popover requires Streamlit >= 1.31; older deployments should upgrade.
- Google Maps route URL caps at 8 waypoints; longer lists drop excess silently.

## 2026-06-02 - Claude (Anthropic) — export redesign

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:
- Renamed route section to "Export survey sites for Google Maps".
- Added two export modes: 1. Auto (top-ranked sites with top_n, min_priority_score, min_sdm_suitability, include_occurrence_supported, include_sdm_high filters); 2. Manual (map-click toggle, preserved).
- Added make_export_csv() producing Google Maps / My Maps import-ready CSV with columns: name, latitude, longitude, priority_rank, priority_score, sdm_suitability, occurrence_support_score, n_occurrences, candidate_type, candidate_method, selection_reason, access_note, google_maps_url.
- Added make_export_kml() for KML download (Google Earth / My Maps compatible).
- Download buttons: google_maps_auto_sites.csv/.kml and google_maps_selected_sites.csv/.kml.
- "Open selected sites in Google Maps" link button.
- Warning text: export does not guarantee road/ferry/mountain/cliff/restricted-access feasibility.
- Moved travel mode, start/end location, day-splitting controls into collapsed "Advanced" expander (day-by-day planner fully preserved per AGENTS.md).
- Added _make_gmaps_url_with_end helper retained from previous iteration.
- EXPORT_CSV_COLS constant added at module level.

Features preserved:
- GBIF pagination
- CSV upload
- Map-click occurrence exclusion
- Red QC excluded points
- Ensemble SDM, VIF stepwise filtering, spatial partition diagnostics
- Raster-style SDM predict map
- SDM-high exploration candidates
- Day-by-day route planner (in Advanced expander)
- HTML/CSV downloads

Known risks / TODO:
- Google Maps URL waypoint cap is 8; routes with >9 sites silently drop excess waypoints.
- KML description is plain text; could be improved with HTML CDATA tables.

## 2026-06-02 - Claude (Anthropic)

Changed files:
- gbif_fieldmap_builder_app.py
- CHANGELOG_AI.md

Summary:
- Renamed "Survey route planner" → "Google Maps-based survey site planning".
- Added two planning modes: A. Auto (top-ranked candidates with priority/suitability thresholds) and B. Manual (existing map-click selection, fully preserved).
- Auto mode: top_n, min_priority_score, min_sdm_suitability filters; shows selected sites table and dropped sites; generates Google Maps verification route URL.
- Added optional end_location field and helper function `_make_gmaps_url_with_end`.
- Added warning text: Google Maps verification required; no road/ferry/mountain/cliff guarantee.
- Added "🗺️ Open verification route in Google Maps" button with disclaimer caption.
- Moved survey-days / max-sites-per-day / max-straight-line-distance into a collapsed "Advanced: preliminary day splitting" expander (feature preserved per AGENTS.md).
- Added google_maps_checked, accessible, access_mode, access_note columns to make_validation_template and to ordered DataFrame output.
- Route returns survey_day=1 when day-splitting is not used, so the map route layer still renders.

Features preserved:
- GBIF pagination
- CSV upload
- Map-click occurrence exclusion
- Red QC excluded points
- Ensemble SDM, VIF stepwise filtering, spatial partition diagnostics
- Raster-style SDM predict map
- SDM-high exploration candidates
- Day-by-day route planner (in Advanced expander)
- HTML/CSV downloads

Known risks / TODO:
- Google Maps URL waypoint cap is 8; routes with >9 sites silently drop lower-priority waypoints.
- end_location with start_location shifts waypoint list by one; verify edge cases with 1-2 sites.

## Template

```md
## YYYY-MM-DD - Agent name

Changed files:
- path/to/file.py

Summary:
- Briefly describe what changed.

Features preserved:
- GBIF pagination
- CSV upload
- map-click occurrence exclusion
- red QC excluded points
- SDM
- VIF stepwise filtering
- spatial partition diagnostics
- predict map
- SDM-high exploration candidates
- route planner
- downloads

Known risks / TODO:
- List anything that still needs checking.
```

## 2026-06-02 - ChatGPT

Changed files:
- AGENTS.md
- CHANGELOG_AI.md

Summary:
- Added AI collaboration rules and a shared changelog format.
- Defined core features that future AI edits must preserve.
- Added routing caution that straight-line route planning does not account for roads, ferries, mountains, cliffs, restricted access, or island barriers.
- Added requirement that every AI agent update this changelog after code changes.

Features preserved:
- No application code changed.

Known risks / TODO:
- Add GitHub Actions syntax check workflow.
- Improve route planning so Google Maps verification and accessible-site selection are explicit.
