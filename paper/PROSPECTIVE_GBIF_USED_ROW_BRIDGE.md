# Future ACSP independent cohort: exact raw GBIF to cleaned used-row bridge

**Status (2026-10-29): offline source-consistency verification and synthetic tests only. No fresh GBIF queries, field results, independent ecological confirmation, derived-data DOI, or historical original-input recovery.**

The prospective [raw source snapshot](PROSPECTIVE_GBIF_SOURCE_CAPTURE.md) freezes JSON response bytes, GBIF record IDs, `datasetKey` attribution and optional analysis-used IDs. But fetched GBIF records can be discarded by cleaning, QC or duplicate removal, so **fetched IDs are not automatically the IDs used for analysis**.

The new offline tool
[research/verify_prospective_gbif_used_rows_v1.py](../research/verify_prospective_gbif_used_rows_v1.py)
checks this distinction without inspecting held-out recovery, changing patch membership, making provider requests, or rerunning historical biological validation.

## Required private inputs

1. A SHA-256-frozen **new-cohort raw GBIF response ZIP** and its
   published coordinate-free receipt, produced by the earlier snapshot tool.
2. That ZIP must already contain its **exact private**
   `analysis_used_gbif_ids.txt` and `private_attribution.json`.
   A snapshot with only fetched records fails closed.
3. A **private post-QC used-row CSV** containing `_row_id`, exact
   `_gbif_id` or `gbifID`, and one complete coordinate pair
   (`_latitude/_longitude`, `latitude/longitude` or
   `decimalLatitude/decimalLongitude`). If columns `datasetKey`,
   `license`, `scientificName`, `eventDate`, `basisOfRecord`
   or `countryCode` are present, they must match the frozen
   original raw record.
4. An unused output path for the **coordinate-free public JSON receipt**.

## What the bridge checks

- Source ZIP SHA-256, all internal member SHA-256 hashes and the
  prospective-only original capture schema.
- Exact equality of the **cleaned used-ID set** to the private
  pre-supplied used-ID set. An arbitrary subset or fetched-only
  registry cannot be promoted to used input.
- Every GBIF ID resolves uniquely to the original JSON record;
  neither IDs nor cleaned source row ordinals may be duplicated.
- Every present coordinate alias matches the original raw latitude
  and longitude to 1e−9 degrees, allowing numeric serialization
  round trips but rejecting changed locations.
- Optional source datasetKey, license and record metadata match,
  and original contributor counts for **used** records agree with
  the private attribution inventory.

The published receipt contains only SHA-256 hashes, aggregate
record and contributing-dataset counts, and explicit false flags
for old-source recovery, provider attestation, independent
pre-outcome attestation, a derived-data DOI and biological
confirmation. **Raw IDs, datasetKey values, taxa and coordinates
remain private.** A mismatch stops before public output.

## Run offline on secure local storage

~~~bash
python research/verify_prospective_gbif_used_rows_v1.py \
  --source-private-zip /private/new-cohort/source_snapshot_with_used_ids.zip \
  --source-receipt /private/new-cohort/source_receipt_with_used_ids.json \
  --cleaned-used-csv /private/new-cohort/used_cleaned.csv \
  --public-receipt /private/new-cohort/used_row_bridge_receipt.json
~~~

Do not upload either source ZIP or cleaned CSV into the public
ACSP repository or into a public CI run. The dedicated
[synthetic-only CI](../.github/workflows/acsp-prospective-used-row-bridge.yml)
makes invented source records and checks the positive path,
ID/coordinate substitution, alternate coordinate columns,
datasetKey/license mismatch, ZIP tampering and output non-overwrite.

## Scientific and provenance boundaries

This is an **input-consistency check, not an original GBIF source
authentication**. It cannot independently verify that the
caller-supplied JSON came from GBIF, that the declared capture
timestamp is correct, or that a used-ID inventory was frozen
before any held-out outcome was inspected. These need an
external trusted timestamp/immutable deposit or independent audit log.

It also does not determine the scientific validity of a QC
filter or spatial thinning rule, establish a new independent
taxon cohort, clear source licensing and sensitive-location
redistribution constraints, or issue a GBIF Derived Dataset
DOI. The [GBIF citation guidance](https://www.gbif.org/citation-guidelines)
remains a separate authenticated publication workflow.

**The original August 2026 Japanese validation is unchanged:**
96 taxon-region pairs, 480 folds, 2.5% float32 support and
1-km non-ranked patches, with original mean 10-km recovery lift
+0.085587. Its original GBIF training/held-out input rows
are still **unrecovered**. A newly matched future source
cannot be used as the historical input or as new ecological
evidence by itself.
