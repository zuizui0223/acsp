# Frozen standard-baseline benchmark

This benchmark addresses a limitation of the existing confirmed ACSP evidence. Same-pool random Top-5 controls show that the frozen ACSP selection rule adds value beyond random choice from its generated candidate pool. They do not show that ACSP exceeds reasonable spatially balanced or environmentally balanced survey designs.

## Frozen protocol

The machine-readable declaration is [`validation/standard_baseline_protocol.json`](../validation/standard_baseline_protocol.json). Parameters must not be changed after comparator outcomes are inspected.

Primary settings:

- Top-5 candidate-set budget;
- 10 km held-out occurrence recovery;
- 0.1-degree spatial blocks;
- five expected repeats per taxon-region pair;
- 200 random sets per fold;
- pair-level inference;
- missing universal-method folds contribute zero to intention-to-evaluate means.

The compared methods are:

1. frozen taxon-group-specific ACSP;
2. local-environment evidence Top-5;
3. geographic maximin;
4. environmental maximin;
5. equally weighted geographic-environmental maximin;
6. same-pool random Top-5 mean;
7. a held-out greedy oracle used only to describe candidate-pool headroom.

The oracle is not a usable survey method because it reads held-out outcomes.

## Environmental comparator eligibility

The frozen environmental feature declaration is:

- elevation;
- slope;
- aspect;
- roughness;
- topographic position index (`tpi`).

Aspect is transformed to sine and cosine before robust scaling. The remaining features use median and interquartile-range scaling within the fold candidate pool.

Environmental and dual-space methods are not treated as universally applicable to every candidate surface. A taxon-region pair enters those method-specific comparisons only when every expected fold contains finite values for all five predeclared raw terrain features. Eligibility is determined from input schema and values, not from recovery outcomes. Universal methods retain every declared pair and use intention-to-evaluate zeroes for failed or missing folds.

## Two-stage audit design

### Stage 1: export

`export_standard_baseline_folds.py` regenerates each frozen cohort from its predeclared taxon-region table. For every fold it writes:

- explicit training occurrences;
- explicit held-out occurrences and blocks;
- the complete distance-free candidate table;
- stable candidate IDs;
- candidate-level held-out coverage IDs and distances;
- the raw environmental columns;
- leakage and environmental-eligibility audits;
- SHA-256 checksums and protocol fingerprints.

The candidate builder receives training occurrence coordinates only. Held-out IDs, coordinates, distances and recovery labels are attached after candidate construction.

### Stage 2: comparison

`run_standard_baseline_benchmark.py` verifies the checksums and protocol fingerprint before evaluating selectors. It writes:

- `fold_method_comparison.csv`;
- `pair_level_intention_to_evaluate.csv`;
- `pair_level_comparator_inference.csv`;
- `method_summary.csv`;
- `method_eligibility_audit.csv`;
- `standard_baseline_benchmark_manifest.json`.

Bootstrap intervals and sign-flip tests operate on taxon-region-pair differences, not repeated folds.

## Execution

Use the manual **Standard same-pool baseline benchmark** GitHub Actions workflow separately for:

- `mixed_20260705`;
- `plants_20260706`.

The workflow performs both stages and uploads the explicit fold exports and result tables as one auditable artifact.

## Claim boundary

The comparator implementations and workflow do not establish a new result by themselves. No superiority claim should enter the manuscript until both frozen cohorts have completed and all negative, equivalent and positive results have been retained.

The benchmark does not validate exact-site occupancy, general 5 km precision, access, detection probability, field efficiency, route optimization or the complete production integrated score.
