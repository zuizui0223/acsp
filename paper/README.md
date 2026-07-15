# ACSP methods paper

This directory separates three evidence layers.

1. **Retrospective breadth:** frozen, predeclared taxon–region cohorts evaluated with spatial-block hold-out and same-pool random Top-5 controls.
2. **Temporal external baseline:** *Campanula microdonta* candidates generated from Japanese GBIF records through 2025 and evaluated against independent field detections from 2026.
3. **Post-baseline development:** a general survey-area-balanced selector added after the baseline exposed candidate concentration across islands.

The baseline and updated results must remain separate. The updated selector does not train on field coordinates, but its need was diagnosed from the baseline result and therefore it is not an untouched confirmation.

## Rebuild retrospective paper outputs

```bash
python -m pip install -e .
python paper/build_paper_outputs.py
```

This rebuilds:

- `table_1_retrospective_validation.csv`
- `table_s1_seed_sensitivity.csv`
- `table_2_field_inventory.csv`
- the 500-m independent-detection clusters and manifest

## Run the temporal external field evaluation

```bash
python field_validation/campanula_microdonta/run_temporal_external_validation.py \
  --output field_validation/campanula_microdonta/temporal_external_results \
  --gbif-cap 2000 \
  --random-iterations 10000 \
  --seed 20260715 \
  --cluster-radius-m 500

python field_validation/campanula_microdonta/compare_area_balanced_update.py \
  --results field_validation/campanula_microdonta/temporal_external_results \
  --random-iterations 10000 \
  --seed 20260715
```

The first command performs the following operations in order:

1. retrieves *C. microdonta* GBIF records dated through 2025;
2. generates the distance-excluded candidate pool;
3. writes the baseline global Top-5;
4. only then reads and clusters the 2026 field GPS file;
5. calculates multi-radius recovery and same-pool random controls.

The second command applies the general area-balanced selector to the already generated candidate pool before evaluating it against field clusters.

## Current field inventory

The 28 positive GPS rows form 19 independent clusters at 500 m:

- Oshima: 13 rows, 9 clusters
- Toshima: 8 rows, 3 clusters
- Niijima: 4 rows, 4 clusters
- Shikinejima: 1 row, 1 cluster
- Kozushima: 2 rows, 2 clusters

These counts describe positive field locations only. They do not estimate occupancy, detection probability, access success, or discoveries per unit effort.

## Current paper tables

- `table_3_campanula_baseline_validation.csv`: untouched external baseline
- `table_4_campanula_area_balanced_update.csv`: post-baseline update against same-allocation random sets
- `table_5_campanula_area_balanced_top5.csv`: updated one-per-island candidate set

## Interpretation guardrails

- The baseline is retained even though it performed poorly.
- Random controls match the candidate pool, Top-k budget, and selected island allocation.
- Ten kilometres is a regional endpoint and saturates on small islands.
- The 2-km updated lift is exploratory and not statistically resolved.
- The field detections are not score-training data.
- Updating the algorithm after inspecting baseline performance converts the same field set into development evidence for the update.
