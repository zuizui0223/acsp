# Original ACSP v2: descriptive heterogeneity of historical candidate-patch recovery

**Status: post hoc descriptive audit of previously confirmed result rows, NOT a new confirmatory experiment.**
The source is **only** original 2026-08-20 GitHub Actions run
[32337884576](https://github.com/zuizui0223/acsp/actions/runs/32337884576),
artifact 9396133154, ZIP SHA-256
`f23c23afe4863f816f2b3a0780d9a39d6eddb383512188a0bf572dcdf055936f`.
The [byte-pinned replay receipt](../validation/acsp_original_v2_archival_reconciliation_20261028.json)
and [descriptive result](../validation/acsp_original_v2_descriptive_heterogeneity_20261028.json)
permit full source-byte checking. No original GBIF raw records, field observations,
new taxa, or post-result tuning enter these calculations.

## The positive primary mean is not an all-taxon result

The preregistered estimand was the **mean** of five-fold within-pair,
10-km held-out recovery lift over equally sized random candidate-patch sets,
with zeros for all declared failures. That frozen confirmatory mean remains
**+0.085587** (96 pairs, 480 folds; original pair-bootstrap 95% CI
**[+0.051186, +0.121651]**, original one-sided sign-flip
**p=3.333222e-5**).

**Post hoc distribution of 96 five-fold pair means:**

| Summary | Pair-level outcome |
|---|---:|
| Positive | **54 / 96** |
| Zero | **17 / 96** |
| Negative | **25 / 96** |
| Pair-level mean lift | **+0.085587** |
| Pair-level median lift | **+0.028380** |
| 25th percentile | −0.002738 |
| 75th percentile | +0.159209 |
| Plant pairs | 48: 25 positive, 7 zero, 16 negative |
| Animal pairs | 48: 29 positive, 10 zero, 9 negative |

The mean and median differ substantially. The **group means** are positive
(plants **+0.057024**, animals **+0.114150**) but taxon-group sign
counts were not separately predeclared confirmatory tests. The original
claim therefore remains **aggregate held-out regional enrichment**, not
uniform gains across every species.

## Failure is a part of the estimand, not field absence

**Of 480 primary 10-km fold outputs:**

| Original failure classification | Fold count |
|---|---:|
| No technical/empty-support failure | 375 |
| Insufficient complete environmental prototypes | 55 |
| Empty selected robust-support tier | 39 |
| Too few occupied spatial blocks | 10 |
| Too few training coordinates | 1 |
| **Total** | **480** |

At the **pair level**, 73 pairs had no failed folds and 23 had at
least one; 17 had failures in all five folds. These zeroed results
do not imply biological nondetections. The descriptive mean was
+0.109511 among the 73 fully evaluated pairs and +0.009653 among
the 23 partially/fully failed pairs. **Do not replace the
intention-to-evaluate mean with a complete-case mean**: that would
change the declared estimand after examining outcomes and cause
selection bias.

## Regional heterogeneity, descriptive only

All 12 frozen frames contained **eight pairs**, and 10 regions had
positive aggregate regional mean lift. The two negative regional means
were **Izu −0.011081** (8/8 pairs with at least one failed fold) and
**Ryukyu −0.080734** (4/8 pairs with at least one failed fold).

A deterministic leave-one-region-out **descriptive** recomputation
retains positive overall mean values across all 12 omissions
(range **+0.079442 to +0.100707**). This is not a new
cluster-bootstrap confidence interval and does not confirm regional
comparability. Each regional mean has only eight taxon-pair
contributions and may reflect a mixture of data availability,
habitat context, species identity and scoring-stage failure.
It cannot establish a causal island effect, elevation effect,
island syndrome, ecological disappearance, detection efficiency,
or landscape fragmentation mechanism.

## Scale is central to scientific interpretation

The original 480 declared fold results at each reported radius give:

| Radius | Mean candidate-patch recall | Mean same-size random recall | Mean lift |
|---:|---:|---:|---:|
| 1 km | 0.009350 | 0.003159 | +0.006191 |
| 2 km | 0.029815 | 0.013042 | +0.016773 |
| 5 km | 0.090940 | 0.058799 | +0.032141 |
| **10 km (predeclared primary)** | **0.258601** | **0.173014** | **+0.085587** |

The strongest *absolute* improvement in these evaluated radii
occurs at the 10-km regional screening endpoint. Gains at finer
distances are not the same claim as verified exact-site occupancy
or field efficiency. The 1/2/5-km values are **secondary, descriptive,
not multiple newly confirmatory tests**.

## Reproduce only from original source bytes

```bash
python research/describe_original_v2_patch_heterogeneity.py \
  --results-zip path/to/acsp_original_confirmation_results_20260820.zip \
  --verify-saved validation/acsp_original_v2_descriptive_heterogeneity_20261028.json
```

The script refuses unexpected ZIP SHA-256, missing/extra source members,
changed pair counts, reweighted groups/regions, missing declared
fold-by-radius cells, unknown failure reasons, drift from the original
primary mean, or disagreement with the committed public aggregate
receipt. The workflow
[`acsp-original-v2-heterogeneity.yml`](../.github/workflows/acsp-original-v2-heterogeneity.yml)
downloads **only the original run's** archival ZIP while still available.

**Strict separation:** historical result-table descriptive audit ≠
original GBIF record restoration ≠ independent confirmation ≠ field
discovery ≠ a change to the frozen 2.5%/float32/1-km product.
No pair identifiers, species names or exact locations are published
in the new aggregate receipt; original sources remain identifiable by
hash and run ID.
