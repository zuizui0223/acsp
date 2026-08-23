# Geographic framing development v2 — rejected

This directory records the authoritative first predeclared development result for `higher_taxon_nonfocal_block_component_10km_padding_v2`.

## Provenance

- source workflow run: `32613456408`
- source artifact: `acsp-geographic-framing-development-v2`
- source artifact digest: `sha256:76a3eafaeeb3a42fcc7d0f525db9d01f7ec5809b6fc26313ccafece5ec7de03e`
- protocol fingerprint: `5f77d4e0d33fec794ce85c666a6bfafbe029f0ed001ab2644eb2e64eceb35f5f`
- prior snapshot fingerprint: `26d93bb3de0b2613e0d328a40290d8a65dce307232d06abf3c9f64e60d885bb4`
- focal occurrence snapshot fingerprint: `4a72414e4916a0d2c870e4ccda4537d997398e859df8a3162683328359535209`

The raw first-run fold diagnostics, pair diagnostics, pair-level prior audit, and higher-taxon prior points remain in the immutable workflow artifact. The aggregate authoritative result is committed as `framing_v2_diagnostic_summary.json` so the rejection decision does not depend on rerunning live GBIF queries.

## Frozen method

For each of the same 96 already-opened framing-development taxa, v2 queried non-focal occurrences of the focal genus inside the fixed development rectangle. Records belonging to the focal species were removed before framing. Family was used only when genus yielded zero usable non-focal coordinates.

The geographic geometry itself was not retuned after v1: 0.1-degree occupied blocks, 8-neighbour components, singleton retention, frozen 10 km padding, and deterministic overlap union. One higher-taxon prior snapshot was fetched per taxon-region pair and reused unchanged across all five focal folds. Focal training and held-out coordinates did not enter prior construction.

## Result

All 480 declared folds remain in the denominator.

- evaluated folds: **460**
- failed folds retained as zero: **20**
- mean held-out containment: **0.7447725724**
- animal mean containment: **0.7231096470**
- plant mean containment: **0.7664354979**
- median inferred-frame / fixed-region area ratio: **0.6484982091**
- mean area ratio: **0.5901962856**
- median frame count: **2**
- usable higher-taxon prior: **92 / 96 taxa**
- prior rank: GENUS **75**, FAMILY **19**, NONE **2**

The predeclared development gate required overall containment >= 0.95, animal containment >= 0.90, median area ratio <= 0.85, and all 480 folds retained. Compactness passed, but both containment requirements failed substantially.

## Decision

**Reject v2.** Do not retune the 0.1-degree blocks, frozen 10 km padding, genus/family fallback, or 300-record cap on these same 96 taxa.

This is not primarily a provider-availability failure: 92 taxa had usable non-focal higher-taxon priors. The geographic representation itself is insufficient. Candidate generation and robust ecological support were intentionally not run after the framing gate failed.

The architectural conclusion is now stronger than after v1: neither focal local occurrence components nor local genus/family occurrence components provide a sufficiently complete outer search universe. The next geographic framing experiment must change the information source more fundamentally toward an independently broad, outcome-blind registry or domain prior. Robust ecological support remains downstream of that framing layer.

No fresh confirmation taxa were consumed, the validated 12-region Japan adapter is unchanged, and no beyond-Japan validation claim is supported by this development result.
