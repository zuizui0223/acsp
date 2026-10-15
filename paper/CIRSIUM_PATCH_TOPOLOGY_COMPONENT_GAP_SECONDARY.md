# A distance-bounded candidate patch need not be a connected high-support region

**Status:** secondary descriptive methods-and-results note, reconstructed on 15 October 2026 from the **already frozen** 8 October four-unit *Cirsium* structural-patch topology audit. **Not** an untouched biological confirmation, a new terrain reanalysis, or part of the independently validated 96-pair / 480-fold Japan robust-patch benchmark. Preserve the full-rank reproducibility block in Issue #253 and draft PR #250.

## Ecological survey-method question

If occurrence-informed spatial support is converted into finite, distance-bounded survey patches, do the patch objects still describe *contiguous* areas of retained high support? This matters for interpreting a patch as one visually coherent region on a map. It does **not** by itself establish a walkable site, a single field visit, or ecological connectivity between occupied habitats.

## Frozen measurement

The earlier research-stage *Cirsium* fine-structure transfer retained the original **2.5% tier** of source-complete **100 m** cells under three predeclared structural families, then grouped the retained cells into **1 km maximum-diameter complete-link patches**. The subsequently frozen patch-membership-only audit (PR #256; source workflow `37732320419`) required byte identity with the PR #247 private patch archives before reading their memberships; it reported coordinate-free components under **eight-neighbour (Moore) adjacency**. The audit was expressly independent of the failed-to-reproduce full upstream structural order.

For unit \(u\), define \(P_u\) as the number of complete-link patches and \(G_u\) as the number of 8-neighbour connected components of the *entire* retained-cell mask. If each patch contains \(c_{ui}\) within-patch connected components, then \(S_u=\sum_i c_{ui}=P_u+E_u\), where \(E_u=\sum_i (c_{ui}-1)\) measures **extra within-patch components**. The difference \(J_u=S_u-G_u\) is the number of **net component unions** obtained when cross-patch grid adjacencies are restored; this is **not** the number of adjacency edges or possible field routes. Therefore

\[
G_u-P_u = E_u - J_u.
\]

A patch set may *under-count* or *over-count* globally connected high-support components depending on which term dominates. The identity is descriptive graph accounting, not a new model fitted to species observations.

## Results from previously frozen public receipts

| Unit and declared structural family | Retained cells | 1 km patches \(P\) | Disconnected patches | Retained cells inside disconnected patches | Within-patch components \(S\) | Net cross-patch unions \(J\) | Global components \(G\) | \(G-P\) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| CIR02 · wetland-moisture | 9,546 | 573 | 320 (55.8%) | 3,472 (36.4%) | 1,161 | 354 | 807 | +234 |
| CIR06 · alpine-topography | 20,409 | 3,883 | 3,292 (84.8%) | 19,313 (94.6%) | 11,720 | 828 | 10,892 | +7,009 |
| CIR12 · open grassland | 15,187 | 654 | 278 (42.5%) | 4,767 (31.4%) | 1,052 | 547 | 505 | −149 |
| CIR13 · open grassland | 15,187 | 654 | 278 (42.5%) | 4,767 (31.4%) | 1,052 | 547 | 505 | −149 |

Across the four **algorithmic configurations**, 42.5–84.8% of bounded patches were internally non-connected in their retained support mask. The strongest discrepancy was in the alpine-topography configuration: 84.8% of its patches were disconnected, enclosing 94.6% of its retained cells, and its global component count was 2.805 times the patch count. Wetland-moisture also had more components than patches (807 versus 573), whereas the grassland configurations had fewer (505 versus 654), because cross-patch reunions (547) exceeded extra within-patch components (398). The **sign reversal** rules out interpreting patch count as a consistent proxy for the number of connected high-support domains.

CIR12 and CIR13 use the *same predeclared grassland structural family*. Their aggregate topology measures are equal, while the originally frozen patch-archive SHA-256 values are **different**. Different compressed-file hashes may reflect unit labels or serialization and do **not** prove different geographic membership. Conversely, equal aggregate counts do not prove identical cell membership or provide two independent confirmations of a species-level generalization.

## Interpretation and limits

**Supported:** A 1 km complete-link diameter bound does not impose 100 m Moore-connected retained support. In these frozen research-stage configurations, patch-level compactness and support-mask connectedness diverged in both directions, so a map legend must not call such patches *contiguous habitat* or count them as independent continuous survey domains without an explicit connectivity layer.

**Not supported:** The high-support mask is a model-derived threshold, not a map of occupied or accessible habitat. Missing or unretained cells are not biological absences or barriers. Connected components are not independent field sites, access routes, site-visits, population fragments, or habitat corridors. The four units span **three declared feature families**, not four independent methods or four biological validation replicates. These numbers are *not* estimates of ACSP's independently validated nationwide robust-patch performance, global transfer, recovery lift, or field efficiency. Upstream GSI/full structural-order reproduction remains a separate unsatisfied gate for the strict PR #250 continuity study.

**Research implication (hypothesis, not present finding):** For a new, independently frozen and prospective ecological validation, retain the existing non-ranked candidate patches as the primary object, then examine a *downstream descriptive* connectivity overlay (without changing their membership), and ask whether connectivity-informed site-level interpretation predicts equal-effort field discovery or survey effort on disjoint taxa and regions. Changing the core patch assignment or reporting connectivity as habitat continuity would require a **new scientific method and validation cycle**.

## Source and reproduction

This is a deterministic *post hoc arithmetic synthesis* of `validation/coverage_then_fine_structure_fresh_sentinel_v2_frozen_patch_topology_result_v1.json`, which already reported the original PR #256 four-unit component counts. Original frozen patch denominators and SHA values come from `validation/coverage_then_fine_structure_fresh_sentinel_v2_fine_patch_transfer_result_v1.json` (PR #247). The four original PR #256 public-safe artifacts are `11532064437`, `11534155745`, `11534893251` and `11536552476`. The source-locked derivation and tests are in `research/summarize_cirsium_frozen_patch_topology_gap.py`, `validation/coverage_then_fine_structure_fresh_sentinel_v2_patch_topology_component_gap_v1.json` and `tests/test_cirsium_frozen_patch_topology_gap.py`. No private cell IDs or coordinates were used in this synthesis.
