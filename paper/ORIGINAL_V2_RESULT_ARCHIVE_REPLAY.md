# Original August 2026 confirmation — byte-verified results replay

**Status (2026-10-28): HISTORICAL RESULTS REPRODUCED; ORIGINAL OCCURRENCE INPUTS STILL MISSING.**

This records recovery and verification of the **actual original** GitHub Actions
ZIPs, rather than a second GBIF download or posthoc re-estimation.

## Original sources recovered

| Object | GitHub run | Artifact ID | ZIP SHA-256 | GitHub retention through |
|---|---:|---:|---|---|
| Taxonomy-safe 96-pair frozen identity cohort | [32335791948](https://github.com/zuizui0223/acsp/actions/runs/32335791948) | 9394691112 | `cc0f949649491439f91e1b90d01d48acbd3f7fffc6833a75105a3bc175a5faf3` | 2026-11-18 05:29 UTC |
| Frozen v2 confirmation outcomes | [32337884576](https://github.com/zuizui0223/acsp/actions/runs/32337884576) | 9396133154 | `f23c23afe4863f816f2b3a0780d9a39d6eddb383512188a0bf572dcdf055936f` | 2026-11-18 06:01 UTC |

Both live GitHub artifact metadata records reported `expired=false`.
Both archives were downloaded on 2026-10-28; their ZIP bytes matched the exact
GitHub SHA-256 digests above. Every member file additionally passed a separate
SHA-256 check. The immutable [receipt](../validation/acsp_original_v2_archival_reconciliation_20261028.json)
pins the member names, hashes, run IDs and exact statistical readout.

The recovered ZIPs must be retained outside GitHub Actions **before expiry**.
A GitHub run link is not a perpetual occurrence-data archive.

## What was reproduced from original result rows

The original confirmation contains 96 taxon–region pair rows and **1,920**
fold-by-radius rows: 96 pairs × five declared spatial folds × four descriptive
recovery radii (1, 2, 5, 10 km). The original cohort archive also contains the
96 predeclared taxon identities, exclusion list, frozen frame audit and manifest.

An independent computation using the original pair-level values and frozen
30,000-draw seeds exactly reproduced:

| Preregistered 10-km endpoint | Recalculated |
|---|---:|
| Observed mean 10-km regional recall | 0.2586007856975168 |
| Same-size random mean 10-km recall | 0.1730137046713449 |
| **Pair-mean recovery lift** | **+0.08558708102617191** |
| Pair-bootstrap 95% CI | [0.051186296271122624, 0.12165096941745603] |
| One-sided sign-flip p | 0.00003333222225925803 |
| Plant mean lift | +0.057023839246432256 |
| Animal mean lift | +0.11415032280591153 |

The original fold-export statuses were **94 complete / 2 failed and retained
as zero**. Across the downstream evaluation, **23 pairs had at least one
failed fold**. The latter includes evaluation-stage issues and does not imply
23 separate original GBIF fetching failures.

The *secondary descriptive* mean lift by radius was +0.00619 (1 km),
+0.01677 (2 km), +0.03214 (5 km) and +0.08559 (10 km). These descriptive
radii are not a newly preregistered collection of independent significance
tests. All five-fold pair-level inferences must retain declared failures
rather than selecting only successfully evaluated pairs.

## Optional post hoc heterogeneity audit

The source-identical [descriptive heterogeneity report](ORIGINAL_V2_HETEROGENEITY_DESCRIPTIVE.md)
gives the 54/17/25 positive/zero/negative distribution of the original
96 pair means, regional summary, failure pathways and four distance
scales. These are exploratory descriptions of the already-opened cohort;
the preregistered overall effect, inferential status and fixed failures
are unchanged. Regional differences are **not** causal ecological
comparisons or new confirmatory hypotheses.

## Two original executions and the effective random-seed offset

The [source-locked comparison](ORIGINAL_V2_RANDOM_BASELINE_PARITY.md)
checks the authentic prior successful run **32336724090** against the
official corrected run **32337884576**. Source history shows an
offset-991 random-baseline implementation correction, not a change to
the validated patch-selection rule. All 1,920 fold-by-radius
deterministic support/held-out fields are unchanged; only
same-size random-reference means and derived lift differ. The original
10-km mean lift was +0.084753 before and +0.085587 after correction,
with positive confidence interval and frozen gate PASS in both runs.

These are *related executions of the same 96-pair cohort*, not a
new independent replication or a controlled fixed-input RNG experiment,
because no original full GBIF occurrence rows were archived.

## Explicit boundary that has not been resolved

The original results ZIP contains exactly these six data files:
`confirmation-folds/export_manifest.json`,
`confirmation-folds/pair_export_status.csv`,
`confirmation-results/confirmation_fold_results.csv`,
`confirmation-results/confirmation_pair_results.csv`,
`confirmation-results/confirmation_radius_summary.csv`, and
`confirmation-results/confirmation_summary.json`.

It does **not** contain `training_occurrences.csv`,
`held_out_occurrences.csv`, the exact original `gbifID` list,
the record-level `datasetKey` inventory, or a historical GBIF download DOI.
Those original inputs are **still not recovered**. Identical historical
outputs do not prove that a new live `occurrence/search` query would
reconstruct the same species-occurrence rows. See
[`GBIF_CITATION_AND_INPUT_PROVENANCE.md`](GBIF_CITATION_AND_INPUT_PROVENANCE.md)
for the separate data-citation blocker and safe recovery procedure.

## Replay, offline and without changing science

Save the two exact original ZIPs to a local directory. Then run:

```bash
python research/replay_original_robust_patch_v2_artifacts.py \
  --cohort-zip path/to/acsp_original_cohort_20260820.zip \
  --results-zip path/to/acsp_original_confirmation_results_20260820.zip
```

The replay routine verifies both **whole-ZIP** SHA-256 hashes and **all ten
internal file hashes** before parsing. It checks pair identities, the
96 × 5 × 4 declared row grid, the 94/2 original export counts, 23 pairs
with any failed fold, paper Table 1 values and original frozen inference
seeds. It computes bootstrap CI and sign-flip p anew. A mismatched or
missing original ZIP fails closed.

A CI self-test that reads only the committed receipt does **not** stand in
for a genuine replay from the original ZIPs. The 2026-10-28 original-byte
run performed the latter separately.

**Scientific claim ceiling:** independently repeated historical
**result-table inference** at the validated Japanese 10-km regional scale.
This is neither a new raw occurrence-data reconstruction nor an additional
prospective field test, and neither a proof of occupancy nor evidence
that country/global transfer passed its earlier failed gates.
