# ACSP methods paper

This paper is scoped to the pre-*Campanula microdonta* cross-taxon validation program.

## Included evidence

1. **Primary retrospective confirmation:** predeclared taxon–region cohorts evaluated with spatial-block hold-out and same-pool random Top-5 controls.
2. **Leakage control:** candidates are reconstructed from training occurrences only; known-location and direct occurrence-distance evidence are excluded from the confirmatory comparison.
3. **Selection-value inference:** repeated folds are summarized within taxon–region pairs, with pair-level bootstrap, half-cohort, leave-one-pair-out, and sign-flip stability analyses.
4. **Frozen decision contract:** the publication-facing plant and animal policies are exported with deterministic manifests and explicit claim boundaries.
5. **Secondary component-attribution benchmark:** the same frozen taxon–region cohorts and ACSP policies were re-evaluated under a separately predeclared same-pool comparator protocol using regenerated GBIF occurrences, candidate surfaces, and spatial folds.

The primary paper asks whether an occurrence-conditioned selection policy adds recovery value beyond random selection from the identical generated candidate pool. The secondary comparator asks whether that value is better explained by focal-taxon local evidence, geographic spread, generic environmental spread, or their combination. It does not claim exact-site occupancy, field efficiency, universal superiority over survey-design algorithms, or validation of every production-app component.

## Excluded from this paper

The 2026 *C. microdonta* island application, area-balanced post-baseline update, gap-patch development, occurrence-patch connectivity, corridor/barrier experiments, and production-only integrated evidence are not part of the ACSP paper.

The island field application remains in `field_validation/` as development provenance. It is not read by the paper builder.

## Rebuild paper outputs

```bash
python -m pip install -e .
python paper/build_paper_outputs.py
```

The publication builder produces the retrospective and reviewed secondary-comparator outputs without requiring field GPS data or post-baseline island algorithms.

Primary outputs:

- `table_1_retrospective_validation.csv`
- `table_s1_seed_sensitivity.csv`
- `table_s2_claim_matrix.csv`
- `table_s3_standard_baseline_comparison.csv`
- `retrospective_stability.json`
- `validated_core_policies.json`
- `standard_baseline_results_manifest.json`
- `paper_output_manifest.json`

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

## Interpretation guardrails

- The supported primary endpoint is regional held-out recovery, with 10 km as the frozen confirmatory scale.
- Same-pool random selection is the central independently confirmed counterfactual; it separates candidate availability from selection value.
- Failed folds and failed taxon–region pairs remain in the intention-to-evaluate denominator.
- Plant and animal selection policies must be reported exactly as frozen.
- Secondary comparator results are component-attribution evidence on regenerated occurrence/candidate snapshots, not a replacement for the original independent confirmation estimates.
- The paper does not claim universal superiority, exact-location prediction, occupancy probability, accessibility, detectability, or discoveries per field day.
- Direct comparison with a fitted SDM-led Top-k policy remains future work.
- The production Streamlit application contains additional components that are outside the validated paper core.

## Repository separation

- `zuizui0223/acsp`: finite candidate-set selection and same-pool counterfactual validation.
- `zuizui0223/odsp`: later occurrence-relative geographical survey-patch development.
- `zuizui0223/eog`: environmental-state geometry and bridge-hypothesis research.

These repositories may exchange frozen data products, but the ACSP paper remains limited to its finite-set decision estimand.
