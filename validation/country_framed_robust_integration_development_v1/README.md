# Country-framed robust integration development v1

Status: **REJECTED development instantiation**.

This directory preserves the first preregistered attempt to connect the independently confirmed historical-country framing layer to the unchanged frozen robust candidate-patch core.

## Outcome isolation

- Protocol fingerprint: `b35b1fee5dd899e800d2449d966266b15df8f4b8987fe3ddcf49c6e7884b092a`.
- Authoritative workflow run: `32685558754`.
- The 24 taxon-country identities were frozen in Job 1 before recent outcomes or integrated candidate generation.
- Pre-outcome artifact: `9505552371`, SHA-256 `b01c0e7b1b757a0e749ab67ebf2926e05134c0070c5a771aa18abd856c80910f`.
- Frozen identity CSV SHA-256: `a13c47bf19fc59f2cca7a42059bc9cc4553f2f73928779994be44419d263cae8`.
- Result artifact: `9505595741`, SHA-256 `47d86fa88d17bb055976ea32e3cdece157273b7d9b35375789bb6ac2b389de2f`.
- No fresh framing-confirmation taxon was used.
- No taxon or country was replaced after declaration.

## Frozen method

The attempt used:

- focal-species historical country registry, 1900–2020;
- one deterministic historical country per development taxon;
- commit-pinned geoBoundaries gbOpen ADM0 v6.0.0 geometry;
- one 800-point country-wide candidate surface;
- the unchanged six terrain features;
- the frozen 2.5% float32 robust-support rule;
- 1 km same-area candidate-patch aggregation;
- 2021–2025 held-out occurrence coordinates;
- the already-confirmed 10 km primary recovery endpoint;
- 200 same-size random subsets of the same candidate surface.

Candidate generation was executed before any recent held-out occurrence was fetched for that taxon.

## Predeclared gate result

| Gate | Result |
| --- | --- |
| exactly 24 declared taxa | PASS |
| candidate-generation success >= 0.75 | **FAIL: 7/24 = 0.2917** |
| temporal evaluability >= 0.75 | PASS: 19/24 = 0.7917 |
| mean robust − random recall > 0 | **FAIL: -0.01045** |
| taxon-bootstrap 95% lower bound > 0 | **FAIL: -0.03045** |
| plant mean lift >= 0 | **FAIL: -0.000745** |
| animal mean lift >= 0 | **FAIL: -0.0250** |

Overall development gate: **FAIL**.

The taxon-bootstrap 95% interval for mean lift was `[-0.03045, 0.00000]`.

## Failure diagnosis

Seventeen taxa failed candidate generation:

- **12** failed because this v1 integration required exactly 800 complete post-terrain surface rows; the provider sampled 800 country points but complete terrain remained 739–799 after missing-data removal.
- **3** selected countries had fewer than five usable unique historical coordinates after cleaning.
- **2** had fewer than five unique complete terrain prototypes.

The exact-800 post-terrain rule is an integration-v1 constraint, not part of the independently validated Japan robust-core claim. It must not be relaxed and rerun on these same 24 taxa.

The negative result is not explained only by that mechanical failure. Among the five taxa with both generated patches and recent outcomes, the robust-minus-random lift signs were:

- positive: **0**;
- zero: **3**;
- negative: **2**.

Thus the tested country-wide 800-point instantiation failed both candidate-generation portability and ecological discrimination over the same-size random baseline.

## Decision

Do not:

- relax the exact-800 condition and rerun these 24 taxa;
- change the selected country after seeing failures;
- change geoBoundaries provider/version;
- retune 2.5% support, 1 km merge, six terrain features, 10 km endpoint, or random baseline on this cohort;
- present this as global ACSP validation.

The next scientific question is structural: whether integration must preserve the **validated regional candidate-surface scale within the confirmed country outer frame**, rather than representing an entire country with one 800-point surface. Any such method must be separately preregistered and evaluated on different development taxa.

Canonical decision record: `validation/acsp_country_framed_robust_integration_development_result_v1.json`.
