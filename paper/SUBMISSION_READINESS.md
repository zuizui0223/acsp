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
```

The validator is network-free and checks:

- authoritative constants in `acsp/validated_robust.py`;
- exact values in the primary robust confirmation table;
- exact values and terminal statuses in the transfer-boundary table;
- frozen country-transfer and provider-abort JSON records;
- bounded manuscript language;
- separation and preservation of the historical Top-5 package.

Repository CI also runs `tests/test_robust_patch_submission_alignment.py`.

## Files ready for scientific review

- `paper/MANUSCRIPT_ROBUST_PATCH_DRAFT.md`
- `paper/generated/table_1_robust_patch_confirmation.csv`
- `paper/generated/table_2_robust_patch_transfer_boundary.csv`
- `paper/validate_submission_alignment.py`
- `tests/test_robust_patch_submission_alignment.py`

## Remaining editorial work

These tasks do not authorize new scientific tuning or reopening consumed cohorts:

1. Select the final journal article type and apply its heading, length, abstract, data-availability, and reference style.
2. Replace the repository placeholder with an immutable release DOI and add GBIF dataset citations for the frozen snapshots.
3. Complete the CRediT author-contribution statement and competing-interest declaration.
4. Decide whether the transfer-boundary table is a main-text table or a figure plus supplementary audit table.
5. Perform line-level English editing without changing estimands, denominators, terminal statuses, or claim ceilings.

## Hard stop

Submission completion does not require a global positive. Do not rescue the provider-aborted cohort, relax the fresh temporal-evaluability gate, promote the conditional country-framed effect, or reintroduce ranking/routing/SDM components into the validated patch membership. Any new global end-to-end experiment requires a separately frozen protocol and fresh identities.
