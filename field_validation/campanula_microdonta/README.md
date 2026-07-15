# *Campanula microdonta* prospective field validation

This directory holds the first prospective field case study for ACSP.

## Current data

`locations_2026.csv` contains 28 positive GPS rows supplied after the 2026 Izu Islands survey:

- Oshima: 13
- Toshima: 8
- Niijima: 4
- Shikinejima: 1
- Kozushima: 2

The Oshima `oshima-15` longitude is stored as `139.349870`, following the data owner's correction of the original `135.349870` entry. A duplicated Toshima coordinate is retained for audit and collapsed by the clustering analysis.

These rows are **positive detections only**. They cannot estimate detection probability, specificity, false absence, or discoveries per field day without the complete visit/effort log.

## Required frozen input

Recover the exact candidate-pool CSV exported before field outcomes were inspected and store it as:

`frozen_candidate_pool.csv`

Do not regenerate candidates now and label them as prospective predictions. The file should include at least:

- `site_id`
- `survey_area_id`
- `latitude`, `longitude`
- `candidate_type`
- `priority_rank`, `priority_score`
- `is_recommended`
- algorithm commit/release and generation time

`frozen_candidate_pool_schema.csv` is a schema example, not analytical data.

## Analysis

Install the package, then run:

```bash
python field_validation/campanula_microdonta/analyze.py \
  --candidate-pool field_validation/campanula_microdonta/frozen_candidate_pool.csv
```

The analysis:

1. clusters nearby positive GPS rows into independent detection units;
2. measures nearest frozen-candidate distance;
3. reports recovery at 0.5, 1, 2, 5, and 10 km;
4. compares the frozen ACSP set against random sets drawn from the identical candidate pool;
5. preserves the number of selected candidates per survey area/island.

The primary claim remains the pre-supported **10 km regional-zone** endpoint. Smaller radii are sensitivity analyses.

## Interpretation

This case study complements, rather than replaces, the national unseen-taxon retrospective benchmark. Retrospective recovery tests ranking transferability. The field case tests whether a recommendation object remains useful when taken into a real expedition.

A positive-only recovery result should be described as field-detection-cluster recall. It must not be described as occupancy-model accuracy or detection probability.
