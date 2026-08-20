# ACSP — Adaptive Complementarity-based Survey Prioritization

**ACSP returns candidate survey patches.**

The validated product reconstructs a robust, occurrence-conditioned environmental support envelope from training occurrences and converts the narrowest confirmed support tier into bounded candidate patches.

It does **not** ask the user to choose a survey budget, number of sites, route, travel mode, or field days. It does **not** claim occupancy probability or an exact occupied location.

## Validated product

The promoted cross-taxon rule is fixed at:

- leave-one-prototype-out robust environmental support;
- float32 support worlds for numerical reproducibility;
- support fraction = **2.5%**;
- same-area patch aggregation within **1 km**;
- output unit = **candidate patch**.

These scientific parameters are not user-tunable in the validated API.

### Untouched confirmation

The rule was frozen before opening a taxonomy-safe untouched cohort and then evaluated on **96 taxon-region pairs × 5 spatial folds = 480 declared folds**. Failed or empty folds were retained as zero rather than dropped or replaced.

At the predeclared 10 km regional screening scale:

- overall mean lift over same-size random = **+0.08559**;
- pair-bootstrap 95% CI = **[+0.05119, +0.12165]**;
- one-sided sign-flip **p = 3.33 × 10⁻⁵**;
- animal mean lift = **+0.11415**;
- plant mean lift = **+0.05702**.

The confirmation passed every predeclared gate without post-outcome retuning. The supported claim is therefore narrow: **the frozen 2.5% robust-support candidate tier enriches held-out occurrences relative to same-size random selection at the 10 km regional screening scale across the tested plant and animal cohort.**

This does not establish occupancy probability, calibrated suitability probability, exact-site precision, route efficiency, budget optimality, or universal optimality of 2.5% outside this ACSP candidate-generation contract.

## Install

```bash
python -m pip install .
```

The installable distribution is `acsp-survey`; the import package is `acsp`.

## Validated CLI

Use `acsp-patches` with:

1. a candidate-universe CSV containing coordinates, survey-area ID, and environmental features;
2. a training-occurrence prototype CSV containing the same environmental feature columns.

Example:

```bash
acsp-patches \
  --universe candidate_universe.csv \
  --prototypes occurrence_prototypes.csv \
  --feature-columns elevation,slope,aspect_sin,aspect_cos,roughness,tpi \
  --output candidate_patches.csv \
  --summary-json candidate_patches_summary.json
```

The command writes one validated candidate-patch CSV. There is no `--budget`, `--days`, `--top-k`, support-threshold, or route option.

## Python API

```python
from acsp.validated_robust import validated_robust_candidate_patches

patches, audit = validated_robust_candidate_patches(
    candidate_universe,
    occurrence_prototypes,
    feature_columns=[
        "elevation",
        "slope",
        "aspect_sin",
        "aspect_cos",
        "roughness",
        "tpi",
    ],
)
```

The output is a bounded patch table with the frozen validation metadata attached to every patch.

Lower-level research/audit utilities remain available in `acsp.robust_patches`:

- `robust_environment_geometry()`;
- `leave_one_out_consensus_support()`;
- `support_cells_to_patches()`.

Those functions expose thresholds and other parameters for method development and audit. They are not the validated no-retuning product API.

## Input interpretation

The candidate universe is an environmental surface, not a probability raster. Environmental features are centered and robustly scaled against training-occurrence prototypes. Candidate support is based on environmental distance to those prototypes across leave-one-prototype-out worlds.

The current cross-taxon confirmation used terrain features:

- elevation;
- slope;
- aspect represented as sine and cosine;
- roughness;
- topographic position index.

The package core itself accepts arbitrary shared numeric environmental feature columns, but changing the feature set is outside the frozen validated product claim.

## Campanula development role

The 2026 *Campanula punctata* / microdonta field material was used as **development data**, not as independent confirmation. It helped identify the robust support-envelope design and is retained as a regression fixture. Independent generalization was established only with the later taxonomy-safe untouched 96-pair cohort.

## Failure handling

The untouched confirmation used intention-to-evaluate accounting. Folds with too few spatial blocks, too few complete environmental prototypes, or an empty 2.5% support tier were retained as zero. In the final confirmation, 23 of 96 pairs had at least one failed fold; the overall result still passed the frozen gate. This makes the reported cross-taxon lift conservative with respect to those operational failures.

## Legacy compatibility

`acsp-recommend`, `acsp-fieldmap`, the Streamlit app, integrated-score ranking, SDM/SSDM helpers, and earlier Top-k/zone-selection functions remain in the repository for backward compatibility and historical analyses. They are **not the current validated product boundary**.

No new route, field-day, travel-mode, or budget optimizer should be added to the validated candidate-patch path.

## Repository layout

- `acsp/validated_robust.py` — promoted validated candidate-patch API.
- `acsp/robust_cli.py` — `acsp-patches` command.
- `acsp/robust_patches.py` — lower-level robust support and patch utilities.
- `validation/` — frozen protocols and confirmation contracts.
- `research/` — development, diagnostics, confirmation runners, and historical analyses.
- `legacy/` — retained historical benchmark code/results.
- `r-acsp/` — earlier R compatibility package.

## Status

**Alpha (0.1.0).** The robust candidate-patch rule has passed independent cross-taxon confirmation at the 10 km screening scale. Exact field occupancy, detectability, abundance, and fine-scale access remain outside the validated claim.
