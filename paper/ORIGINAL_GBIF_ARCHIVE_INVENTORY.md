# Six original ACSP Actions archives: exact-input recovery audit

**2026-10-28 | status: EXACT_ORIGINAL_GBIF_INPUT_RECORDS_NOT_IN_SIX_CHECKED_ARCHIVES**

This is a **source-byte-verified recovery attempt**, not a new
GBIF download, ecological experiment, or proof that no original inputs
exist in an unexamined/private location. It does not change the
frozen Japanese ACSP primary result or candidate-generation method.

## Exact historical artifact inventory

| Historical source | Run | Artifact ID | ZIP SHA-256 | Original focal training/held-out occurrence CSVs |
|---|---:|---:|---|---|
| Frozen 96-pair cohort identities | [32335791948](https://github.com/zuizui0223/acsp/actions/runs/32335791948) | 9394691112 | `cc0f949649491439f91e1b90d01d48acbd3f7fffc6833a75105a3bc175a5faf3` | No: identities only |
| Earlier successful robust v2 | [32336724090](https://github.com/zuizui0223/acsp/actions/runs/32336724090) | 9395679418 | `7b7bc3dd069c948bb7c63254b3e50e2822d3a8bbe51bd3a4f245dd04aad297f3` | No: folded results |
| Official robust v2 | [32337884576](https://github.com/zuizui0223/acsp/actions/runs/32337884576) | 9396133154 | `f23c23afe4863f816f2b3a0780d9a39d6eddb383512188a0bf572dcdf055936f` | No: folded results |
| Geographic framing v1 re-export | [32574305976](https://github.com/zuizui0223/acsp/actions/runs/32574305976) | 9476173948 | `54ed1ccaaebc22c768fb3eb06af2cf647ac8174f07638c582e2577a58676d972` | No: fold diagnostics |
| Geographic framing v2 re-export | [32613853356](https://github.com/zuizui0223/acsp/actions/runs/32613853356) | 9486388476 | `907b9c83e49b84e9681fa9e7561345929ba655adabd6dfce58204102edbc9313` | No: fold diagnostics and **nonfocal** prior |
| Geographic framing v3 country registry | [32615062909](https://github.com/zuizui0223/acsp/actions/runs/32615062909) | 9486693473 | `92f48e8a91388d98acc152b13fe3d4ed5cb74d6454b6aa1f4f6735f7ee412ec3` | No: country counts |

Each GitHub Actions original ZIP was downloaded and its entire
SHA-256 verified. The [source-locked scanner](../research/audit_original_gbif_archive_inventory.py)
replays all six ZIPs and refuses unrecognized file counts or
unexpected source bytes. The public
[coordinate-free receipt](../validation/acsp_original_gbif_archive_inventory_20261028.json)
contains only archive IDs/hashes, safe aggregate counts and explicit
recovery-status flags.

## Four identical status files do not prove identical GBIF records

The two robust-v2 success archives and the geographic-v1 and v2
archives each contain a 96-pair `pair_export_status.csv`.
Those four files are **exactly byte-identical**, SHA-256
`55f66ba821cba0eafdcc149f04e082e0c66ecf4a51d9456c94319e158a81b7bf`.
Their `export_manifest.json` files are also byte-identical,
SHA-256 `b9e89cb8de1969ea0531c8106d3f82750aa4791bfbf7658429855b1dd1f637fd`.

The common operational status is **94/96 complete** and **2/96
failed-retained-as-zero**; the official robust-v2 archive contains
96 pair results and 1,920 fold-by-radius results.

These audit/summary files do **not** list every used `gbifID`,
`datasetKey` or input row. Identical aggregate record counts
or fold status cannot establish byte-identical input across
distinct live GBIF Search API calls.

## Why geographic v2's 7,895 points cannot supply the missing input

The geographic-v2 artifact contains
`higher_taxon_prior_points.csv` with **7,895 rows** of
**genus/family-level nonfocal reference locations**. Its companion
96-pair audit shows **94 completed pairs explicitly marked as
NOT using focal training or focal held-out coordinates**, with
two inapplicable failed pairs. The prior points have no `gbifID`
or `datasetKey` fields and do not represent the original
focal-species records. **No coordinate row from that file has
been copied into the public receipt or report.**

Geographic v3 contains country registry summaries and counts
rather than the original source-record list. Its country totals
are useful for later geographic-framing development, not for
retroactively identifying the records that produced the
2026-08-20 frozen confirmation.

## Citation consequence and next legitimate input

GBIF's [official citation guidelines](https://www.gbif.org/citation-guidelines)
recommend a *derived dataset* for data accessed via the
Occurrence Search API, while the
[derived-dataset registration requirements](https://www.gbif.org/derived-dataset/about)
call for a list of contributing dataset DOIs or `datasetKey`s
and a persistent URL where the extracted dataset is accessible.
Neither of those source-identity requirements has been verified
for the original 96-pair focal input. **Do not cite an unrelated
October GBIF download DOI as the August ACSP input, or register
current data as if they were historically used.**

The appropriate next evidence is an **authenticated original
`confirmation-folds/pair_*/fold_*/training_occurrences.csv`
and `held_out_occurrences.csv` backup** or equivalent frozen
record-ID inventory with provenance. These may be in local,
private cloud or external backups, but they were absent from
the six inspected GitHub Actions archives. If they do not exist,
the publication must retain the already corrected statement:
statistical **result tables** are reproducible, exact historical
**input rows** are not currently publicly reproducible.

For prospective **new** GBIF-based confirmation only, capture an
immutable source-ID inventory and source dataset keys under a
controlled privacy policy *before* fold splitting, attach a
checksum and DOI-backed citation, and archive input separately
from biological results. Such a new run cannot repair the
historical trial or be described as its original input.

## Verification

```bash
python research/audit_original_gbif_archive_inventory.py \
  --cohort path/to/original_cohort.zip \
  --prior-confirmation path/to/original_prior_results.zip \
  --official-confirmation path/to/original_official_results.zip \
  --geographic-v1 path/to/original_geo_v1.zip \
  --geographic-v2 path/to/original_geo_v2.zip \
  --geographic-v3 path/to/original_geo_v3.zip \
  --verify-saved validation/acsp_original_gbif_archive_inventory_20261028.json
```

GitHub Actions verifies all six original ZIP bytes while they
remain available; the oldest expire on **2026-11-18 UTC**.
The only published CI output is the coordinate-free aggregate
receipt, never the input/held-out locations or nonfocal
reference coordinates. Source-level recovery remains
**open**, not silently marked completed.
