# ACSP methods paper

This directory separates the two evidence layers used by the manuscript.

1. **Retrospective breadth:** frozen, predeclared taxon-region cohorts evaluated with spatial-block holdout and same-pool random Top-5 controls.
2. **Prospective realism:** positive *Campanula microdonta* field detections compared with the exact candidate pool exported before field outcomes were inspected.

## Rebuild current outputs

```bash
python -m pip install -e .
python paper/build_paper_outputs.py
```

The command always rebuilds:

- `table_1_retrospective_validation.csv`
- `table_s1_seed_sensitivity.csv`
- `table_2_field_inventory.csv`
- the 500 m independent-detection clusters and manifest

When `field_validation/campanula_microdonta/frozen_candidate_pool.csv` is absent, it records the prospective comparison as blocked and does not reconstruct recommendations. When the frozen file is restored, the same command also creates:

- multi-radius ACSP field recovery;
- 10,000 same-pool random sets with the same survey-area quotas;
- lift and one-sided randomization p-values.

## Current field inventory

The 28 positive GPS rows form 19 independent clusters at the prespecified 500 m threshold:

- Oshima: 13 rows, 9 clusters
- Toshima: 8 rows, 3 clusters
- Niijima: 4 rows, 4 clusters
- Shikinejima: 1 row, 1 cluster
- Kozushima: 2 rows, 2 clusters

These counts describe positive field locations only. They do not estimate occupancy, detection probability, access success, or discoveries per unit effort.

## Immutable prospective input

The required candidate file must contain at least:

- `site_id`
- `survey_area_id`
- `latitude`
- `longitude`
- `is_recommended`

Candidate roles, ranks, scores, generation timestamp, and algorithm commit should also be retained. A narrative route plan or a candidate set regenerated after examining the field GPS data is not a valid substitute.
