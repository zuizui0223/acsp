# Geographic framing v4 — development PASS and representation freeze

This directory preserves the first predeclared v4 development test of the unchanged historical focal-species country-registry representation.

## Decision

**PASS at the predeclared development gate.**

The representation is now frozen as `validation/acsp_geographic_framing_country_registry_freeze_v1.json` before any fresh framing confirmation cohort is sampled or evaluated.

No country expansion, temporal-window tuning, higher-taxon fallback, local component geometry, candidate generation, or robust-support calculation was added after opening v4 outcomes.

## Representation tested

The broad outer geographic registry is the set of countries in which the focal species had already been observed. In the fixed retrospective development instantiation:

- registry period: **1900–2020**;
- held-out period: **2021–2025**;
- GBIF filters: coordinates present, no GBIF geospatial issue, `occurrenceStatus=PRESENT`;
- no neighbouring-country expansion;
- no geographic padding or distance buffer;
- no genus/family, continent/realm, or all-world fallback.

The registry is only a **high-recall outer search universe**. The existing frozen ecological robust-support core remains the downstream narrowing layer. Country membership is not a priority score, occupancy probability, route decision, or budget decision.

## Why v4 differs from rejected v3

The country representation did **not** change from v3. V4 changed only the evaluation design and used a completely new development cohort.

V3 treated taxa with no 2021–2025 country-facet observations as geographic zeroes. V4 predeclared separate endpoints for:

1. historical-registry availability;
2. temporal evaluability;
3. conditional geographic containment among taxa for which recent outcomes objectively exist.

This prevents lack of a temporal observation from being silently re-labelled as a geographic miss.

## Identity freeze before outcomes

The first v4 workflow froze exactly **96 new taxa before temporal outcomes were opened**:

- 48 plants / 48 animals;
- 12 Japanese region cells, 8 taxa per cell;
- four record-count strata, 24 taxa per stratum;
- cohort seed `2026082304`;
- zero overlap with the previous 96 framing-development taxa;
- 443 exact previously inspected taxa excluded in total, plus the `Campanula microdonta` and `Campanula punctata` prefixes;
- no focal occurrence rows or temporal country outcomes were fetched before declaration;
- no taxon replacement after the identity freeze.

The frozen identity list is `predeclared_taxon_region_pairs.csv`.

## Predeclared gate and result

| Endpoint | Gate | First v4 result | Decision |
| --- | ---: | ---: | --- |
| Historical-registry availability | >= 0.95 | **1.0000** | PASS |
| Temporal evaluability, overall | >= 0.90 | **0.9583** | PASS |
| Temporal evaluability, plants | >= 0.85 | **0.9792** | PASS |
| Temporal evaluability, animals | >= 0.85 | **0.9375** | PASS |
| Conditional recent-record containment | >= 0.97 | **0.98994** | PASS |
| Conditional containment, plants | >= 0.95 | **0.99562** | PASS |
| Conditional containment, animals | >= 0.95 | **0.98401** | PASS |
| Declared yield denominator | 96 | **96** | PASS |

Ninety-two taxa had 2021–2025 country observations and four had no recent country-facet observations. The four temporally non-evaluable taxa were:

- `Cauloramphus magnus`;
- `Polystichum ×kurokawae`;
- `Cynoglossus ochiaii`;
- `Halocypria globosa`.

These four count against temporal evaluability but are not treated as geographic misses in conditional containment.

The low-containment tail is preserved rather than tuned away. The lowest evaluated recent-record containment values included `Cercyon algarum` (0.706), `Silpha perforata` (0.824), `Campsomeris annulata` (0.909), and `Leucothoe grayana` (0.931).

## Authoritative provenance

- workflow run: `32615423653`;
- evaluated code head: `4068f439c19703ea6d47fdcdac58615416322b3f`;
- protocol fingerprint: `3bd9e6145e17a99b52d8a9f82c07f346541f56a2bf81bd768e180de78c295bf8`;
- cohort artifact digest: `sha256:c7492cd70717ad906b8132291ec4fb19f8f68d0c3635bb267fee0730429fb369`;
- result artifact digest: `sha256:825b26ac6597393547f89feb7dd37d7e9ca9c72b6efb179a8c19f228cf76a05f`;
- identity CSV SHA-256: `04342b9c06f6bdf109ea4a684945acdbba8a7063cd11b29b563f80e701de485f`;
- cohort manifest SHA-256: `2360838d9665835ccd12766d83dea60b13ce56f1d022fb46dac2c6713e673dad`;
- summary SHA-256: `93150e9a0f2bfefcdbdee9b244d4d3d70125b07e06f497c33ff6bd932f73638c`;
- full per-taxon diagnostic CSV SHA-256 in the first-run artifact: `4829e8164889699856b968eea7cdb9ec8d189d58353514e15ae6185885e98711`;
- diagnostic snapshot fingerprint: `cdaf111af4ab86e1ebb018bb2c227d387e6b3f85d6b7b1e82373acb6ffe4f886`.

## Claim boundary

This is a **development PASS**, not an independent confirmation and not a global name-only ACSP validation.

It does not alter the independently validated Japan robust candidate-patch contract: support fraction `0.025`, float32 support worlds, 1 km same-area patch aggregation, non-ranked output, and planner-free candidate membership remain unchanged.

The only allowed next scientific step on this framing line is a **fresh, disjoint framing confirmation** using the frozen representation and excluding every v3/v4 development taxon. Candidate-generation integration must wait until that confirmation is resolved.
