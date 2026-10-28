# Robust candidate-patch submission readiness

## Current state

The submission-facing scientific object is now aligned with the authoritative validated ACSP product:

```text
occurrence-conditioned environmental support
        ↓
leave-one-prototype-out robust support
        ↓
frozen 2.5% consensus tier
        ↓
1 km same-area complete-link aggregation
        ↓
non-ranked bounded candidate patches
```

The current manuscript does not replace the historical finite Top-5 paper. Both are retained because they answer different questions:

- `MANUSCRIPT_ROBUST_PATCH_DRAFT.md` — current submission-facing candidate-patch paper;
- `MANUSCRIPT_DRAFT.md` — preserved historical Top-5 decision-policy paper and comparator provenance.

## Scientific terminal decisions included

1. **Validated Japanese core — PASS**
   - 96 taxon-region pairs;
   - 480 declared folds;
   - 10-km mean lift over same-size random patches: `+0.08558708102617191`;
   - 95% CI: `[+0.051186296271122624, +0.12165096941745603]`;
   - one-sided sign-flip `p = 3.333222225925803e-05`;
   - plant and animal means both positive.

2. **Reserved country-framed replication — FAIL, 6/7 gates**
   - positive mean lift `+0.08960843345273417`;
   - 95% CI lower bound `-0.0024797646968568506`;
   - no global promotion.

3. **Fresh country-framed confirmation — FAIL, 6/7 gates**
   - positive mean lift among integrated-evaluable taxa `+0.1322978884579088`;
   - positive 95% CI;
   - temporal evaluability `34/48 = 0.7083`, below the frozen `0.75` gate;
   - no global promotion.

4. **Provider-eligible observability first activation — ABORT / NOT EVALUABLE**
   - 6,147 candidate rows frozen;
   - 3,161 historical provider queries;
   - 29 HTTP 429 failures;
   - no complete 96-frame artifact;
   - 2021–2025 heldout unopened;
   - hypothesis unavailable, not negative.

## Alignment guard

Run from the repository root:

```bash
python paper/validate_submission_alignment.py
python -m unittest discover -s tests -p "test_robust_patch_submission_alignment.py" -v
```

Both checks are network-free. The validator checks:

- authoritative constants in `acsp/validated_robust.py`;
- exact values in the primary robust confirmation table;
- exact values and terminal statuses in the transfer-boundary table;
- frozen country-transfer and provider-abort JSON records;
- bounded manuscript language;
- separation and preservation of the historical Top-5 package.

Repository CI runs the same alignment test as part of the ordinary test suite.

## Files ready for scientific review

- `paper/MANUSCRIPT_ROBUST_PATCH_DRAFT.md`
- `paper/generated/table_1_robust_patch_confirmation.csv`
- `paper/generated/table_2_robust_patch_transfer_boundary.csv`
- `paper/validate_submission_alignment.py`
- `tests/test_robust_patch_submission_alignment.py`

## Provisional editorial packet prepared (2026-10-25)

The new optional [editorial handoff](SUBMISSION_EDITORIAL_HANDOFF.md)
includes five ≤85-character candidate Highlights, a shorter alternative
abstract, a draft cover letter, a claim-boundary audit and six network-free
regression tests. These are **review materials, not an actual journal
submission or replacement of this validated manuscript**.

```bash
python paper/validate_submission_alignment.py
python paper/validate_submission_packet.py
python -m unittest discover -s tests -p 'test_submission_packet.py' -v
```

The draft packet always reports `author_submission_ready=false`. The
journal-specific Guide for Authors still requires live author verification,
and the repository has no confirmed final DOI, approved coauthor CRediT
roles or completed competing-interest declarations.

## Exact-input citation gap audited (2026-10-26)

[`GBIF_CITATION_AND_INPUT_PROVENANCE.md`](GBIF_CITATION_AND_INPUT_PROVENANCE.md)
documents that the primary 96-pair validation used GBIF's live
`occurrence/search` API (no automatic download DOI), retained
`gbifID` but not the source `datasetKey`, and did not include the
original per-fold occurrence CSV files in the specified public
GitHub Actions artifact upload. The previous manuscript claim of
fully identified external occurrence snapshots has been corrected.

The author-side next input is an authenticated copy of the **original**
fold data/record-ID inventory, not an arbitrary fresh GBIF query.
Original validation and all its statistics remain frozen.

```bash
python paper/audit_gbif_citation_provenance.py
```

A passing audit means only that this known provenance problem is
reproducibly disclosed. It is **not** evidence of complete raw-data
archiving or DOI attribution; submission remains blocked on the
honest publication-data decision and author declarations.

## Original confirmation result archive recovered (2026-10-28)

Both original 2026-08-20 GitHub Actions archives have been recovered
and independently verified against original SHA-256 digests. From
the original 96 pair summaries and 1,920 fold-by-radius output rows,
the frozen +0.085587 10-km mean lift, 95% CI and sign-flip p were
recomputed **exactly**, including failures retained in the denominator.
The [source-verified replay note](ORIGINAL_V2_RESULT_ARCHIVE_REPLAY.md)
records original run IDs, ZIP/member hashes and the offline replay method.

**Important remaining blocker:** The results ZIP does **not** contain
the original GBIF occurrence training/held-out rows. No matching
historical GBIF download DOI or original record-ID list has been recovered.
This is not a completed raw-data or software archive and does not satisfy
the unresolved author-approval and dataset-citation gates.

## Failure-inclusive descriptive heterogeneity supplement (2026-10-28)

An optional [original-v2 descriptive report](ORIGINAL_V2_HETEROGENEITY_DESCRIPTIVE.md)
documents that the **96-pair mean** improvement is not identical across
taxa (54 positive, 17 zero, 25 negative pair means). Among 480 primary
10-km fold results, 105 had explicit failure/empty support recorded as
zero. The report describes 12 regional frames and four radii without
additional hypotheses or significance tests.

The source-bounded script and fixed public aggregate receipt must agree
exactly on the original byte-authenticated GitHub results ZIP. This
document does not promote the 1/2/5-km descriptive effects or regional
contrasts to independent evidence, and does not repair the still-missing
GBIF original occurrence rows or attribution DOI.

## Original run-level random-baseline parity audit (2026-10-28)

The [two-source execution comparison](ORIGINAL_V2_RANDOM_BASELINE_PARITY.md)
documents an original prior successful run (mean +0.084753) and the
official corrected run (mean +0.085587). Exact source comparison
shows the frozen evaluator added 991 internally to the random draw
seed, and the corrected runner subtracted 991. Across 1,920 output
rows, ecological support, candidate patch counts, held-out recall,
failures and other deterministic fields were unchanged; only the
same-size random baseline and derived lift differed. **Both frozen
confirmation gates passed.**

This is not a second independent cohort or a new hypothesis test,
and original GBIF input rows are absent from both result archives.
Only the official corrected estimate is used in the submitted
manuscript; no effect estimate or confidence interval was rewritten.

## Original GBIF input archival search — source-limited negative (2026-10-28)

The [six-archive inventory](ORIGINAL_GBIF_ARCHIVE_INVENTORY.md)
examined SHA-256 authenticated historical cohort, two
confirmation and three geographic-framing source ZIPs. It found
**no** original focal-species train/held-out CSVs or a matching
historical GBIF DOI. The four common 96-pair export-status
files and manifests are byte-identical, but do not prove
original input record identity. Geographic v2's 7,895
coordinate-bearing rows are **nonfocal prior data**, not
recoverable primary occurrence inputs.

This clarifies the outstanding source-record provenance gate:
an authenticated private backup of the actual August 2026
focal input (or an equivalent immutable historical record-ID
inventory) is still required for exact dataset attribution.
It does **not** modify the independently recomputed result
inference or the existing statistical manuscript claim.

## Remaining editorial work

These tasks do not authorize new scientific tuning or reopening consumed cohorts:

1. Select the final journal article type and apply its heading, length, abstract, data-availability, and reference style.
2. Replace the repository placeholder with an immutable release DOI and add GBIF dataset citations for the frozen snapshots.
3. Complete the CRediT author-contribution statement and competing-interest declaration.
4. Decide whether the transfer-boundary table is a main-text table or a figure plus supplementary audit table.
5. Perform line-level English editing without changing estimands, denominators, terminal statuses, or claim ceilings.

## Hard stop

Submission completion does not require a global positive. Do not rescue the provider-aborted cohort, relax the fresh temporal-evaluability gate, promote the conditional country-framed effect, or reintroduce ranking/routing/SDM components into the validated patch membership. Any new global end-to-end experiment requires a separately frozen protocol and fresh identities.
