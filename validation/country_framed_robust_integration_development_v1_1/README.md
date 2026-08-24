# Country-framed robust integration development v1.1

Status: **universal integration rejected; exact-800 portability diagnosis supported**.

V1.1 was preregistered after v1 had already been rejected. It used a completely disjoint 24-taxon development cohort and changed exactly one v1 integration-specific condition: after 800 external country-geometry draws, incomplete terrain rows could be dropped instead of requiring the complete table to remain exactly 800 rows.

## Outcome isolation

- Protocol fingerprint: `b61ab7f2625112c459559d28129db89c74ddc32808ebd5cfc6cf43009824d555`.
- Authoritative run: `32686580507`.
- Pre-outcome artifact: `9505872905`, SHA-256 `39963cefae128cc3453b5d19b3bf25187246f62b7503f8c68421964060795260`.
- Frozen identity CSV SHA-256: `c87cde0c202365a9ccb12ff9aa8650621c593e32cd7028d4c4339a4e7428dd7a`.
- Result artifact: `9505911984`, SHA-256 `3589068687f000e07304365728f0f633411b3ef61227b1855ad6f6dd084d53ac`.
- V1 taxa reused: **0**.
- Fresh framing-confirmation taxa consumed: **0**.
- 24/24 v1.1 taxon-country declarations succeeded before Job 2.
- Candidate generation was executed before any 2021–2025 occurrence request for that taxon.

## Sole change from rejected v1

V1 required `complete_post_terrain_surface_rows == 800` after drawing 800 external country points and attaching terrain. This caused 12/17 v1 candidate-generation failures.

V1.1 kept the same 800 initial geometry draws but used the existing `country_terrain_inputs` behavior:

1. sample 800 outcome-blind points inside the frozen country boundary;
2. attach the same six terrain features;
3. drop rows with incomplete terrain;
4. pass the remaining non-empty complete surface to the unchanged robust core;
5. add no new minimum complete-surface threshold.

Everything else remained frozen: historical country rule, geoBoundaries v6 provider, support 0.025, float32 worlds, six terrain features, 1 km patch merge, max 32 prototypes, 2021–2025 held-out window, 10 km primary endpoint, and 200 same-size random subsets from the actual post-terrain surface.

## Result

| Gate | Result |
| --- | --- |
| exactly 24 declared taxa | PASS |
| candidate-generation success >= 0.75 | **PASS: 20/24 = 0.8333** |
| temporal evaluability >= 0.75 | **PASS: 18/24 = 0.7500** |
| mean robust − random recall > 0 | **PASS: +0.05911** |
| taxon-bootstrap 95% lower bound > 0 | **PASS: +0.0000055** |
| plant mean lift >= 0 | **FAIL: -0.008045** |
| animal mean lift >= 0 | **PASS: +0.14544** |

Overall development gate: **FAIL**.

The taxon-bootstrap 95% interval for overall mean lift was `[+0.0000055, +0.13540]`.

Successful candidate surfaces contained a median of 799 complete rows and a minimum of 739, demonstrating that the exact-800 requirement was not needed for the unchanged robust core to execute.

## What v1.1 resolved

Candidate-generation success improved from v1 **7/24 = 0.2917** to v1.1 **20/24 = 0.8333** on a disjoint cohort. The exact-800 post-terrain requirement is therefore supported as a major v1 integration-specific portability blocker.

The four remaining candidate-generation failures were:

- three taxa with fewer than five unique complete historical terrain prototypes;
- one Seychelles case where whole-country rejection sampling could obtain only 227/800 land points inside a highly fragmented island geometry.

There were no exact-800 post-terrain failures in v1.1.

## Why the universal integration still fails

Sixteen taxa had both generated patches and evaluable recent outcomes.

- Plants, n=9: **1 positive / 6 ties / 2 negative**, mean lift **-0.008045**.
- Animals, n=7: **4 positive / 1 tie / 2 negative**, mean lift **+0.14544**.
- Overall: 5 positive / 7 ties / 4 negative.

Thus relaxing the v1 mechanical blocker reveals a real group-specific contrast rather than a universal gain. The positive overall mean is driven by animals and does not satisfy the preregistered plant guardrail.

## Decision

Do not:

- retune or reuse these 24 taxa;
- change country selection, provider, support 0.025, terrain features, 1 km merge, 10 km radius, or same-size random baseline on this cohort;
- interpret the favorable animal branch as validation of a separate animal production product;
- consume fresh framing-confirmation taxa for method development;
- present the one-country sparse-surface integration as universally validated.

The next method should address the **regional representation inside the confirmed country outer frame**, especially for plant transfer. It must be preregistered on different remaining v4 development taxa. A regional scale should be inherited outcome-blind from the already validated Japanese region design rather than tuned on v1/v1.1 outcomes.

Canonical decision: `validation/acsp_country_framed_robust_integration_development_result_v1_1.json`.
