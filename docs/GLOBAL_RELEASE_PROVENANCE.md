# Global release provenance

This release exposes the automatic global candidate-patch adapter without importing experimental LOCAL/DETACHED discovery or merging draft PR184.

## Audited extraction

Main baseline: `0c6e45599c3b1deac8e7666c5c22948a55bcad75`. Source: [tested integration 0357b7e](https://github.com/zuizui0223/acsp/tree/0357b7e4bbf39bea787c893587714a260eebaa59).

The [port manifest](../validation/acsp_global_release_port_manifest_v1.json) records hashes for eight modules and two fixed resources. All 41 extracted function/class definitions were AST-compared against that source. Only module imports and the resource package name change; the GBIF helper retains the two unchanged matching/transport functions needed here. Existing main candidate-generation files remain unchanged.

The previously tested [PR210 Windows path repair](https://github.com/zuizui0223/acsp/pull/210) is included separately. Relative identity paths use POSIX serialization; frozen file bytes and hash checks are unchanged.

## Scientific authority

- [Frozen protocol](https://github.com/zuizui0223/acsp/blob/0357b7e4bbf39bea787c893587714a260eebaa59/validation/acsp_global_availability_parity_confirmation_v2.json).
- [Canonical result](../validation/acsp_global_availability_parity_confirmation_result_v2.json) and [taxon results](../validation/acsp_global_availability_parity_heldout_results_v2.csv), copied from the pinned source.
- [Original run 34174350904](https://github.com/zuizui0223/acsp/actions/runs/34174350904), artifact 10036923813, archive digest `sha256:68f133bb9b6dd0f22663aa385c697f03b6719eda545e844ac498761b1d347867`, as recorded in the canonical result.

The 48 fresh taxa were drawn from the pooled Japanese discovery-region registry. The result applies to the tested automatic historical-country adapter, not arbitrary worldwide taxa or explicit target countries. The valid empty set remains in the constructible denominator. No occupancy or field-efficiency claim follows.

Full staged research execution and its dependencies remain in the pinned source tree. These copied results are provenance, not a claim that the entire study can be replayed from this reduced runtime release alone.

## Earlier results are preserved

The [reserved replication](https://github.com/zuizui0223/acsp/blob/0357b7e4bbf39bea787c893587714a260eebaa59/validation/acsp_country_framed_robust_integration_development_v2_replication_result_v1.json) and [fresh heterogeneity confirmation](https://github.com/zuizui0223/acsp/blob/0357b7e4bbf39bea787c893587714a260eebaa59/validation/acsp_country_framed_fresh_heterogeneity_confirmation_result_v1.json) retain their original failures and denominators. Provider aborts are not biological negatives. No opened cohort is reused as fresh confirmation.

## Operational examples

The source wheel completed Ficus microcarpa with explicit SG: ROBUST_EMPTY, 0 patches. Automatic mode selected TW: ROBUST_READY, 85 patches. These live-provider runs are operational checks, not new scientific confirmation or large-country scaling evidence. No tiles or density are reduced for speed.

The standalone release wheel was also run outside the checkout on 2026-09-15 with Ficus microcarpa and no country override. It selected TW and produced 85 patches. Its CSV was byte-identical to the source-wheel run: SHA-256 `20588204f32524c111f22109e0ec2ed2cc7be98a496808b1af0165e30413cdeb`. This corroborates the code-level port comparison, not a new ecological claim.

The command is `acsp-global-patches --taxon NAME --out-dir NEW`, with optional `--country XX`. The Japan command remains unchanged. Neither command requires a budget, route, day count or ranking.
