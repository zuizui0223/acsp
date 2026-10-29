# Byte-original ACSP development source versus independent confirmation cohort

**2026-10-29 — source-authenticated recovery of DEVELOPMENT inputs. The August 20 untouched CONFIRMATION occurrence inputs remain unrecovered.**

An earlier [historical development run](https://github.com/zuizui0223/acsp/actions/runs/32258117404)
(2026-08-19, artifact **9367472075**) still held real training and
held-out GBIF occurrence CSVs. Its authentic source ZIP was downloaded,
SHA-256-verified and compared *only at the cohort-identity level* with
the actual [96-pair untouched confirmation identity archive](https://github.com/zuizui0223/acsp/actions/runs/32335791948)
(2026-08-20, artifact **9394691112**). The source identity comparison
used both original **scientific names** and original **GBIF speciesKey**
values; neither list is published.

| Data layer | Authenticated original source | Taxa | Folds containing full occurrence inputs |
|---|---|---:|---:|
| Mixed historical development | 2026-08-19 original ZIP | 8 (4 plants/4 animals) | 40 |
| Plant historical development | Same original ZIP | 8 plants | 40 |
| **Total original development** | [run #32258117404](https://github.com/zuizui0223/acsp/actions/runs/32258117404) | **16** | **80** |
| **Independent Japan confirmation** | [run #32335791948](https://github.com/zuizui0223/acsp/actions/runs/32335791948) | **96** | **Original source CSVs not preserved in confirmed result archives** |

### Proven facts from original bytes

- Development original ZIP: SHA-256
  `46ca48bfa6be30e7302f1671b824e4a4f73da5040fb738fe44512b58806ba76a`;
  **368 archive members**, original Actions artifact **9367472075**.
- Independent cohort identity ZIP: SHA-256
  `cc0f949649491439f91e1b90d01d48acbd3f7fffc6833a75105a3bc175a5faf3`;
  original Actions artifact **9394691112**.
- **Zero overlap** between 16 development taxa and 96 confirmation taxa
  by *both* scientific name and GBIF `speciesKey`; no new taxa were
  retrospectively selected, and no outcome observations were opened.
- The original 80 development folds each contained
  `fold_manifest.json`, `training_occurrences.csv`,
  `held_out_occurrences.csv` and a `candidates.csv`.
  Per-file SHA-256 hashes in all 80 original fold manifests match the
  exact original files (240 train/held-out/candidate files).
- The original fold CSVs retain actual `gbifID`, `_gbif_id`,
  `_row_id` and coordinates. Training and held-out GBIF IDs do not
  overlap within a fold. The complete source-record pool for each
  development taxon is stable across its five folds.
- The repeated 80 folds contain **9,660 training-row appearances** and
  **1,965 held-out-row appearances**, corresponding to **2,325**
  pair-level unique source-record rows summed once per taxon. These
  represent repeated train/test partitions, **not 11,625 distinct
  occurrences**. The originally cleaned CSVs do **not** retain
  contributor `datasetKey`.

### Why this matters — and what it does NOT prove

This strengthens a crucial **development-to-confirmation leakage
boundary**: the recovered historical development taxon identities
are disjoint from the previously declared untouched Japanese
confirmation cohort. It does **not** prove all methodological
independence conditions (e.g., no global hyperparameter inspection of
the confirmation distribution); those require other protocol evidence.

Most importantly, development originals **cannot replace**
the August-20 confirmed 96-pair train/held-out inputs: the source
cohorts differ in taxon identity and study stage, and the archived
development folds were used for exploratory model selection. Reusing
them as a new independent confirmation, retrofitting GBIF dataset
citations, or presenting the 80 folds as an extension of the
480-fold confirmatory denominator would be invalid.

The official **10-km Japanese primary effect +0.0855870810** (95%
pair-bootstrap CI [+0.051186, +0.121651]) and its non-ranked
2.5%-consensus/float32/1-km robust patch method remain unchanged.

### Privacy, provenance and reuse

The [source-byte auditing script](../research/audit_original_development_input_disjointness.py)
checks the exact original ZIP hashes, all 16 original taxon identities,
80 fold manifests, per-input hashes, counts and used IDs in memory,
but outputs **aggregate, coordinate-free results only**. The
[public receipt](../validation/acsp_20260819_original_development_fold_source_audit_20261029.json)
contains no taxon list, record ID or precise geographic coordinates.
The original development ZIP itself contains original coordinates and
must be retained in **restricted storage**; do not add it to public Git
or upload it to public Actions artifacts.

This dataset is new evidence of original **development-data
preservation** and taxon-set separation, not original 2026-08-20
confirmation-input recovery, a verified GBIF Derived Dataset DOI, a
new biological result or broader global product validity.

```bash
python research/audit_original_development_input_disjointness.py \
  --development-zip /private/ACSP_development_fold_cache_20260819.zip \
  --confirmation-cohort-zip /private/acsp_original_cohort_20260820.zip \
  --verify-saved validation/acsp_20260819_original_development_fold_source_audit_20261029.json
```

The original development artifact was available on 2026-10-29
and was scheduled to expire on **2026-11-17 13:26:41 UTC**.
Its source archive has been separately preserved in the private
personal `/acsp/` file library; this archive is not automatically
licensed for unrestricted public redistribution.
