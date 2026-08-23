# Geographic framing development v3 — rejected at the predeclared gate

This directory records the authoritative first development result for the historical focal-species country registry.

## Provenance

- workflow run: `32614846554`
- artifact: `acsp-geographic-framing-development-v3`
- artifact digest: `sha256:4b35f7cd06e9f549e05ec4244bcc2715e699838d4c62c65942b1e53a5253fefd`
- protocol fingerprint: `23ccd2ad90d387438079a992335978734bd0a460433cf266300e3852cdd1f9ce`
- diagnostic snapshot fingerprint: `03d32c0f283f69acf32a1be5d9cf4e603e378101f5257b5d29d00726ae7687f3`

The full 96-taxon country-count diagnostics remain in the immutable workflow artifact. The authoritative aggregate result is committed as `country_registry_v3_summary.json` so live GBIF drift cannot revise the decision.

## Frozen method

For each of the same 96 already-opened framing-development taxa:

- historical registry: GBIF country facet counts from 1900–2020;
- temporal held-out outcome: country facet counts from 2021–2025;
- records required coordinate presence, no GBIF geospatial issue, and PRESENT occurrence status;
- the outer frame contained exactly historically observed focal-species country codes;
- no neighbouring-country expansion, padding, distance buffer, higher-taxon fallback, continent/realm fallback, local occurrence components, or all-world fallback.

The primary endpoint was recent-record containment within the historical country set, calculated within taxon and then averaged equally across all 96 taxa. Provider failure, no historical registry, or no recent country records was predeclared to contribute zero.

## Result

- taxa in denominator: **96**
- analyzable recent outcomes: **92**
- zero outcomes retained: **4**, all `zero_recent_country_records`
- overall mean recent-record containment: **0.9414169324**
- plant mean: **0.9537181249**
- animal mean: **0.9291157400**
- mean recent-country containment: **0.8516906594**
- median historical country count: **9**
- mean historical country count: **25.5**
- median recent country count: **5**
- mean newly observed recent-country count: **1.8021**
- median historical-country fraction of the 249-code reference universe: **0.03614**

The predeclared gate required overall >=0.95, plant >=0.90, animal >=0.90, and all 96 taxa in the denominator. Plant and animal passed, but overall containment was **0.9414**, so v3 is **rejected** exactly as predeclared.

## Diagnosis

The v3 failure is not the same as v1/v2. All four zero-scoring taxa lacked 2021–2025 country-facet records; the summary contains no historical-registry or provider failures. For the 92 taxa with an observable temporal held-out outcome, the descriptive equal-taxon containment is **0.9823481034**. This value is diagnostic only and was not the predeclared promotion endpoint.

Therefore the exact v3 protocol remains rejected and may not be repaired by changing the temporal split, adding countries, or introducing fallback on the same 96 taxa. At the same time, the historical-country information source appears substantially more promising than local focal or local genus/family components when a temporal outcome is observable.

The next development design must use a **new disjoint cohort** and predeclare two separate questions: (1) temporal/applicability yield and (2) conditional containment among objectively evaluable taxa. Only after that development step could a registry representation be frozen for a fresh framing confirmation.

Candidate generation and robust ecological support were not run. No fresh confirmation taxa were consumed, the validated Japan adapter is unchanged, and no global name-only claim is supported.
