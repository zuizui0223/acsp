# ACSP paper packages

## Current submission-facing robust candidate-patch package

The current authoritative ACSP paper object is the **non-ranked robust candidate-patch set** defined by `VALIDATED_PRODUCT_CONTRACT.md` and `acsp/validated_robust.py`.

Use these files for the next scientific review and journal-formatting pass:

- `MANUSCRIPT_ROBUST_PATCH_DRAFT.md` — submission-facing manuscript aligned to the frozen 2.5% leave-one-prototype-out support tier, float32 support worlds, 1 km same-area complete-link aggregation, and the 96-pair / 480-fold untouched confirmation;
- `generated/table_1_robust_patch_confirmation.csv` — primary Japanese confirmation bound to authoritative implementation constants;
- `generated/table_2_robust_patch_transfer_boundary.csv` — reserved and fresh country-framed failures plus the provider-aborted observability boundary;
- `validate_submission_alignment.py` — network-free cross-check against code constants and frozen result JSONs;
- `SUBMISSION_READINESS.md` — completed scientific boundary and remaining editorial tasks.

Run the alignment guard from the repository root:

```bash
python paper/validate_submission_alignment.py
```

The current paper supports independently validated enrichment over same-size random candidate-patch sets in the fixed Japanese 12-region frame. It does not promote a global product, occupancy probability, exact-site prediction, ranking, routing, field-efficiency, or superiority over SDM/GRTS/biosurvey. *Campanula microdonta* remains development and freeze-regression evidence.

## Historical finite Top-5 package — preserved provenance

The files below are preserved provenance for the earlier finite Top-5 decision-policy paper and its matched-pool comparator analyses. They must not be silently presented as the definition of the current authoritative candidate-patch product, but they remain scientifically useful historical evidence and are not deleted or rewritten:

- `MANUSCRIPT_DRAFT.md`;
- `generated/table_1_retrospective_validation.csv`;
- `generated/table_s1_seed_sensitivity.csv`;
- `generated/table_s2_claim_matrix.csv`;
- `generated/table_s3_standard_baseline_comparison.csv`;
- `generated/table_s4_fitted_sdm_performance_contrast.csv`;
- `generated/table_s5_sdm_decision_differences.csv`;
- the legacy-output path in `build_paper_outputs.py`.

The remainder of this document records that historical finite-set package exactly as its publication boundary was closed.

---

# ACSP methods paper

This paper is scoped to the pre-*Campanula microdonta* cross-taxon validation program.

## Included evidence

1. **Primary retrospective confirmation:** predeclared taxon–region cohorts evaluated with spatial-block hold-out and same-pool random Top-5 controls.
2. **Leakage control:** candidates are reconstructed from training occurrences only; known-location and direct occurrence-distance evidence are excluded from the confirmatory comparison.
3. **Selection-value inference:** repeated folds are summarized within taxon–region pairs, with pair-level bootstrap, half-cohort, leave-one-pair-out, and sign-flip stability analyses.
4. **Frozen decision contract:** the publication-facing plant and animal policies are exported with deterministic manifests and explicit claim boundaries.
5. **Secondary component-attribution benchmark:** the same frozen taxon–region cohorts and ACSP policies were re-evaluated under a separately predeclared same-pool comparator protocol using regenerated GBIF occurrences, candidate surfaces, and spatial folds.
6. **Untouched fitted-SDM decision contrast:** 24 new taxon–region pairs were frozen before outcomes, then ACSP and a production-aligned fitted-SDM Top-5 rule were compared under identical training folds, candidate pools, budgets, and 10-km endpoints. Held-out recovery is reported as a secondary performance contrast; outcome-free set-overlap diagnostics establish whether the methods make the same field decision.
7. **Prospective generalization boundary:** a separately preregistered one-shot country-framed/global observability attempt is reported as provider-supply and evaluability evidence only. Its historical provider stage aborted before heldout years, so it contributes no effect estimate and does not change the validated Japanese product.

The primary paper asks whether an occurrence-conditioned selection policy adds recovery value beyond random selection from the identical generated candidate pool. The secondary standard comparator asks which broad selection component best explains that value. The fitted-SDM stage asks a different positioning question: **does a pointwise fitted-model ranking produce the same finite survey decision as ACSP when candidate availability and budget are held constant?**

The answer in the frozen benchmark is no. ACSP and fitted-SDM Top-5 ranking had essentially the same all-declared 10-km regional recovery, but among 101 SDM-evaluable folds their Top-5 sets shared only 1.93 candidates on average, mean Jaccard overlap was 0.264, and exact set agreement occurred once. The paper therefore does not claim that ACSP is universally better than SDMs. ACSP is positioned as a downstream finite-set decision layer that can also consume SDM output as an optional evidence channel.

## Excluded from this paper

The 2026 *C. microdonta* island application, area-balanced post-baseline update, gap-patch development, occurrence-patch connectivity, corridor/barrier experiments, and production-only integrated evidence are not part of the ACSP paper. The global observability terminal is included only to delimit generalization; it is not an additional validation cohort or a negative scientific result.

The island field application remains in `field_validation/` as development provenance. It is not read by the paper builder.

## Publication hard stop

The manuscript-development condition is satisfied by the validated Japanese product plus the frozen failed/conditional generalization and provider-supply/evaluability boundaries. Do not delay submission for a global positive, reopen the provider-aborted cohort, substitute failed candidates, or add a new scientific extension to this paper. Any successor observability experiment is a separate prospectively frozen study.

## Rebuild paper outputs

```bash
python -m pip install -e .
python paper/build_paper_outputs.py
```

The publication builder produces the retrospective, reviewed standard-comparator, and reviewed fitted-SDM decision-contrast outputs without requiring field GPS data or post-baseline island algorithms.

Primary and supplementary outputs:

- `table_1_retrospective_validation.csv`
- `table_2_evidence_availability.csv`
- `figure_1_primary_recovery.svg`
- `figure_2_evidence_boundary.svg`
- `table_s1_seed_sensitivity.csv`
- `table_s2_claim_matrix.csv`
- `table_s3_standard_baseline_comparison.csv`
- `table_s4_fitted_sdm_performance_contrast.csv`
- `table_s5_sdm_decision_differences.csv`
- `table_s6_global_observability_boundary.csv`
- `retrospective_stability.json`
- `validated_core_policies.json`
- `standard_baseline_results_manifest.json`
- `sdm_decision_results_manifest.json`
- `paper_output_manifest.json`

The builder also removes legacy *Campanula* tables from its output directory so an old local build cannot contaminate the submission package.

## Standard comparator stage

The comparator protocol was frozen in `validation/standard_baseline_protocol.json` before the two full workflow runs were inspected. It evaluates:

- frozen ACSP;
- local-evidence Top-k;
- geographic maximin coverage;
- environmental maximin coverage after robust scaling;
- declared geographic–environmental dual-space maximin coverage;
- reproducible random same-pool sets;
- a held-out greedy oracle used only as non-operational headroom.

The reviewed result snapshot is stored in `validation/standard_baseline_results_20260724/`. Both workflow artifacts passed checksum review. The absolute recall values in this secondary benchmark must not replace Table 1 because GBIF records, candidate surfaces, and spatial-block assignments were regenerated on 2026-07-24 rather than copied from the original confirmatory folds.

The secondary result supports focal-taxon local-habitat ranking as the principal observed selection signal. Animal ACSP was not detectably better than local-evidence-only Top-5, ACSP did not clearly exceed geographic maximin, and ACSP exceeded generic environmental maximin in both animal and pooled plant comparisons. These findings do not establish a general benefit of complementarity itself.

## Fitted-SDM decision contrast

The mathematical and interpretation boundary is documented in `docs/ACSP_SDM_POSITIONING.md`.

The untouched 24-pair cohort was frozen before candidate generation or outcome inspection. The fitted comparator reuses ACSP's production automatic-SDM family: logistic regression, random forest, ExtraTrees, and gradient boosting combined by equal-weight averaging. Each fold uses the same training information and the same candidate pool as ACSP, and both receive a Top-5 budget.

The reviewed result snapshot is stored in `validation/sdm_decision_results_20260808/`. The original pair run is `31236963484`; after rejecting implementation-only invalid aggregates, the final checksum-verified recovery run is `31238895064`. The outcome-free decision-difference run is `31239346408`.

Key result boundary:

- 24/24 pair artifacts verified;
- 101/120 folds produced a valid fitted-SDM Top-5 set;
- 16 folds retained genuine SDM fitting/scoring failures;
- 3 folds had an empty shared candidate pool;
- all-declared ACSP minus fitted-SDM recovery difference = −0.00027 (95% bootstrap interval −0.03852–0.03675);
- mean Top-5 shared count among SDM-evaluable folds = 1.93/5;
- mean Jaccard overlap = 0.264;
- exact set agreement = 1/101 folds.

The intended interpretation is **similar regional recovery with usually different operational decisions**. The benchmark does not establish general superiority of either method.

## Interpretation guardrails

- The supported primary endpoint is regional held-out recovery, with 10 km as the frozen confirmatory scale.
- Same-pool random selection is the central independently confirmed counterfactual; it separates candidate availability from selection value.
- Failed folds and failed taxon–region pairs remain in the intention-to-evaluate denominator.
- Plant and animal selection policies must be reported exactly as frozen.
- Secondary standard-comparator results are component-attribution evidence on regenerated occurrence/candidate snapshots, not a replacement for the original independent confirmation estimates.
- The direct fitted-SDM comparison is a secondary matched-pool decision contrast, not a universal test that ACSP is better than SDMs.
- Similar held-out recovery does not imply that ACSP and SDM are equivalent methods; decision overlap is reported separately.
- SDMs estimate a location-indexed fitted quantity; ACSP returns a finite candidate set under a budget. SDM output may be an input to ACSP.
- The paper does not claim exact-location prediction, occupancy probability, accessibility, detectability, or discoveries per field day.
- The production Streamlit application contains additional components that are outside the validated paper core.

## Repository separation

- `zuizui0223/acsp`: finite candidate-set selection and same-pool counterfactual validation.
- `zuizui0223/odsp`: later occurrence-relative geographical survey-patch development.
- `zuizui0223/eog`: environmental-state geometry and bridge-hypothesis research.

These repositories may exchange frozen data products, but the ACSP paper remains limited to its finite-set decision estimand.
