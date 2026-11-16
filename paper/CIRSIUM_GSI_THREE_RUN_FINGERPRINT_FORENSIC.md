# Three-run GSI replay fingerprint audit — Cirsium (source integrity only)

**16 November 2026.** This is a **post-observation forensic software receipt**, not a preregistered source-stability or ecological performance experiment. It is additional evidence for [Issue #253](https://github.com/zuizui0223/acsp/issues/253). It does not reopen, resolve, or bypass the fail-closed [PR #250](https://github.com/zuizui0223/acsp/pull/250) whole-order topology gate.

## Original run identities and observational comparison

Read all **12 original GitHub Actions job logs** from three *named* historical four-unit executions:

- [PR #247 initial run 37647225829](https://github.com/zuizui0223/acsp/actions/runs/37647225829), whose per-unit structural and final patch SHA values are pinned in the prior PR #248 receipt;
- [PR #249 replay 37705751756](https://github.com/zuizui0223/acsp/actions/runs/37705751756), previously included in PR #254's **two-run** audit;
- [PR #250 strict audit 37726204623](https://github.com/zuizui0223/acsp/actions/runs/37726204623), where three units stopped at the original structural-order hash gate.

A: identical to the **first run's** unit-specific GSI feature SHA; B: a different exact SHA from that unit's first run. **Do not compare A or B between different units.**

| Unit | 247 | 249 | 250 | Grid, source-state and chunk-audit metadata | Frozen final patch CSV SHA | PR250 whole-order gate |
| --- | --- | --- | --- | --- | --- | --- |
| CIR02 wetland-moisture | A | A | B | 3/3 identical | 3/3 identical | STOP |
| CIR06 alpine-topography | A | B | A | 3/3 identical | 3/3 identical | PASS |
| CIR12 open grassland | A | A | B | 3/3 identical | 3/3 identical | STOP |
| CIR13 open grassland | A | B | B | 3/3 identical | 3/3 identical | STOP |

For **all four units**, each run has exactly **two distinct** GSI feature hashes and the corresponding GSI CSV and full structural-order fingerprints change together. The original candidate grid hashes, complete/indeterminate GSI counts, full per-chunk availability/attribution audit records, structural source-state digests, retained-cell counts and final compressed patch-file SHA-256 remain unchanged across **all 12 jobs**.

This is **not** proof that individual GSI PNG tile or TIFF DEM mosaic bytes were equal, or that the ranking of all unselected cells changed in the same way. Matching chunk *metadata* is weaker than matching chunk contents.

The full-order SHA from the third run matches the original only for CIR06, and PR250 correctly stopped the other three units. The all-four original patch-membership-only topology result was already obtained in [PR #256](https://github.com/zuizui0223/acsp/pull/256) and synthesized in [PR #273](https://github.com/zuizui0223/acsp/pull/273). No topology result is newly claimed here.

## What this does and does not reveal

The earliest **recorded metadata-level divergence** across the three executions is the GSI terrain-feature digest, *before* structural ranking and patch compression. The run-specific pattern differs across units, even when the final patches remain byte-identical. This rules out a simple interpretation of the final patch SHA as full numerical determinism.

Separate, source-matched CIR02 diagnostics in PR #270 observed the first per-operator numerical divergence at native float32 `arctan_radians` in a selected 72-cell sample and different cross-worker NumPy SIMD loop dispatches. The same-worker intervention in PR #271 failed to change the actual selected loop, and PR #272's subsequent CPU-only eligibility check was ineligible. Therefore the CPU-dispatch **causal mechanism remains unproven**. The 12-job fingerprint audit is neither a CPU mechanism experiment nor a test of all 177 original CIR02 source chunks.

**No changes are authorized** to the original 2.5% support cutoff, 1-km complete-link grouping, source priority, chunk phase, float32 numerical implementation, field outcomes, site estimates, validated Japanese 96-pair / 480-fold core, or manuscript's independent performance estimate.

## Reproducibility without publishing location-bearing logs

- Implementation: `research/audit_cirsium_three_run_gsi_fingerprints.py`
- Source-locked, coordinate-free result: `validation/cirsium_three_run_gsi_fingerprints_20261116.json`
- Synthetic failure tests: `tests/test_cirsium_three_run_gsi_fingerprints.py`
- CI: `.github/workflows/cirsium-three-run-gsi-fingerprint-audit.yml`

The CI reads the 12 named historical job logs into **temporary private storage**, verifies exact safe GSI/structural/patch hashes and original denominator bindings, compares per-chunk metadata internally and emits **only aggregate counts**. Raw logs, cells, geographic tile names, occurrences, coordinates, and private GSI rasters are not committed or uploaded as artifacts. The saved receipt is a source-bound record of metadata extracted from GitHub Actions logs; without externally authenticated source-log bytes it is **not cryptographic proof of original provider tile content**. The workflow does **not** rerun GSI or the biological analysis.

Conclusion: **patch representation repeated exactly in all three named runs; upstream GSI/full-order bytes did not.** This fact supports keeping the strict PR250 stop and reporting the existing downstream patch geometry separately from upstream numerical reproducibility.
