# Future independent ACSP cohort: private GBIF Search API snapshot v1

**Status (2026-10-29): implemented for new cohort preparation with synthetic tests only. No fresh biological results, verified live provider fetch, archive DOI, or historical input recovery.**

The 2026-08-20 Japan confirmation of 96 taxon–region pairs and 480 folds remains unchanged. The exact old training and held-out GBIF records were not recovered from six checked historical Actions archives. The separate [candidate-backup structural gate](ORIGINAL_GBIF_INPUT_CANDIDATE_GATE.md) is for an authenticated *possible old* input backup. **This utility must never replace or claim to restore those records.**

## What the new tool freezes

[research/freeze_prospective_gbif_search_source_v1.py](../research/freeze_prospective_gbif_search_source_v1.py) consumes **already captured GBIF occurrence/search JSON response pages** and caller-provided query metadata. It does not make a GBIF request, select patches or open held-out outcomes.

For each capped, offset-zero request, it verifies a separate new-cohort protocol hash, declared UTC capture time, mandatory GBIF search filters, response offset and limit, source records' exact integer **gbifID**, **datasetKey** UUID, license and valid coordinates, and uniqueness of record IDs. An optional private text file listing the **actual analysis-used GBIF IDs** must be a subset of the original fetched records. All validation occurs before archive creation.

The output consists of two different objects:

- **Private deterministic ZIP, outside the public Git checkout:** original input manifest bytes, every raw response exactly as captured, a SHA-256 digest list, contributor datasetKey and license counts, and optionally the precise analysis-used ID list and contributor counts. This contains sensitive locations and is **not for public GitHub**.
- **Public coordinate-free JSON receipt:** original-manifest/response/ZIP hashes, aggregate record and contributing-dataset counts, whether exact used IDs were separately supplied, and explicit assertions that provider origin, a persistent archive URL, a GBIF DOI and the August 2026 original data are **not verified**. It contains no taxon names, GBIF IDs, datasetKey lists or precise coordinates.

The tool refuses to overwrite existing snapshots or to create the private ZIP under this repository. The snapshot represents the caller-supplied original bytes; a claimed capture timestamp is **not** independently provider-attested.

## Example of a private input manifest

This example is deliberately fictitious. Its protocol hash, taxonKey and timestamp must be replaced with the actual values in a separately preregistered new experiment.

~~~json
{
  "schema_version": "acsp-new-prospective-gbif-search-capture-v1",
  "purpose": "new-independent-cohort-only-not-2026-08-20",
  "frozen_protocol_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "capture_time_declared_utc": "2026-10-29T08:00:00Z",
  "pages": [
    {
      "path": "first_page_001.json",
      "query": {
        "taxonKey": 12345,
        "country": "JP",
        "limit": 150,
        "offset": 0,
        "hasCoordinate": "true",
        "hasGeospatialIssue": "false",
        "occurrenceStatus": "PRESENT"
      }
    }
  ]
}
~~~

The file **first_page_001.json** must contain the actual *unmodified* GBIF response with offset, limit, count, endOfRecords and results. Preserve that page at the time it is returned; do not recreate the response later using an evolving Search API.

## Run on a secure local system

~~~bash
python research/freeze_prospective_gbif_search_source_v1.py \
  --manifest /private/new-cohort/capture_manifest.json \
  --private-archive /private/new-cohort/source_snapshot_v1.zip \
  --public-receipt /private/new-cohort/source_receipt_v1.json
~~~

If the **pre-outcome QC and thinning process** has separately frozen the precise analysis-used records, provide a private UTF-8 file with one exact GBIF ID per line and use a *new output path*:

~~~bash
python research/freeze_prospective_gbif_search_source_v1.py \
  --manifest /private/new-cohort/capture_manifest.json \
  --private-archive /private/new-cohort/source_snapshot_with_used_ids.zip \
  --public-receipt /private/new-cohort/source_receipt_with_used_ids.json \
  --used-gbif-ids /private/new-cohort/analysis_used_gbif_ids.txt
~~~

A frozen raw fetch inventory is **not automatically the same as the exact records used after QC**. Even when the used-ID file is supplied, an authentic signed timestamp or trusted storage lineage is required to attest when the input was collected. No original provider identity is authenticated by a self-computed checksum alone.

## Exact source-to-cleaned input parity (separate offline gate)

The [cleaned used-record bridge](PROSPECTIVE_GBIF_USED_ROW_BRIDGE.md)
checks a **new** independently frozen GBIF source ZIP with its exact
private analysis-used ID list against a separate cleaned occurrence
CSV. It verifies GBIF ID identity, original location coordinates
and contributing datasetKey/license attribution. Fetched IDs are
**not** silently treated as used IDs after QC, thinning or
held-out partition construction.

The audit publishes only file hashes and aggregate counts. It does
not attest that the used-ID list was prepared before outcomes,
prove provider origin or recover August 2026 raw inputs. Both steps
are synthetic-only in CI; a later live new study requires its own
preregistered cohort and private source snapshots.

## GBIF dataset citation and release boundary

GBIF's [citation guidelines](https://www.gbif.org/citation-guidelines) say that Search API calls do not automatically receive a Download DOI. Its [Derived Dataset guidance](https://www.gbif.org/derived-dataset/about) requires contributing dataset DOI/datasetKey information (ideally counts), a persistent URL of the extracted dataset, its preparation description, and account-authenticated registration.

This tool prepares a source-attribution inventory that can later support review, but it **does not**: register a derived dataset, mint a DOI, create or verify a persistent URL, clear license/privacy restrictions, attest the provider's raw response or establish that any resulting new cohort is scientifically independent.

The later study still needs a separately frozen taxon-region sampling frame, pre-outcome source capture and used-record inventory, declared outcome leakage boundaries, matched baseline and failed-fold rules, and prospective review of source licenses. Never use a fresh record snapshot to claim the 2026 Japanese confirmation has been exactly reproduced from original GBIF inputs.

## Automated tests and claims

[Dedicated CI](../.github/workflows/acsp-prospective-gbif-source-capture.yml) runs only **invented synthetic GBIF rows** plus the frozen ACSP paper-alignment checks. It does not access GBIF, upload private source pages, change any of the validated 2.5%/float32/1-km patch generation, or create a new ecological result.

This is a future **data integrity capability** rather than an expansion of ACSP's published biological claim.
