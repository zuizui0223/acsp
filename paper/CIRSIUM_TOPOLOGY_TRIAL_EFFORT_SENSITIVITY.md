# Cirsium topology-versus-geometry: outcome-blind trial-effort sensitivity

**Status (19 October 2026): scenario analysis only; no measured field response.**
This is a bounded next-step calculation for issue #275, **not** an amendment
to the 2026-10-16 frozen topology-site design, the existing three-arm
fresh-SENTINEL study, or the independently validated Japan ACSP product.

## Why the calculation is necessary

PR #273 establishes that some *development-stage* 1-km bounded Cirsium
patches contain several disconnected retained 100-m support fragments.
PR #278 proves the available component-count summaries **cannot reveal**
whether the two frozen representative-site algorithms actually return
different cells. The proportion of assigned new-cohort patches with
different selected cells is **q**, and q remains unmeasured.

A fragmented support patch is not necessarily a changed survey site.
Even a changed survey site need not produce a biological detection gain.
Before proposing field effort, we can quantify what a *hypothetical* site
effect would imply for sample size, keeping these three steps separate.

## Explicit assumptions and estimand

Take one patch as the independent binary outcome unit: at least one
verified-current-occurrence detection after the **three scheduled
30-minute searches by one observer**. These are patch-level outcomes;
the three repeated visits are **not** three independent samples.

- Assume the geometry-arm patch-level verified detection fraction
  `p0 = 0.30`; this is an invented planning scenario, not a Cirsium estimate.
- Let `q` be the **assumed**, equal-across-arms fraction with distinct
  topology and geometry candidate cells. The real new-cohort q is NULL.
- Let `theta` be the **assumed** risk difference in verified detection
  among distinct-site patches, with zero expected site-only contrast
  when both methods choose the same original retained cell.
- Assume comparable search/observer/season/permissions, common control
  response across strata, no loss to follow-up, no taxon/sector
  clustering, and no interference. Actual randomized arms are only
  balanced by **patch count within cohort**, not guaranteed balanced
  on discordance q; the calculations are therefore optimistic.

Under those assumptions the hypothetical intention-to-treat patch-level
risk difference is `delta = q * theta` and `p1 = p0 + delta`.

For a balanced two-arm, **two-sided** alpha = 0.05 normal approximation,
power = 0.80, with z values from the standard normal distribution,

```text
pbar = (p0+p1)/2
n_per_arm = ceil(
  [ z_0.975 * sqrt(2*pbar*(1-pbar))
    + z_0.80 * sqrt(p0*(1-p0)+p1*(1-p1)) ]^2
  / (p1-p0)^2
)
planned_active_person_hours = (2*n_per_arm)*90/60
```

This is an **illustrative** normal approximation, not an exact
randomization-based power calculation, a confidence interval, a
preregistered final sample size, or a validated field-efficiency effect.
No retrospective Cirsium outcome data or private sites are used.

## Model-only scenario results

All rows assume p0=0.30, two-sided alpha=0.05, 80% target power and
90 planned active person-minutes per patch. Travel, setup, permission
screening, non-evaluability, and between-taxon/sector clustering are excluded.

| Assumed q | Assumed theta | Implied delta | Patches per arm | Total patches | Active person-hours |
|---:|---:|---:|---:|---:|---:|
| 0.25 | 0.10 | 0.025 | 5,395 | 10,790 | 16,185 |
| 0.25 | 0.20 | 0.050 | 1,377 | 2,754 | 4,131 |
| 0.50 | 0.20 | 0.100 | 356 | 712 | 1,068 |
| 1.00 | 0.20 | 0.200 | 93 | 186 | 279 |

When q=0, there is no changed-site first stage and **no positive
site-only risk difference can be detected under this model**, regardless
of the number of replicate patches. The real q is **not** assumed to be
0.25, 0.50, 1.00, or 0; it is unknown. The old 4,168 fragmented
development patches and 6,252 theoretical active person-hours from
PR #277 **cannot** be substituted for new cohort sample size or q.

## Decision boundary

**Do not freeze a field sample size or authorize a trial from these rows.**
An independent trial remains blocked until exact, owner-authorized,
source-complete private 100-m patch member lists and disjoint new
taxon/sector identities are frozen; both candidate cells are vetted
symmetrically for access, permits and phenology before outcomes; actual
site discordance q and available evaluable patch counts are documented;
and a separate prospective power/precision and analysis plan is frozen
with clustering, missingness and achievable field capacity considered.

The existing hashed assignment salt, two medoid definitions, 90-minute
per-patch design, three-arm SENTINEL protocol, CIR02/CIR06/CIR12/CIR13
source receipts, and Japan validated 2.5%/1-km product are unchanged.

Reproduce the *hypothetical* table with:

```bash
python research/cirsium_topology_trial_effort_sensitivity_v1.py
pytest -q tests/test_cirsium_topology_trial_effort_sensitivity_v1.py
```
