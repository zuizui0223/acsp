# First-stage feasibility: topology-aware versus geometry-only Cirsium field sites

**Status, 16 October 2026:** Post hoc and source-locked *method-design feasibility*, not a new biological confirmation, assigned field schedule or field detection result. This note is separate from the independently validated ACSP Japan robust-patch manuscript.

## Question and design

Prior frozen Cirsium development showed that a 1-km complete-link patch of retained 100-m high-support cells can contain multiple Moore-8 connected components. But internal fragmentation is not enough to imply a different **survey site**. The two predeclared downstream rules may choose the same retained cell: (T) medoid of the largest 8-neighbour fragment, or (G) medoid of all retained cells in the unchanged patch. Thus the useful pre-field *first stage* is the fraction of **assigned** patches whose proposed sites actually differ.

Define for an independently frozen pre-outcome patch cohort with N assigned patches:

\[q=\frac{1}{N}\sum_{i=1}^{N}\mathbf{1}\{s_T(i)\ne s_G(i)\}.\]

Under a **site-only intervention**, identical observer/season/search process for identical sites, and a binary verified-current-occurrence response, the mean **expected potential-outcome** contrast satisfies:

\[|\tau| = \left|N^{-1}\sum_i(E[Y_i(T)]-E[Y_i(G)])\right|\le q.\]

This follows because same-site assignments have zero expected site-only difference and each different-site binary difference is at most one. **It is not a bound on the realized difference in observed arm proportions, an estimate of detection, a confidence interval or a claim of exchangeability** when access, observer effects, timing or permissions differ. A missing or unknown N gives undefined q, not zero effect. If q=0, no site-only comparison is identifiable despite fragmented high-support masks.

The already-implemented original `public_design_receipt` counts `shared_counterfactual_count` per cohort without revealing candidate cell IDs. The new source-bound validator ensures 1:1 arm balance, 90 planned person-minutes per patch, exact shared-site accounting, and no accidentally promoted eligibility. It reports the **theoretical** bound only for the submitted unauthenticated synthetic public preview. It cannot certify actual candidate-patch source or a prospective field allocation.

## Frozen development frame: hypothetical exhaustive active-search workload

From the byte-frozen PR #273 topology result, the old, method-development-exposed units have 320 (CIR02), 3,292 (CIR06), 278 (CIR12) and 278 (CIR13) internally disconnected patches. Assume, **only for hypothetical accounting**, every one of these patches is assigned one representative site and all receive three 30-minute searches by one observer (90 person-minutes each). All four counts are even, so there would be no odd reserve:

| Previously exposed structural configuration | Disconnected patches | Sites per arm (hypothetical) | Total planned active person-hours |
|---|---:|---:|---:|
| CIR02 wetland | 320 | 160 | 480 |
| CIR06 alpine | 3,292 | 1,646 | 4,938 |
| CIR12 grassland | 278 | 139 | 417 |
| CIR13 grassland | 278 | 139 | 417 |
| **Four configurations** | **4,168** | **2,084** | **6,252** |

These are **not independent biological replicates** (the grassland policy is shared), proposed sample sizes, permission-eligible sites, survey-day/cost budgets, required visits, travel time or field observations. The exhaustive arithmetic would count 375,120 hypothetical person-minutes. It does not mean 4,168 actual sites could be visited, nor imply any gain from connectivity.

## Unmet prerequisites for the new independent study

The source-locked PR #276 nine-name screen had **zero** confirmed independent taxon-sector cohorts and **zero** authenticated field-ready assignments. All remaining prospective 100-m patch frames are unbuilt or unverified. The fraction q of real source-authenticated *new* patches proposing distinct sites is unknown. The previous development units cannot be repurposed as untouched confirmation.

Before field visits, independently freeze new taxa/sectors, authenticate exact private source-complete 100-m patch members and SHA evidence, assess both potential sites for access/permission/phenology **without outcomes**, then calculate q and seal arm assignment and matched effort with a public hash-only receipt. If fewer than two viable patches or q=0, retain that outcome-blind ineligibility rather than replacing the cohort for a favorable response. All field outcomes, actual effort, species detection and any taxon-level effect estimate remain unavailable.

Neither the validated 2.5% / 1 km non-ranked robust patch generator, the previous three-arm fresh-SENTINEL cohort, the strict structural-order PR #250 gate nor the unresolved CIR02 CPU causality is changed.

## Reproducibility

Source Git blob SHA-1s are checked for `validation/coverage_then_fine_structure_fresh_sentinel_v2_patch_topology_component_gap_v1.json` (PR #273), `validation/coverage_then_fine_structure_patch_connectivity_field_trial_design_v1.json` (PR #274), and `validation/cirsium_topology_new_cohort_public_exposure_screen_result_v1.json` (PR #276). The public calculation is in `research/assess_cirsium_topology_site_first_stage.py`; the no-private-sites output is `validation/cirsium_topology_site_selection_first_stage_feasibility_v1.json`. The illustrative preview in `examples/synthetic_topology_site_preview.json` is **fabricated** and is never an actual candidate cohort. Regression tests are in `tests/test_cirsium_site_first_stage_feasibility.py`.
