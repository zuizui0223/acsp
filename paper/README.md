# ACSP methods paper

This paper is now scoped to the frozen pre-*Campanula microdonta* validation program.

## Included evidence

1. **Retrospective breadth:** predeclared taxon–region cohorts evaluated with spatial-block hold-out and same-pool random Top-5 controls.
2. **Leakage control:** candidates are reconstructed from training occurrences only; known-location and direct occurrence-distance evidence are excluded from the confirmatory comparison.
3. **Selection-value inference:** repeated folds are summarized within taxon–region pairs, with pair-level bootstrap, half-cohort, leave-one-pair-out, and sign-flip stability analyses.

The paper asks whether an occurrence-conditioned environmental-analogue selection rule adds recovery value beyond random selection from the identical generated candidate pool. It does not claim exact-site occupancy, field efficiency, or validation of every production-app component.

## Excluded from this paper

The 2026 *C. microdonta* island application, area-balanced post-baseline update, gap-patch development, occurrence-patch connectivity, and corridor/barrier experiments are not part of the confirmatory ACSP paper.

The island field application is retained as provenance and as the motivating case for the separate `zuizui0223/odsp` research program. ODSP asks what geographical survey object should be used when supported candidate patches lie near, but outside, known occurrence patches.

## Rebuild paper outputs

```bash
python -m pip install -e .
python paper/build_paper_outputs.py
```

The publication builder should produce the frozen retrospective tables and manifest without requiring field GPS data or post-baseline algorithms.

Primary outputs:

- `table_1_retrospective_validation.csv`
- `table_s1_seed_sensitivity.csv`
- retrospective cohort audit and manifest

## Interpretation guardrails

- The supported endpoint is regional held-out recovery, with 10 km as the primary frozen scale.
- Same-pool random selection is the central counterfactual; it separates candidate availability from selection value.
- Failed folds and failed taxon–region pairs remain in the intention-to-evaluate denominator.
- Plant and animal selection policies must be reported exactly as frozen.
- The paper does not claim universal superiority, exact-location prediction, occupancy probability, accessibility, detectability, or discoveries per field day.
- The production Streamlit application contains additional components that are outside the validated paper core.

## Repository separation

- `zuizui0223/acsp`: finite candidate-set selection and same-pool counterfactual validation.
- `zuizui0223/odsp`: occurrence-relative geographical survey-patch construction.
- `zuizui0223/eog`: descriptive geometry of observed states in environmental feature space.

Any future cross-reference should preserve these distinct estimands rather than presenting the repositories as successive versions of one algorithm.
