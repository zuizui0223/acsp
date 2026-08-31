# Campanula anchor selector comparison v1

Status: **development-only; coverage-constrained NDVI selector not retained**.

This record does not modify the independently validated 10-km ACSP robust candidate-patch product, does not use 2026 field outcomes, and does not promote any local-discovery selector.

## Exact evidence provenance

- workflow run: `33413970618`
- head SHA: `44de0055a8d3ffa51b8d4d2182a496b6ae02129e`
- result artifact: `campanula-anchor-selector-comparison`
- artifact id: `9766302088`
- artifact digest: `sha256:4972ab18b8c7699cce30fe782e5747164af0c207e64de022c3567e0fd900a69f`
- pinned spatial/NDVI baseline run: `33412591850`
- pinned baseline artifact id: `9765765509`
- pinned baseline artifact digest: `sha256:4cb8fb3b9dbf2d7461c711f25bba91ef1bb442d3c125fe19e933875a96ed2a4f`
- baseline head SHA: `55ca4f5b7552f82bf82579814d9914b60951cba9`

All 96 comparison configurations used the same complete-NDVI annular candidate frame and exactly matched median selected-cell counts across pure spatial balance, pure retained-anchor NDVI ranking, and the coverage-constrained NDVI hybrid.

## Result

Against **pure deterministic spatial balance**, the coverage-constrained NDVI hybrid produced:

- all configurations: **11 wins / 68 ties / 17 losses**;
- primary `single_link` clustering: **6 wins / 34 ties / 8 losses**;
- sensitivity `complete_link` clustering: **5 wins / 34 ties / 9 losses**;
- mean recall delta across all 96 configurations: approximately **-0.0114**;
- mean recall delta under the primary policy: approximately **-0.0117**.

By recovery radius, coverage-habitat versus spatial balance was:

| recovery radius | wins | ties | losses | mean recall delta |
|---:|---:|---:|---:|---:|
| 0.10 km | 6 | 8 | 10 | -0.0231 |
| 0.25 km | 2 | 16 | 6 | -0.0276 |
| 0.50 km | 3 | 20 | 1 | +0.0052 |
| 1.00 km | 0 | 24 | 0 | 0.0000 |

The only clean selection-fraction advantage was at 10% selection (3 wins / 13 ties / 0 losses), but every gain at that fraction occurred at the **0.10-km recovery radius**. It therefore fails the predeclared development rule that any retained gain must not depend on one clustering policy **or one recovery radius**. No 10% parameter is retained or promoted.

Against **pure retained-anchor NDVI ranking**, the hybrid produced 70 wins / 25 ties / 1 loss overall (34 / 13 / 1 under the primary policy). This only shows that spatial coverage repairs much of the weakness of pure NDVI compression; it does not establish ecological added value beyond the strong spatial-coverage comparator.

## Development decision

**Do not retain this selector as the next local-discovery candidate.**

The experiment shows that imposing NDVI similarity inside deterministic spatial-coverage strata does not provide stable added recovery beyond spatial balance at matched candidate-cell count. The result is a development-internal design failure, not a scientific adverse result and not evidence against the validated ACSP product.

Do not rescue the hybrid by selecting the favorable 10% / 0.10-km corner, retuning the Morton strata, changing clustering policy, or changing recovery radius after seeing this result.

## Consequence for the next development step

`spatially balanced coverage` remains the minimum allocation comparator for anchor-conditioned local discovery. A next ecological selector should be evaluated only if it has an independently motivated structural mechanism (for example explicit terrain/barrier/continuity structure) and is frozen before its LOCO recovery results are inspected. It must beat spatial balance at matched candidate count before any later matched-route or matched-field-effort claim is considered.
