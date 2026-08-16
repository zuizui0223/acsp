# Profile support and what it does not threaten

The Campanula development loop found that `component_local_habitat_score` ranks
how few records fitted a survey area's profile rather than how suitable the
habitat is. Across the five Izu islands the ordering was exact and inverted,
`spearman(training_records, median_score) = -0.900`:

| island | training records | median score | score IQR |
|---|---:|---:|---:|
| Shikinejima | 0 | 0.9835 | 0.0246 |
| Niijima | 1 | 0.9837 | 0.0130 |
| Toshima | 3 | 0.9387 | 0.1278 |
| Oshima | 16 | 0.9244 | 0.0272 |
| Kozushima | 36 | 0.8069 | 0.3257 |

A profile fitted to one record has no spread, so every candidate matches it and
the score saturates near 1. That is why seven of the global top ten were
Niijima, fitted from a single record, and why Kozushima with the most evidence
was never selected.

## Does this invalidate the frozen 192-pair confirmation?

Checked against the declared cohort metadata only —
`predeclared_taxon_region_pairs.csv` and `cohort_manifest.json`, both written at
freeze time. No candidate generation, no outcome inspection. The manifest still
reports `outcomes_inspected: false`, `candidate_generation_run: false`,
`practical_core_run: false`, `heldout_recovery_run: false`.

**Two of the three failure modes cannot reach the confirmation.**

**1. The catastrophic tightness cases are excluded by the protocol.** The cohort
sets `minimum_records: 20`, and the declared pairs bear that out: minimum 20,
10th percentile 44, median 142. Nothing in the 0-5 record range that broke
Niijima, Toshima and Shikinejima exists there.

| in-region records | pairs | share |
|---|---:|---:|
| ≤1 | 0 | 0.0% |
| 2–5 | 0 | 0.0% |
| 6–20 | 2 | 1.0% |
| 21–50 | 24 | 12.5% |
| >50 | 166 | 86.5% |

**2. The cross-area comparability defect is structurally absent.** It appears
only when several survey areas compete inside one Top-k. The Campanula case put
five islands into a single global Top-5, so the island with the least evidence
won. The confirmation scores one taxon in one region per pair, so there is no
cross-area competition to lose.

That defect is a **product** problem, not a confirmation problem — the app lets
users draw several rectangles, and `select_area_balanced_candidates` was added
precisely because global Top-k concentrated in too few of them. It is worth
fixing there.

## What remains a live risk

**Within-region inversion.** On Campanula the score pointed *away* from the real
sites inside Oshima (+0.342), Toshima (+0.484) and Shikinejima (+0.179), and
only Kozushima (−0.336) and Niijima (−0.283) pointed the right way. The
mechanism was sampling bias faithfully reproduced: Oshima's sixteen records skew
up the volcano (median 118 m, 90th percentile 364 m) while the novel field
detections sit at 45–75 m.

Nothing about `minimum_records: 20` prevents that. A region can hold 500 records
that are all roadside and still mis-rank the interior.

**This cannot be measured without spending the cohort.** Testing it needs
candidate generation and scoring on the declared pairs, which is the
confirmation run itself; once those outcomes are seen the cohort stops being
independent. So the choice is between running the confirmation as frozen and
reading this risk from its result, or building a separate development cohort to
measure it first.

Running the confirmation as frozen is the cheaper option, because the result
already discriminates: if the practical core beats the GRTS comparators despite
within-region inversion, the inversion is not fatal at 10 km; if it loses, this
note names a concrete mechanism to investigate rather than leaving the failure
unexplained.

## Reproduce

```bash
python research/campanula_score_audit.py --pool dense   # sections 1-5
```
