# ACSP methods-paper plan

## Working title

**From occurrence records to field decisions: complementary environmental-analogue prioritization of biodiversity survey zones**

Alternative: **Beyond habitat-suitability maps: testing finite survey decisions against same-pool counterfactuals**

## Central claim

ACSP is not proposed as a wholly new species-distribution model, and the manuscript should not imply that every production component has been independently validated. The supported object is the **occurrence-conditioned local-environment analogue and finite set-selection workflow**.

Given a fixed survey budget, the validated core:

1. rebuilds environmental candidate evidence from training occurrences only;
2. removes known-location candidates and direct occurrence-distance/density evidence during validation;
3. ranks environmental analogues without requiring a presence/background SDM;
4. selects a finite candidate set rather than producing only a continuous map; and
5. evaluates the selected set against random sets from the identical candidate pool and budget.

The external *Campanula microdonta* case adds a second lesson: when the survey contains several explicitly declared areas, global Top-k ranking may concentrate the budget in too few areas. A general area-coverage constraint is therefore an algorithmic extension, but its result must be labelled post-baseline development because the need for the update was exposed by the first field evaluation.

## What the implementation does

The national retrospective benchmark already isolates the non-SDM environmental pathway:

- every spatial fold rebuilds candidates from training occurrences only;
- local terrain/environment analogues are learned from those occurrences;
- known-location candidates are removed;
- occurrence support, survey-gap distance, environmental novelty, and distance-to-known components are excluded;
- plants use `component_local_habitat_score` with evidence weight `1.0`;
- animals use the same score with evidence weight `0.75`, leaving `0.25` for geographic complementarity;
- each Top-5 is compared with random Top-5 draws from the identical fold-specific pool.

The production `integrated_support_score`, optional macro-SDM support, access, logistics, and field-feedback layers remain broader than this confirmatory core.

The environmental analogue score is still niche-related. The defensible distinction from conventional SDM is the estimand and output: **which finite candidate set should be surveyed under a budget**, not the value of a suitability surface at every cell.

## Novel contributions

1. **Candidate-set prediction rather than map prediction.**
2. **Occurrence-conditioned environmental analogues without a required classifier.**
3. **Leakage-controlled recovery validation.**
4. **Same-pool random counterfactuals under the same budget.**
5. **Explicit separation of candidate generation, area allocation, and within-area ranking.**
6. **Cross-taxon retrospective validation plus later-year field evaluation.**
7. **External validation that is allowed to expose failure and motivate a versioned update.**
8. **Explicit spatial precision floors and bounded claims.**

## Study 1: general retrospective benchmark

- unit: taxon–region pair;
- partition: complete 0.1-degree spatial blocks;
- candidate reconstruction: training records only;
- leakage control: remove known-location candidates and occurrence/distance-derived score components;
- budget: fixed Top-5;
- primary endpoint: held-out observation-unit recovery within 10 km;
- baseline: 200 random Top-5 draws from the identical fold-specific pool;
- inference: intention-to-evaluate failures as zero, pair-clustered bootstrap intervals, sign-flip tests, leave-one-pair-out, and half-cohort stability.

### Existing independent results

- Animals: 12 pairs, recall `0.0981` versus random `0.0572`; lift `0.0408`.
- Plants: 36 pairs, recall `0.1098` versus random `0.0912`; lift `0.0186`.
- The 5-km plant effect is not stable and remains outside the supported claim.
- All leave-one-pair-out mean lifts remained positive.
- Maximum five-seed sign-flip p: animals `0.0853`, plants `0.0271`.

These results support modest regional ranking information. They do not estimate occupancy, detectability, exact-site accuracy, or field efficiency.

## Study 2: temporal external *Campanula microdonta* evaluation

### Independence design

- query Japanese GBIF records for *C. microdonta* through 2025;
- build and save the candidate pool before reading the 2026 field GPS file;
- exclude known-location candidates and direct occurrence/distance-derived evidence;
- keep Top-k, score, radii, random iterations, and clustering threshold fixed in code;
- use the 2026 detections only for the final recovery calculation.

This is a temporal external evaluation, not a claim that a candidate file was physically exported before fieldwork.

### Data

- historical GBIF training records after cleaning: `281`;
- distance-excluded candidate pool: `97`;
- field GPS rows: `28`;
- independent detection clusters at 500 m: `19`;
- cluster counts: Oshima `9`, Toshima `3`, Niijima `4`, Shikinejima `1`, Kozushima `2`.

### Baseline policy and result

The unchanged plant policy selected the global Top-5 by local-habitat score.

- allocation: Niijima `4`, Shikinejima `1`;
- 0.5-km recall: `0.1579` versus random `0.1035`; lift `0.0544`, p `0.2458`;
- 2-km recall: `0.2105` versus random `0.2163`; lift `-0.0058`;
- 10-km recall: `0.2632` versus random `0.2632`; lift `0`, p `1.0`.

Interpretation: the first field evaluation does **not** support the unstratified global Top-5 policy. It identifies a general multi-area allocation failure.

## Post-baseline algorithm update

### General rule

Add `select_area_balanced_candidates`:

- if `k` is at least the number of non-empty declared survey areas, represent every area once before selecting any duplicate area;
- within that constraint, retain the configured evidence and geographic-complementarity utility;
- do not encode species names, field coordinates, island-specific weights, or detection labels.

### Updated *C. microdonta* result

The updated Top-5 contains one candidate per island.

- 0.5-km recall: `0.1053` versus same-allocation random `0.1027`; lift `0.0026`, p `0.6972`;
- 1-km recall: `0.1579` versus random `0.1748`; lift `-0.0170`;
- 2-km recall: `0.4737` versus random `0.3750`; lift `0.0987`, p `0.1960`;
- 5-km recall: `0.6842` versus random `0.6752`; lift `0.0090`;
- 10-km recall: `0.8947` versus random `0.8573`; lift `0.0374`, p `0.4996`.

Interpretation:

- area balancing greatly improves total coverage relative to the concentrated baseline;
- most coarse-scale improvement comes from representing all islands, not from a resolved ranking advantage;
- the largest ranking lift occurs at 2 km but remains uncertain with 19 clusters;
- 10 km saturates on small islands and is not an informative fine-location endpoint for this case.

## Scientific status of the update

The 2026 detections are not model inputs. Nevertheless, the area-coverage rule was added after the baseline result exposed the failure. Therefore:

- the baseline is the untouched external result;
- the area-balanced result is post-baseline algorithm development;
- it must not be described as an independent confirmation;
- confirmation requires an independent multi-area taxon, an untouched island group, or a later field campaign.

This distinction avoids both extremes: pretending that an obvious algorithm flaw cannot be repaired, and pretending that a repaired result on the same evaluation set is a fresh test.

## Why the two validation layers belong together

The retrospective benchmark tests breadth across taxa and regions. The field case tests transfer to later real observations and reveals operational failures that single-region database hold-outs may miss.

The two effects must not be pooled:

- retrospective endpoint: recovery of spatially held-out occurrence records;
- field endpoint: proximity to independent later-year detection clusters;
- post-baseline endpoint: diagnostic performance after a versioned algorithm update.

## Reporting rules

1. Always report candidate-pool size and selected-area allocation.
2. Keep baseline and updated algorithm versions separate.
3. Preserve the original unfavorable baseline result.
4. Random controls must match both total Top-k and selected area quotas.
5. Report 0.5, 1, 2, 5, and 10 km; do not promote a favorable radius post hoc.
6. Treat 10 km as a regional endpoint and acknowledge saturation on small islands.
7. Cluster positive GPS rows before analysis.
8. Do not call positive-only recovery occupancy or detection probability.
9. Do not infer field efficiency without attempted-site, effort, access, and non-detection records.
10. Re-run general random validation after substantive changes to the ecological scoring pathway.

## Proposed figures

1. occurrence records → environmental analogues → finite candidate set → field detections;
2. conventional continuous-map output versus finite set decision;
3. spatial-block hold-out and same-pool random counterfactual;
4. independent animal and plant lift at 10 km;
5. stability across pair resampling and seeds;
6. five-island candidate pool, concentrated baseline Top-5, and area-balanced Top-5;
7. baseline versus updated recovery across radii;
8. updated ACSP versus same-allocation random distributions at 2 and 10 km.

## Claims table

| Claim | Status |
|---|---|
| ACSP converts occurrence-conditioned evidence into a finite, auditable field decision | Method/software contribution |
| The local-analogue core exceeds same-pool random at 10 km across independent animal and plant cohorts | Supported and resampling-stable |
| The unstratified plant Top-5 transfers successfully to the five-island field design | Not supported |
| Explicit area coverage fixes the concentrated allocation failure | Demonstrated on the field case; post-baseline development |
| Environmental ranking within islands is superior to random selection | Suggestive at 2 km, not statistically resolved |
| The complete production score is validated as one unit | Unsupported |
| Representative coordinates are exact occupied sites | Unsupported |
| ACSP increases detection probability or discoveries per day | Requires complete visit and effort data |

## Next independent test

The next confirmatory dataset should contain several declared survey areas and must remain untouched until the area-balanced candidate set is frozen. Suitable designs include another island archipelago, several disconnected protected areas for one taxon, or a new *C. microdonta* field season with complete visit logs.
