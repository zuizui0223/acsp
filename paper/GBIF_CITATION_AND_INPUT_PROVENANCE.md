# GBIF input citation and exact-data provenance gate — 2026-10-26

**Status:** **ORIGINAL_INPUT_CITATION_NOT_YET_RECOVERED.** This is a
source-code and committed-artifact audit, **not** a new GBIF query, field
result, retrospectively repaired validation, a claim that the original
GBIF occurrence records no longer exist anywhere, or a public release.

## Confirmed source-to-output chain

1. The frozen cohort-definition receipt in
   [`validation/acsp_robust_patch_untouched_confirmation_execution_v2.json`](../validation/acsp_robust_patch_untouched_confirmation_execution_v2.json)
   identifies **96 taxon–region identities** (pre-outcome GitHub Actions
   run **32335791948**, cohort artifact **9394691112**, ZIP digest
   `cc0f949649491439f91e1b90d01d48acbd3f7fffc6833a75105a3bc175a5faf3`).
   This artifact is a frozen identity frame, **not** a GBIF occurrence
   snapshot.
2. The primary input exporter
   [`research/export_robust_patch_confirmation_folds_v2.py`](../research/export_robust_patch_confirmation_folds_v2.py)
   calls `fetch_occurrences(row, 150)` from
   [`research/benchmark_general_random_taxa_regions.py`](../research/benchmark_general_random_taxa_regions.py).
   That function calls the live **`https://api.gbif.org/v1/occurrence/search`**
   endpoint, with taxonKey, rectangular polygon, coordinate and
   geospatial-quality filters, occurrenceStatus=PRESENT, **offset=0**
   and a fixed **maximum of 150** records per taxon–region. A
   live search request **does not generate a GBIF occurrence download DOI**.
3. [`gbif_fieldmap_builder_app.py`](../gbif_fieldmap_builder_app.py)'s
   `gbif_record_to_species_row()` transfers the public `gbifID` (or
   `key`) into cleaned rows, but **does not transfer `datasetKey`**.
   `clean_occurrences()` adds `_gbif_id`. The exporter writes
   temporary **training_occurrences.csv** and **held_out_occurrences.csv**
   per fold; thus identifiers can be present in those temporary inputs,
   but they are **not preserved in the named public upload paths**.
4. The original
   [`robust-patch-untouched-confirmation-v2.yml`](../.github/workflows/robust-patch-untouched-confirmation-v2.yml)
   uploads **only** `confirmation-folds/export_manifest.json`,
   `confirmation-folds/pair_export_status.csv`, and
   `confirmation-results/`. It does **not** upload the per-pair
   training/held-out occurrence CSV trees. Artifact retention was
   specified as 90 days. There may be privately retained originals,
   external archives, or other source files that this specific public
   contract cannot verify.
5. The **frozen analysis result** is still supported as reported:
   96 taxon-region pairs, 480 declared folds, 10-km mean lift over
   same-size random patches **+0.08558708102617191** (95% CI
   **[+0.051186296271122624, +0.12165096941745603]**). An inability
   to cite exact original provider records is a **data-provenance
   limitation**, not a new statistical null or license to retune the
   original cohort.

## Verified recovery of original **results**, not source records (2026-10-28)

The original historical GitHub Actions ZIPs were retrieved on 2026-10-28,
with GitHub-reported and locally computed SHA-256 digests matching
**byte-for-byte**. The frozen identity cohort is from
[run #32335791948](https://github.com/zuizui0223/acsp/actions/runs/32335791948)
(artifact 9394691112); the independent result archive is from
[run #32337884576](https://github.com/zuizui0223/acsp/actions/runs/32337884576)
(artifact 9396133154). The latter contains 96 pair summaries and 1,920
fold-by-radius output rows. Recomputing the original 30,000-draw
pair-bootstrap and one-sided sign-flip test with the **frozen seeds**
exactly reproduced the published primary effect, CI and p-value.

**This resolves result-table provenance, not original observation
provenance.** Neither recovered ZIP includes the original
`training_occurrences.csv`, `held_out_occurrences.csv` or the exact
historical GBIF ID/datasetKey inventory. The GBIF citation gate above
therefore remains **OPEN**. The separate
[replay note](ORIGINAL_V2_RESULT_ARCHIVE_REPLAY.md) and
[byte-level receipt](../validation/acsp_original_v2_archival_reconciliation_20261028.json)
provide exact hashes and replay instructions. GitHub lists both original
artifact ZIPs as scheduled to expire on **2026-11-18 (UTC)**; do not rely
on those links as permanent data archives.

## Second original successful run does not restore original input rows

A separate original successful 2026-08-20 execution ([run
#32336724090](https://github.com/zuizui0223/acsp/actions/runs/32336724090),
artifact **9395679418**, verified ZIP SHA-256
`7b7bc3dd069c948bb7c63254b3e50e2822d3a8bbe51bd3a4f245dd04aad297f3`)
was also recovered. Its cohort/fold export status files are
byte-identical to the later official archive; all 1,920
deterministic support and held-out recovery values are identical.
The GitHub source diff is consistent with an effective random-seed
offset correction between the two runs, explained in
[`ORIGINAL_V2_RANDOM_BASELINE_PARITY.md`](ORIGINAL_V2_RANDOM_BASELINE_PARITY.md).

**Neither ZIP contains the original GBIF training/held-out occurrence
rows or `datasetKey` provenance.** The identical reported
deterministic values do not prove byte identity of the earlier and
later raw GBIF searches. Original occurrence IDs and a matching
historical data citation still remain unrecovered.

## Six original-archive search outcome (2026-10-28)

The [SHA-256-verified six-archive inventory](ORIGINAL_GBIF_ARCHIVE_INVENTORY.md)
extends the original-input search to the cohort archive, both
robust-v2 success archives and geographic-framing v1/v2/v3 outputs.
**None** contains the original focal-species training/held-out
occurrence CSVs. The four original and re-exported 96-pair status
and export-manifest files are *byte-identical*, but this does not
verify that distinct live GBIF requests returned the same records.

Geographic v2 includes 7,895 genus/family-level **nonfocal** prior
locations that must not be substituted for the focal validation
input or published as part of this coordinate-free audit.
Exact GBIF record IDs/datasetKeys and a matching historical DOI
remain **unrecovered**. These results narrow the search within
GitHub Actions; they do not exhaust private backups.

## Prepared private candidate-backup integrity gate (2026-10-28)

The [offline structural validator](ORIGINAL_GBIF_INPUT_CANDIDATE_GATE.md)
can inspect any subsequently located `confirmation-folds`
backup against the authenticated original cohort/results ZIPs:
96 taxon–region identities, 480 manifest/CSV sets, archived
94-complete/2-failed counts, preserved `_row_id` record pools,
and the frozen 0.1-degree block-splitting RNG rule.

**This does not recover the original records or prove authenticity.**
No contemporaneous per-fold raw CSV hashes were retained in the
checked result ZIPs. Therefore a structurally compatible folder
cannot be relabeled the August 2026 input merely by passing these
checks. The tool reports *safe aggregate counts only*; no GBIF IDs,
taxon names or precise locations are published.

## Prospective prevention — a different source problem (2026-10-29)

For **new, separately frozen independent cohorts only**, the offline
[GBIF raw-source capture utility](PROSPECTIVE_GBIF_SOURCE_CAPTURE.md)
now preserves unmodified Search API response bytes, exact `gbifID`,
contributor `datasetKey` UUIDs, source license counts and optional
pre-outcome analysis-used IDs inside a **private ZIP**. Its public
receipt contains hashes and aggregate counts, no coordinates or
record IDs, and cannot be described as a historical original.

This makes subsequent dataset attribution possible *if* a genuinely
new source capture and used-ID freeze occur. It does **not** recover
the missing 2026-08-20 96-pair raw inputs, authenticate
caller-supplied provider response time, assign a DOI, satisfy a
persistent data URL, or turn old results into a new independent trial.

## Recovered pre-confirmation development inputs — separate data source (2026-10-29)

The [byte-original development source audit](ORIGINAL_DEVELOPMENT_INPUT_AND_COHORT_DISJOINTNESS.md)
identified a 2026-08-19 Actions artifact **9367472075** containing the
actual training and held-out GBIF CSVs for **16 development taxa /
80 folds**. All original input/candidate CSV hashes in the fold
manifests were verified; the 16 development taxa overlap with the
later 96-taxon independent cohort in **zero** scientific names
and **zero** GBIF `speciesKey` identities.

**This is development-source recovery, NOT recovery of August-20
untouched-confirmation source rows.** Development CSVs retain
`gbifID` but not contributor `datasetKey`; their identities are
different from the frozen 96. The old source-to-dataset citation
gap remains OPEN, and development data are not substituted for
confirmation input or pooled into the positive 96-pair estimate.

## What is and is not established

| Object | Status | Meaning |
|---|---|---|
| Frozen protocol/code and cohort identity metadata | Present and source-pinned | Reproducible procedure/declared sampling identities |
| Summarized confirmation output | In frozen manuscript and result records | Reported historical effect |
| Full original GBIF occurrence IDs for all 96 pairs | **Not verified in declared public results upload** | Cannot assume full exact original record set recoverable from those outputs |
| Original `datasetKey` per used record | **Dropped by frozen row converter** | Need to recover from an actual original record-ID list or original raw provider response |
| Original per-fold train/held-out CSVs | **Not in declared result upload** | Check private local/Drive/backups *without* replacing with present-day search |
| Existing GBIF download DOI matching *this* cohort | **Not verified** | Do not insert unrelated GBIF download DOI |
| Software version-specific Zenodo DOI | **Not verified** | Public GitHub commit identity alone is not a Zenodo DOI |
| New DOI or current GBIF result treated as August 2026 input | **Not acceptable** | Would falsely substitute an evolving provider state |

Separate GBIF download notification emails may exist for other research
and dates. **A DOI from an unrelated download must never be assigned to
the frozen ACSP data** solely because the account owner is the same.

## Publication-safe recovery sequence (no outcomes reopened)

1. **Recover, do not regenerate, original source inputs:** Check the
   original frozen workflow-run archive, authorised private/local
   copies, connected project storage or backups for
   `confirmation-folds/pair_*/fold_*/training_occurrences.csv` and
   `held_out_occurrences.csv`. Confirm all **480** fold directories,
   original hashes/creation context, the **96** declared taxa and
   exact artifact or machine provenance. Do not publish protected
   coordinates or rare-taxon localities.
2. **Resolve record attribution:** Extract and deduplicate original
   `gbifID` values **only after source authentication**, keeping the
   exact old record-ID inventory immutable. Associate original
   `datasetKey` values using archived raw responses, or clearly label
   any later GBIF metadata lookup as a **2026 re-resolution**, not the
   historical provider content. Validate used, missing, obscured and
   deleted IDs. Do not silently swap records.
3. **Create an appropriate citation, only after exact input mapping:**
   Use GBIF's official occurrence download or derived dataset mechanism
   as appropriate. If GBIF's derived-dataset record is created later,
   describe the difference between **historically used input records**
   and **newly archived citation inventory**. Preserve contributor
   dataset identities, count and license attribution. Multiple distinct
   download DOIs can be listed in a supplementary data-citation table.
4. **If no authentic originals exist:** Preserve the existing
   evaluation as an explicitly bounded historical result; disclose
   that the exact record snapshot is not archived in the present
   public reproduction package. A **fresh** input download/new cohort
   is a new analysis, not retroactive verification of the 480 historical
   folds. Do not assert exact replication by re-running an evolving
   `occurrence/search` endpoint.
5. **Software release:** The public repository's Git commit can be
   cited by immutable commit URL. To obtain a version DOI, the owner
   should first verify author metadata and connect the public repository
   to an archiving service (e.g. Zenodo), then create a **deliberate**
   GitHub Release and verify the DOI issued for those actual bytes.
   Neither `CITATION.cff`'s `ACSP Developers` nor a guessed DOI is
   sufficient for author contributions.

## Official public guidance

- GBIF citation guidelines:
  https://www.gbif.org/citation-guidelines
  (GBIF recommends derived datasets for records retrieved with the
  Occurrence Search API and no assigned download DOI).
- GBIF occurrence API documentation:
  https://techdocs.gbif.org/en/openapi/v1/occurrence
- GitHub/Zenodo persistent identifiers:
  https://docs.github.com/en/repositories/archiving-a-github-repository/referencing-and-citing-content

## Manuscript correction and boundaries

The previous availability paragraph claimed that exact external
occurrence snapshots were fully identified by recorded run/artifact
digests. That was too broad: **cohort identities and aggregated
results are documented, while exact raw fold input archives have not
been verified.** The corrected paragraph in
[`MANUSCRIPT_ROBUST_PATCH_DRAFT.md`](MANUSCRIPT_ROBUST_PATCH_DRAFT.md)
now explicitly distinguishes these.

Do not change the original 2.5% support threshold, 1-km patch
aggregation, 96×5 denominator, 10-km effect, comparator, independent
confirmation outcome, or country-framed/global STOP results. This is a
data-availability/citation correction, **not** new field or ecological
confirmation.

```bash
python paper/audit_gbif_citation_provenance.py
python paper/validate_submission_alignment.py
python paper/validate_submission_packet.py
python -m unittest discover -s tests -p 'test_gbif_citation_provenance.py' -v
```

A successful audit still reports `journal_submission_ready=false`
because the source-record DOI and approved author metadata are
missing. It is a reproducible description of the gap rather than
manufactured bibliographic completeness.
