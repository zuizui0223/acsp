# Geographic framing confirmation v1

This directory preserves the first independent confirmation of the frozen ACSP geographic-framing layer.

## What was confirmed

The tested representation is the frozen **past-observed focal-species country registry** used only as a broad outer search universe:

- focal-species GBIF country facets;
- historical registry period 1900–2020;
- held-out temporal outcome period 2021–2025;
- coordinate present, no GBIF geospatial issue, occurrenceStatus=PRESENT;
- no neighbouring-country expansion;
- no geographic padding or distance buffer;
- no higher-taxon, continent/realm, local-component, or all-world fallback.

The representation was frozen after v4 development in `validation/acsp_geographic_framing_country_registry_freeze_v1.json` and was not changed before this confirmation.

## Fresh cohort boundary

The authoritative run was GitHub Actions run `32624041517`. A fresh 96-taxon cohort was frozen before temporal outcomes were opened:

- 48 plants and 48 animals;
- 12 Japanese sampling cells × 8 taxa;
- four record-count strata × 24 taxa;
- seed `2026082305`;
- no overlap with framing-development v3 or v4 taxa;
- no taxon replacement after declaration.

Cohort artifact digest: `sha256:52f62323c55ed0bef4298f372285305ae53cfcbb322eacab1891aeb2287759b5`.

The original full identity artifact had SHA-256 `cd145e74de66319b6f878d2ceb384c399008a510a51814490dddb32b4f0f0273`. `confirmation_taxa.csv` is the durable compact identity registry used for future exclusion/audit.

## Confirmation result

Every predeclared gate passed:

| Endpoint | Result | Gate |
| --- | ---: | ---: |
| Historical registry availability | 1.0000 | >= 0.95 |
| Temporal evaluability | 0.9792 | >= 0.90 |
| Plant temporal evaluability | 0.9792 | >= 0.85 |
| Animal temporal evaluability | 0.9792 | >= 0.85 |
| Conditional recent-record containment | 0.98903 | >= 0.97 |
| Plant conditional containment | 0.99383 | >= 0.95 |
| Animal conditional containment | 0.98422 | >= 0.95 |

Ninety-four of 96 taxa had evaluable 2021–2025 country outcomes; two had no recent country-facet records. Those two reduce temporal evaluability but are not treated as geographic misses.

Results artifact digest: `sha256:350314a14e1631a0697534d6a82188871871b2ff63a8fc4e19699d17f4ca4263`.

The full per-taxon diagnostic artifact had SHA-256 `0a8bbc0f9c9d6d6640614d10952e2c75ee845cab5e381219efba0557b3c99468` and diagnostic snapshot fingerprint `a17b57c48258351c4d56aeb0862412b01e026391112e0a1481907b0b538c883a`.

## Claim ceiling

This confirmation supports only the statement that the frozen focal-species historical country-registry **framing rule** independently replicated across this fresh taxonomy-safe cohort drawn from Japan-recorded plant and animal taxa.

It does **not** establish that:

- global all-name ACSP is validated;
- country framing predicts exact occupied sites;
- integrating this frame with candidate generation has been validated;
- route, day, budget, access, SDM, or SSDM superiority has been validated.

Candidate generation and robust support were deliberately not run in this confirmation. Integration of the confirmed outer frame with the frozen candidate-patch core is therefore a separate next experiment and must not retroactively broaden this confirmation.

## Durable files

- `cohort_manifest.json` — identity-freeze audit from before outcome inspection.
- `confirmation_taxa.csv` — compact durable list of the 96 confirmation taxa.
- `country_registry_confirmation_v1_summary.json` — authoritative aggregate confirmation result.
- `validation/acsp_geographic_framing_confirmation_result_v1.json` — canonical run provenance and scientific decision.

The dedicated workflow is retained for manual replay only. A later live GBIF replay can diagnose source drift but cannot replace the authoritative first-run result.
