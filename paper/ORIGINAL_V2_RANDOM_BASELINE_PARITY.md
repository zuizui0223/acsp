# ACSP original v2: two historical executions and the random-baseline seed offset

**Status (2026-10-28): SOURCE-PINNED HISTORICAL EXECUTION COMPARISON, NOT AN INDEPENDENT REPLICATION.**

This note reconciles two authentic successful executions of the *same frozen*
96 taxon–region-pair Japanese confirmation. The official result, frozen
10-km primary estimand, 2.5%/float32/1-km non-ranked patch method, and
country/global transfer endpoints remain unchanged.

## Exact original execution lineage

| Item | Earlier successful run | Official corrected run |
|---|---|---|
| GitHub Actions | [32336724090](https://github.com/zuizui0223/acsp/actions/runs/32336724090) | [32337884576](https://github.com/zuizui0223/acsp/actions/runs/32337884576) |
| Start (UTC) | 2026-08-20 05:44:04 | 2026-08-20 06:01:40 |
| Completed (UTC) | 2026-08-20 06:19:10 | 2026-08-20 06:38:08 |
| Head commit | [\`df6277f4d9e8b3e36a5dad1730affb8db69da48a\`](https://github.com/zuizui0223/acsp/commit/df6277f4d9e8b3e36a5dad1730affb8db69da48a) | [\`39c9e6853f8d8aeffe42acd1258fe4f8f936f009\`](https://github.com/zuizui0223/acsp/commit/39c9e6853f8d8aeffe42acd1258fe4f8f936f009) |
| Original artifact ID | **9395679418** | **9396133154** |
| SHA-256 of source ZIP | \`7b7bc3dd069c948bb7c63254b3e50e2822d3a8bbe51bd3a4f245dd04aad297f3\` | \`f23c23afe4863f816f2b3a0780d9a39d6eddb383512188a0bf572dcdf055936f\` |
| GitHub result | success | success |
| Frozen statistical/guardrail gates | passed | passed |

These are **NOT** two independently sampled cohorts and **NOT** two
different scientific methods. The same run-specific source ZIP archives
and individual internal file digests are checked by the
[execution comparator](../research/audit_original_v2_seed_offset_parity.py).
Both original archive artifacts have been separately downloaded for
retention. The earlier GitHub artifact is scheduled to expire on
**2026-11-18 05:44 UTC**, the later one at **06:01 UTC** that day.

## Source-code cause and evidence limit

The immutable frozen execution describes effective random draw seeds as:

\`\`\`text
random_seed_base + pair_id * 10000 + repeat * 1009
\`\`\`

The reused dense-evaluator function
\`research/evaluate_robust_patches_on_dense_surface.py\` contains
\`np.random.default_rng(int(random_seed) + 991)\`.

The earlier runner at \`df6277f4\` passed the expression above
directly into the evaluator, giving the RNG an effective seed
**991 larger** than that described by the frozen execution JSON.
The code-only correction in commit
[\`39c9e685\`](https://github.com/zuizui0223/acsp/commit/39c9e6853f8d8aeffe42acd1258fe4f8f936f009)
passed \`frozen_effective_seed - 991\` to that evaluator, restoring
the effective seed value in the execution contract. The *validated
ecological patch-selection implementation*, support threshold, fold
denominator, region definitions, and inference criterion were not
changed in that commit. The frozen execution JSON Git blob and reused
dense-evaluator Git blob were identical between these two head commits.

**Timeline precision matters:** the fix commit was made on
2026-08-20 **06:01:34 UTC**, *after* the earlier run began but *before*
that run completed. This audit cannot establish whether any earlier
held-out results were viewed before the correction. It must **not**
call this a new untouched confirmation, a wholly pre-opening fix, or
proof of the intent behind the code correction; the commit message
and source changes are the directly observed evidence.

## Exact historical output comparison

The two original ZIPs each contain the same six output paths. Their
\`confirmation-folds/export_manifest.json\` and
\`confirmation-folds/pair_export_status.csv\` are **byte-identical**.
Pair identity, fold state, selected-cell counts, patch counts,
prototype counts, held-out counts, held-out recall, nearest-distance
diagnostics and failure reasons are **identical in all 1,920**
pair × repeat × radius rows.

Only \`random_mean_recall\` (same-size random comparison) and
\`lift_over_random\` differ. The random comparison differs in
**1,287 of 1,920** output rows, including **369 of 480** primary
10-km fold rows. At the pair level, **78 of 96** five-fold mean lifts
differ. Across the four original distance scales, the number of
random-reference rows changed is 225 (1 km), 324 (2 km), 369 (5 km)
and 369 (10 km).

| Original 10-km metric | Earlier effective seed offset | Official corrected seed |
|---|---:|---:|
| Mean held-out recovery lift | **+0.0847532680** | **+0.0855870810** |
| Pair bootstrap 95% CI | [+0.0504593493, +0.1205699316] | [+0.0511862963, +0.1216509694] |
| One-sided sign-flip p | 0.0000333322 | 0.0000333322 |
| Frozen overall confirmation gate | PASS | PASS |

Change in 10-km aggregate mean lift:
**+0.0008338130** (final minus earlier). This is **0.0834
percentage points**, not 0.0834 proportion units. The predeclared
practical gain threshold and both positive-group guardrails still pass
in the archived summary of each run. The paper correctly retains
**only the corrected official result** as its primary confirmatory
estimate, rather than averaging two related executions or counting
them as N=192.

## What cannot be concluded

Although all reported deterministic ecological/held-out fields are
equal, **the raw train/held-out occurrence CSVs are not present in
either archived result ZIP**. Both jobs fetched live GBIF records,
and we cannot establish byte-level identity of their original input
rows. Therefore the entire observed numerical difference cannot
be causally attributed *only* to the RNG correction under a controlled
fixed-input experiment. Instead, this is direct **execution-level
consistency evidence** concordant with the source-documented RNG
change. The primary zero/failure-inclusive result remains separately
verified in the frozen official archive.

This comparison is not a new ecological effect, fresh test, additional
significance test, prospective observation, biological interpretation
of islands, patch membership change, or verified global generality.
The original input-record \`gbifID\` inventory and any matching GBIF
citation DOI remain unresolved in the
[original-input provenance audit](GBIF_CITATION_AND_INPUT_PROVENANCE.md).

## Exact-source offline replay

\`\`\`bash
python research/audit_original_v2_seed_offset_parity.py \
  --prior-zip path/to/robust_v2_preceding_run_aug20_archive.zip \
  --final-zip path/to/acsp_original_confirmation_results_20260820.zip
\`\`\`

Run against the exact historical source ZIPs, not new GBIF data.
The script first fails closed on any ZIP/member SHA mismatch; it
then aligns the original 96 pairs and 480 × four distance rows and
rejects changes in any ecological/held-out field other than the
two random-baseline quantities. It reports only aggregate counts
and differences, without publishing species names, pair IDs or
sensitive survey coordinates. The reproducibility claim is limited
to the original historical **result tables**.

The dedicated GitHub workflow re-downloads the two original
artifacts while they remain available and writes a public
aggregate receipt only. Its success **cannot** reconstruct
unarchived GBIF raw occurrence records or authenticate private backups.
