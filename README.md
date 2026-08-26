# ACSP — Adaptive Complementarity-based Survey Prioritization

**ACSP returns candidate survey patches.**

The validated product reconstructs a robust, occurrence-conditioned environmental support envelope from occurrence prototypes and converts the narrowest confirmed support tier into bounded candidate patches.

It does **not** ask the user to choose a survey budget, number of sites, route, travel mode, or field days. It does **not** claim occupancy probability or an exact occupied location.

## Simplest use

For the validated Japanese domain, the user now supplies only a scientific species name:

```bash
acsp-patches \
  --taxon "Castanopsis sieboldii" \
  --output candidate_patches.csv \
  --summary-json candidate_patches_summary.json
```

ACSP resolves the species through the GBIF backbone and evaluates the **same 12 Japanese region rectangles used by the cross-taxon confirmation design**. Each region is processed independently with the frozen input-generation conventions: up to 150 regional occurrence records, deterministic thinning to at most 32 prototypes, one deterministic 800-point terrain surface, the confirmed terrain features, and the fixed 2.5% robust-support rule.

Regions with too few usable occurrence/environment prototypes are recorded as skipped. ACSP does not widen the support threshold, replace the region, or create a route/budget optimization problem. Candidate patches from evaluable regions are concatenated and retain their validation-region identity.

The 12 validation units intentionally remain separate; overlapping units such as Kanto and Izu are not merged after candidate generation.

### Optional custom extent

A custom rectangular region remains available when the user explicitly wants one:

```bash
acsp-patches \
  --taxon "Castanopsis sieboldii" \
  --extent 139.20 34.60 139.50 34.85 \
  --output candidate_patches.csv
```

The fixed Japan-region path is the closest match to the spatial domain used in the untouched confirmation. A custom extent changes that spatial domain and should be interpreted as a convenience application of the same candidate-generation rule, not a new independent validation result.

## Candidate CSV schema

The validated CSV is deliberately narrow. Each row is one candidate patch and contains only:

- `candidate_patch_id`;
- `survey_area_id`;
- representative `latitude` / `longitude`;
- `support_cell_count`;
- `candidate_patch_radius_m`;
- fixed `patch_merge_distance_m`;
- fixed `support_fraction`;
- `validation_status`.

The species-only Japan path additionally records `validation_region_id`, `validation_region_name`, and `validation_geographic_stratum`.

Legacy planner fields such as `zone_score`, model/access support, agreement scores, and ranks are excluded from the validated product. Confirmation statistics such as pair count, fold count, lift, confidence interval, and p-value remain in the summary JSON instead of being duplicated on every candidate row.

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

The confirmation passed every predeclared gate without post-outcome retuning. The supported claim is narrow: **the frozen 2.5% robust-support candidate tier enriches held-out occurrences relative to same-size random selection at the 10 km regional screening scale across the tested plant and animal cohort.**

This does not establish occupancy probability, calibrated suitability probability, exact-site precision, route efficiency, budget optimality, or universal optimality of 2.5% outside this ACSP candidate-generation contract.

### Country-framed extension status

A separate country-framed regional-lattice extension was developed to test whether the same frozen candidate-patch rule could be carried beyond the validated Japanese regional frame. Its development cohort was favorable, but the preregistered reserved 24-taxon replication did **not** pass all seven gates.

The reserved replication retained positive mean lift overall (**+0.08961**), for plants (**+0.07515**), and for animals (**+0.11026**). Candidate generation succeeded for **20/24** taxa and temporal evaluation was available for **18/24**. However, the taxon-bootstrap 95% CI was **[-0.00248, +0.18243]**, so the preregistered positive-lower-bound gate failed.

A completely fresh, disjoint **48-taxon** confirmation was then frozen before identities and outcomes were opened. The scientific method and seven primary gates were unchanged. It again produced a positive effect among integrated evaluable taxa: mean robust-minus-random lift was **+0.13230**, with taxon-bootstrap 95% CI **[+0.04958, +0.21964]**; plant mean lift was **+0.08583** and animal mean lift was **+0.17330**. Candidate generation succeeded for **40/48** taxa. However, temporal evaluation was available for only **34/48 = 0.7083**, below the preregistered **0.75** gate, so the fresh confirmation also failed overall (**6/7 gates passed**).

The secondary heterogeneity hypothesis generated after the reserved replication did not reproduce: plant lift SD was **0.22460**, animal lift SD was **0.27292**, and the plant/animal SD ratio was **0.823** with bootstrap 95% CI **[0.340, 1.242]**. This secondary result was explicitly unable to change the primary promotion decision.

Therefore the country-framed/global extension remains **development evidence, not a validated global candidate-generation product**. The repeated positive lift among evaluable taxa is not enough to override the preregistered generality/evaluability gates. No country-framed or global claim should replace the validated Japanese-domain claim above.

The reserved-replication result is preserved in `validation/acsp_country_framed_robust_integration_development_v2_replication_result_v1.json`. The fresh confirmation is preserved in `validation/acsp_country_framed_fresh_heterogeneity_confirmation_result_v1.json`, with its 48-taxon compact audit in `validation/acsp_country_framed_fresh_heterogeneity_confirmation_taxon_audit_v1.csv`. Post-outcome diagnostics remain descriptive only and are not eligibility rules or retuned science.

## Install

```bash
python -m pip install .
```

The installable distribution is `acsp-survey`; the import package is `acsp`.

## Python API

Species-only Japan scan:

```python
from acsp import discover_validated_candidate_patches_japan

patches, audit = discover_validated_candidate_patches_japan("Castanopsis sieboldii")
```

Custom region:

```python
from acsp import discover_validated_candidate_patches

patches, audit = discover_validated_candidate_patches(
    "Castanopsis sieboldii",
    (139.20, 34.60, 139.50, 34.85),
)
```

For precomputed environmental tables, the lower-level validated API remains available:

```python
from acsp import validated_robust_candidate_patches

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

## Input interpretation

The candidate universe is an environmental surface, not a probability raster. Environmental features are centered and robustly scaled against occurrence prototypes. Candidate support is based on environmental distance to those prototypes across leave-one-prototype-out worlds.

The confirmed terrain features are elevation, slope, aspect represented as sine/cosine, roughness, and topographic position index. Changing the feature set belongs to research/audit use, not the frozen validated path.

## Campanula development role

The 2026 *Campanula punctata* / microdonta field material was used as **development data**, not as independent confirmation. Independent generalization was established only with the later taxonomy-safe untouched 96-pair cohort.

## Failure handling

In normal use, a Japanese region with insufficient occurrence/environment prototypes is skipped and retained in the audit. If none of the 12 fixed regions is evaluable, ACSP returns an explicit failure. An evaluable region may legitimately yield zero patches at the frozen 2.5% tier; the threshold is not widened automatically.

## Legacy compatibility

`acsp-recommend`, `acsp-fieldmap`, the Streamlit app, integrated-score ranking, SDM/SSDM helpers, and earlier Top-k/zone-selection functions remain for backward compatibility and historical analyses. They are **not the current validated product boundary**.

No route, field-day, travel-mode, or budget optimizer belongs in the validated candidate-patch path.

## Repository layout

- `acsp/taxon_patches.py` — species-only fixed-Japan and optional custom-region adapters.
- `acsp/validated_robust.py` — promoted validated candidate-patch API and minimal output schema.
- `acsp/robust_cli.py` — `acsp-patches` command.
- `acsp/robust_patches.py` — lower-level robust support and patch utilities.
- `validation/` — frozen protocols and confirmation contracts.
- `research/` — development, diagnostics, confirmation runners, and historical analyses.
- `legacy/` — retained historical benchmark code/results.

## Status

**Alpha (0.1.0).** The robust candidate-patch rule has passed independent cross-taxon confirmation at the 10 km screening scale in the validated Japanese regional domain. The country-framed extension failed both its reserved replication and a completely fresh 48-taxon confirmation and remains development-only. Exact field occupancy, detectability, abundance, and fine-scale access remain outside the validated claim.
