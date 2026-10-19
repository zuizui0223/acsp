# Public-record exposure and readiness audit for a future topology-informed *Cirsium* field trial

**Status, 16 October 2026:** Public-source **screening only**. No independent prospective field cohort was selected, no field outcome was accessed, no source-complete 100-m candidate patches were created, and no taxon/sector was cleared for real-world visits. This is not an independent biological test or an update to the confirmed ACSP 96-pair/480-fold robust-patch product.

## Why the original nine candidates are not nine untouched replicates

The aza3 public registry names thirteen Cirsium slots. CIR02, CIR06, CIR12 and CIR13 were already used in the frozen patch-connectivity method development (PR #256/273), so subtracting these four leaves nine **publicly named possibilities**, not nine eligible independent units. `outcome_opened=false` in the original registry concerns prospective field outcomes **in that registry**; it does not imply that the taxon, sector, public temporal outcomes, or method-development analysis had never been examined.

A source-locked audit of ten original committed ACSP public inputs distinguishes previous method execution, a preflight nomination, existing public outcomes, and unresolved exposure. Only a method/outcome signal explicitly present in those sources is positively asserted. Absence of a signal is `NOT_EVIDENCED_IN_PINNED_SOURCES_NOT_PROVEN_UNTOUCHED`, never `UNTOUCHED`.

| Registry unit | Taxon | Publicly verifiable previous method exposure | Field readiness |
|---|---|---|---|
| CIR01 | *C. sieboldii* | Executed population-holdout development; smoke selected; Japan38 exclusion specifically documents previous public outcome opening | Not built/authorized |
| CIR03 | *C. ugoense* | No explicit method-use evidence in the ten pinned files; **not proven unexposed** | Not built/authorized |
| CIR04 | *C. otayae* | Executed population-holdout development; structural smoke selected; its separate alpine technical smoke was blocked, not a successful biological result | Not built/authorized |
| CIR05 | *C. nambuense* | No explicit method-use evidence in pinned files; **not proven unexposed** | Not built/authorized |
| CIR07 | *C. pendulum* | Executed population-holdout development; also named in aza3 genomic planning (different research aim) | Not built/authorized |
| CIR08 | *C. brevicaule* | Structural preflight and smoke nominated; separate coastal development outcome opened, but broad population-holdout *execution deferred* | Not built/authorized |
| CIR09 | *C. spinosum* | No explicit method-use evidence in pinned files; **not proven unexposed** | Not built/authorized |
| CIR10 | *C. hachijoense* | No explicit method-use evidence in pinned files; **not proven unexposed** | Not built/authorized |
| CIR11 | *C. tamastoloniferum* | No explicit method-use evidence in pinned files, **and only a spatial-baseline feature family** is declared | Not built/authorized |

CIR01, CIR04 and CIR07 are explicitly in the three executed `execution_pairs` of `cirsium_structural_population_holdout_development_v1.json`; CIR08 is the deferred fourth pair, and has separately opened coastal development reports. All four appear in the earlier population-holdout preflight. The 3-family structural smoke nominated CIR01/CIR04/CIR08, with its *overall* method choice exposed to public temporal outcomes; no claim is made about a per-taxonomic temporal outcome where that evidence is absent. The original Japan38 disjoint roster explicitly excluded C. sieboldii for a previously opened CIR01 public outcome.

The other five carry **no affirmative evidence of methodological independence**. Source negativity is limited to these ten pinned public files and does not extend to other ACSP branches, aza3/EAzami, unpublished work or field notebooks. Their original aza3 table, private source requirements and current `NOT_BUILT` states remain unchanged.

## Independent source separation

The separate public [aza3 repository](https://github.com/zuizui0223/aza3) also contains sampling proposals; for example, `docs/AZA3_NATURE_GENOMIC_SAMPLING_PANEL_V1.md` proposes work on *C. pendulum*, *C. sieboldii* and *C. brevicaule*. These are **genomic planning roles**, not observations of completed ACSP field performance. Its source-level `data/planning/chapter3_acsp_range_sector_readiness_v1.csv` currently lists only the four already development-exposed SENTINEL IDs CIR02/CIR06/CIR12/CIR13 as unready for geometry materialization. That separate document **does not certify the other nine as ready or unready**; it simply does not cover them. It also does not substitute for privately verified sector geometry.

## What must be done before any biological comparison

1. Review method-exposure across all relevant projects and determine disjoint taxa/**geographic sectors** prospectively. A new sector in an old taxon is not automatically a new independent taxon. Retain failures after selecting a new cohort; do not remove a taxon because the method performs poorly or sources are inconvenient.
2. Verify the exact frozen private 100-m support-cell membership and patch SHA, provenance completeness and *at least two internally disconnected patches* per assigned new unit. Use no guessed locality coordinates.
3. Complete outcome-blind access, protected-area, land-manager and phenology checks for **both** counterfactual sites. No after-outcome substitution of accessible or detectable sites.
4. Independently freeze original equal-effort topology-versus-geometry site assignment (3 visits x 30 min x 1 observer, 90 person-minutes) and a public hash-only schedule receipt. Preserve all not-evaluable states, including permission block and incomplete search.
5. Only then conduct authorized, complete prospective detection/non-detection surveys and evaluate a pre-frozen estimand. **Do not append a fourth arm** to the separate original three-arm fresh-SENTINEL program. The source-only screen cannot estimate detection benefit, required visits, occupancy or field access.

## Reproduction and source boundary

`research/audit_cirsium_topology_cohort_exposure_screen.py` checks exact Git blob SHA-1 of ten public ACSP files, parses the 13-row registry and matching source-requirement rows, validates named prior method nomination/execution separately from public outcome usage, and exports a public-safe diagnostic. It does **not** read any source containing private coordinates, field logs or original candidate patch membership. The pinned source identities are in its `SOURCE_GIT_BLOBS` mapping. The runtime report's `independent_confirmatory_unit_count` and `ready_for_field_assignment_count` both **must remain zero** until an independent later protocol and source are verified. It cannot certify a negative exposure claim across other repositories.
