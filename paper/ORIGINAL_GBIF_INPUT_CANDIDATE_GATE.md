# Original GBIF fold-input recovery: private candidate verification gate

**2026-10-28 — ready for an authenticated original backup, if one is found.**

The original 2026-08-20 confirmatory ACSP v2 run generated
**96 taxon–region pairs × five folds = 480** temporary folders with
`fold_manifest.json`, `training_occurrences.csv` and
`held_out_occurrences.csv`. These per-fold source CSVs were **not**
included in the six GitHub Actions ZIPs inspected in
[`ORIGINAL_GBIF_ARCHIVE_INVENTORY.md`](ORIGINAL_GBIF_ARCHIVE_INVENTORY.md).
No exact contemporaneous GBIF occurrence-source archive has yet been
verified.

The offline utility
[`research/audit_candidate_original_gbif_folds.py`](../research/audit_candidate_original_gbif_folds.py)
provides a way to check any subsequently located **candidate** backup
without reopening the biological analysis, calling the present-day
GBIF API or publishing occurrence coordinates.

## Input expected

Provide a local private directory with structure:

```text
candidate-original-folds/
  pair_001/
    fold_001/
      fold_manifest.json
      training_occurrences.csv
      held_out_occurrences.csv
    ...
    fold_005/
      ...
  ...
  pair_096/
    fold_001/ ... fold_005/
```

Plus the two verified original Actions archives (already preserved in
the project user's private file Library):

- Cohort identities from
  [run 32335791948](https://github.com/zuizui0223/acsp/actions/runs/32335791948),
  artifact 9394691112, ZIP SHA-256
  `cc0f949649491439f91e1b90d01d48acbd3f7fffc6833a75105a3bc175a5faf3`.
- Official 96-pair results from
  [run 32337884576](https://github.com/zuizui0223/acsp/actions/runs/32337884576),
  artifact 9396133154, ZIP SHA-256
  `f23c23afe4863f816f2b3a0780d9a39d6eddb383512188a0bf572dcdf055936f`.

**Do not use an October 2026 fresh GBIF download** as the August 2026
historical input. The source ZIPs are pinned; a candidate raw directory
is not known to be original until additional provenance evidence exists.

## What is actually checked

For every pair/fold, the validator checks:

1. The authoritative original cohort taxon name, taxon group, region
   and speciesKey; the frozen execution fingerprint; five fold manifests
   per declared pair.
2. The original output archive's pair-level export counts and
   statuses (**94 complete, two failed retained as zero**), including
   empty CSVs and preserved failure reasons for failed pairs.
3. Fold-manifest training and held-out record counts, a complete and
   nonduplicated `_row_id` range, disjoint train/test partitions,
   and the **same record pool across all five folds**.
4. The number and order of original 0.1-degree spatial blocks and the
   exact sequential selection rule using NumPy
   `default_rng(20260823 + pair_id)` with 20% held-out blocks.
5. The count (not values) of usable `_gbif_id`/`gbifID` fields
   and `datasetKey` fields. The legacy frozen converter did **not**
   retain `datasetKey`, so absence of that field would be expected
   and would still leave source dataset attribution unresolved.

Run locally, outside the public repository if coordinates could be
sensitive:

```bash
python research/audit_candidate_original_gbif_folds.py \
  --candidate-root /secure/path/to/candidate-original-folds \
  --cohort-zip /secure/path/to/original-cohort.zip \
  --results-zip /secure/path/to/original-official-results.zip
```

The output is aggregate counts only. It never outputs `gbifID` values,
taxon names, exact latitude/longitude or original CSV contents.
**Do not upload the source directory or the original coordinate-bearing
rows into public PRs or GitHub Actions.** Automated CI intentionally
uses **synthetic, invented test folds** and is not presented as a real
480-fold original-input recovery.

## The distinction between structural agreement and authenticity

A successful run returns
`STRUCTURALLY_CONSISTENT_CANDIDATE_BACKUP_PROVENANCE_UNAUTHENTICATED`.
Even perfect fold identity, counts and seed selections **cannot prove**
that the GBIF Search API supplied those exact records on 2026-08-20.
A differently constructed pool could pass the same structural checks.
The known original Actions result ZIP contains no contemporaneous
per-fold source CSV hashes against which to authenticate candidates.

**Evidence ladder:**

| Level | Evidence | Interpretation |
|---|---|---|
| A | Original Actions result ZIP digest and 96-pair inference | Already verified; historical **results** reproducible |
| B | A private candidate folder passes all 480 split and identity checks | Structurally consistent backup; **historical origin unproven** |
| C | Contemporaneous original source archive and independently anchored source digest / trusted storage lineage | Historical input origin can be evaluated as authentic |
| D | Complete original `gbifID` inventory plus verified `datasetKey`/publisher DOIs and persistent appropriately redacted record archive | Exact data-use citation can be assembled and reviewed |
| E | Fresh independently predeclared cohort with prospectively frozen provider snapshot | **New** biological confirmation; not retrospective repair |

Do not jump from B to C or D. When an authenticated original source is
recovered, record its historical provenance, compare immutable hashes
and dataset contributions, and follow the
[GBIF citation guidelines](https://www.gbif.org/citation-guidelines)
and [derived dataset requirements](https://www.gbif.org/derived-dataset/about).

For a future, separate independent confirmation, a DOI-ready source
inventory should preserve `gbifID`, `datasetKey`, dataset licenses
and the exact historical fetch response or authenticated download
*at acquisition time*, before computing support or held-out recovery.
This is a prospective design recommendation; it does not modify the
frozen ACSP 2.5%/float32/1-km core, the 96-pair primary mean
+0.085587 or earlier transfer failure/abstention statuses.

## State after preparing this gate

- **No original historical GBIF record list has been recovered here.**
- No original GBIF citation DOI or software release DOI is generated.
- No new GBIF queries, refitting, field survey or hypothesis test was run.
- Structural validator and synthetic regression tests are prepared so
  an original candidate backup can be checked immediately when supplied.
