# ACSP methods paper

This paper is scoped to the frozen pre-*Campanula microdonta* validation program.

## Included evidence

1. **Retrospective breadth:** predeclared taxon–region cohorts evaluated with spatial-block hold-out and same-pool random Top-5 controls.
2. **Leakage control:** candidates are reconstructed from training occurrences only; known-location and direct occurrence-distance evidence are excluded from the confirmatory comparison.
3. **Selection-value inference:** repeated folds are summarized within taxon–region pairs, with pair-level bootstrap, half-cohort, leave-one-pair-out, and sign-flip stability analyses.
4. **Frozen decision contract:** the publication-facing plant and animal policies are exported with deterministic manifests and explicit claim boundaries.

The paper asks whether an occurrence-conditioned environmental-analogue selection rule adds recovery value beyond random selection from the identical generated candidate pool. It does not claim exact-site occupancy, field efficiency, superiority over established survey-design algorithms, or validation of every production-app component.

## Excluded from this paper

The 2026 *C. microdonta* island application, area-balanced post-baseline update, gap-patch development, occurrence-patch connectivity, corridor/barrier experiments, and production-only integrated evidence are not part of the confirmatory ACSP paper.

The island field application remains in `field_validation/` as development provenance. It is not read by the paper builder.

## Rebuild paper outputs

```bash
python -m pip install -e .
python paper/build_paper_outputs.py
```

The publication builder produces the frozen retrospective outputs without requiring field GPS data or post-baseline algorithms.

Primary outputs:

- `table_1_retrospective_validation.csv`
- `table_s1_seed_sensitivity.csv`
- `table_s2_claim_matrix.csv`
- `retrospective_stability.json`
- `validated_core_policies.json`
- `paper_output_manifest.json`

## Standard comparator stage

`acsp.decision_baselines` implements deterministic same-pool selectors for:

- local-evidence Top-k;
- geographic maximin coverage;
- environmental maximin coverage after robust scaling;
- declared geographic–environmental dual-space maximin coverage;
- reproducible random same-pool sets.

These implementations make the next benchmark possible, but no comparator result enters the manuscript until frozen candidate-level fold exports are evaluated without changing the ACSP policies.

## Interpretation guardrails

- The supported endpoint is regional held-out recovery, with 10 km as the primary frozen scale.
- Same-pool random selection is the central confirmed counterfactual; it separates candidate availability from selection value.
- Failed folds and failed taxon–region pairs remain in the intention-to-evaluate denominator.
- Plant and animal selection policies must be reported exactly as frozen.
- The paper does not claim universal superiority, exact-location prediction, occupancy probability, accessibility, detectability, or discoveries per field day.
- The production Streamlit application contains additional components that are outside the validated paper core.
- Geographic, environmental, dual-space, and SDM-led comparators must be reported before claiming superiority over established survey-design approaches.

## Repository separation

- `zuizui0223/acsp`: finite candidate-set selection and same-pool counterfactual validation.
- `zuizui0223/odsp`: later occurrence-relative geographical survey-patch development.
- `zuizui0223/eog`: environmental-state geometry and bridge-hypothesis research.

These repositories may exchange frozen data products, but the ACSP paper remains limited to its validated finite-set estimand.
