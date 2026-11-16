# Three historical GSI replays: stable patch bytes, unstable upstream terrain/order bytes

**Recorded 2026-11-16. Post-hoc reproducibility diagnostic, not a preregistered or independent ecological study.**

The frozen Cirsium 100 m source-world test originally ran in GitHub Actions [37647225829](https://github.com/zuizui0223/acsp/actions/runs/37647225829) (PR #247); a second full run [37705751756](https://github.com/zuizui0223/acsp/actions/runs/37705751756) (PR #249) and the later [37726204623](https://github.com/zuizui0223/acsp/actions/runs/37726204623) (draft PR #250) re-executed the same four units with the same declared source and scientific settings. The third run failed the original full-order SHA guard for three units. No results were selected for favorable terrain values or field outcomes.

## Source-bound observational comparison

All 12 original GitHub job logs were read. The ledger `validation/cirsium_gsi_three_run_log_ledger_20261116.json` retains job/run IDs and only six types of SHA-256: grid CSV, GSI terrain-feature digest, GSI CSV, source-state digest, full structural order CSV and final patch CSV. It contains **no raw candidate coordinates, grid row/column values, GBIF records or observed field outcomes**. It does not contain the original full job-log bytes or the raw DEM tiles, so the recorded job-log lineage must not be overstated as a complete cryptographic source archive.

A cell below is **equal to the initial PR #247 source** (the initial run is equal to itself):

| Unit and declared structure | First run | PR #249 GSI / full order | PR #250 GSI / full order | Final patch SHA across all 3 |
|---|---|---|---|---|
| CIR02 wetland | original | equal / equal | **different / different** | equal |
| CIR06 alpine | original | **different / different** | equal / equal | equal |
| CIR12 grassland | original | equal / equal | **different / different** | equal |
| CIR13 grassland | original | **different / different** | **different / different** | equal |

**Across the two later rounds:** 3/8 unit-runs reproduced the original GSI feature digest *and* original full structural-order SHA, while 5/8 did not. Across **all 12 named unit-run logs**, original grid and structural source-state digests match **12/12**, and original final patch CSV bytes match **12/12**. All 3 PR #250 failed jobs stopped specifically at the full-order gate. These are repeated executions of the same research-stage source and cannot be treated as 12 ecological replicates.

The earliest observed difference is within the GSI terrain content/representation, upstream of the structural-order and patch aggregation stages. Counts, source-state labels and public provider-category aggregates remaining equal do not prove every GSI PNG tile, DEM mosaic, terrain vector or CPU math result was equal. Stable final patch bytes do not retroactively repair differing source-world hashes.

## What the prior detailed numerical work establishes

A separately source-bound 72-cell CIR02 diagnostic (merged PR #270, `validation/coverage_then_fine_structure_fresh_sentinel_v2_cir02_real_angle_operator_pair_result_v1.json`) identified `arctan_radians` as the first different elementary operation. The two native float32 arctan loops were `baseline(X86_V2)` and `X86_V4` on different workers, despite verified equality of selected DEM source bytes, sampled identities, gradient arrays, squared terms and square roots. This is an **observed cross-worker co-variation**, not established CPU-dispatch causality for all cells/units.

The later original-source same-worker attempt (PR #271) did **not** change the actual selected arctan loop with `AVX512F` disabled. The separately frozen native NumPy 2.4 `X86_V4` preflight (PR #272) landed on a baseline-only worker and was **ineligible**. Neither yielded a causal mechanism proof. Do not turn repeated runner selection into another empirical search.

## Decision and separation of scientific objects

- **For numerical/source replay:** keep Issue #253 unresolved and draft PR #250's strict full-order SHA gate unchanged; no additional opportunistic hosted-worker repeats. Any causal test needs reproducible fixed source bytes, a pinned capable architecture, a preflight demonstrating an actual loop switch, and a separately frozen single-worker experiment.
- **For geometric support-mask topology:** the existing membership-only four-unit audit from merged PR #256 is complete, and PR #273 already provides a secondary graph interpretation. It verifies **frozen patch bytes**, not a successful full upstream replay. A thresholded support-mask disconnection is neither habitat disconnection nor survey inaccessibility.
- **For the validated product/paper:** keep the original Japan 96 taxon-region × five-fold 2.5% float32 / 1 km non-ranked candidate-patch result and its 10-km screening claim untouched. This Cirsium study adds no field efficiency, occupancy, exact-site recovery or new independent validation.

## Reproduce the internal audit

```bash
python research/audit_cirsium_gsi_three_run_ledger.py
python -m pytest -q tests/test_cirsium_gsi_three_run_ledger.py
```

Optional original-job-log cross-check (requires the user to download the **matching original** GitHub job logs, not alternative reruns):

```bash
python research/audit_cirsium_gsi_three_run_ledger.py --logs-root PRIVATE_LOG_DIR
```

The optional local directory must contain `PRIVATE_LOG_DIR/<run_id>/<CIRxx>.log`. It verifies the recorded stage hashes and fail-closed markers against supplied logs, **not the external provenance or authenticity of the supplied files**. No log content is uploaded by the audit.

Related: [#253](https://github.com/zuizui0223/acsp/issues/253), [draft #250](https://github.com/zuizui0223/acsp/pull/250), [merged #256](https://github.com/zuizui0223/acsp/pull/256) and [merged #273](https://github.com/zuizui0223/acsp/pull/273).
