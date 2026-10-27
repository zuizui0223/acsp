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
