# *Campanula microdonta* development dataset

> **Status: development data, not independent confirmation.**
>
> The 2026 field outcomes have been inspected, and the
> `select_area_balanced_candidates` update was made *because* those outcomes
> exposed a failure — `METHODS_PAPER_PLAN.md` already records that update as
> post-baseline development. This taxon therefore cannot support a validation
> claim about ACSP. It is now used deliberately as a development instrument:
> somewhere to work out a candidate rule that reaches real field sites, before
> that rule is frozen and tested on untouched taxa.

This directory holds the first prospective field case study for ACSP, and the
data it produced.

## Development target

The national retrospective claim uses a 10 km endpoint. **That endpoint is
saturated here**: the Izu islands are smaller than the radius, so five
candidates placed anywhere recover about 86% of detection clusters and same-pool
random scores essentially the same (`0.8947` vs `0.8573` for the area-balanced
update). Within-island nearest-cluster separation has a median of 0.9-1.9 km, so
the working target is **19 detection clusters recovered at 1 km**.

Why a plain SDM does not settle this: the one-click SDM path derives climate from
NASA POWER MERRA-2 at a native 0.5° × 0.625° grid, about 56 × 57 km per cell. The
whole five-island system spans 64.5 × 29.2 km — roughly **1.16 × 0.51 cells** —
and Toshima occupies about 0.03 × 0.01 of one cell. A macro climate surface
cannot separate these islands from each other, let alone rank sites within one.
The informative surface here is terrain, which the app fetches from GSI per
island at 5 m.

Iterate with [`research/campanula_development_loop.py`](../../research/campanula_development_loop.py).

## Original prospective design

## Current data

`locations_2026.csv` contains 28 positive GPS rows supplied after the 2026 Izu Islands survey:

- Oshima: 13
- Toshima: 8
- Niijima: 4
- Shikinejima: 1
- Kozushima: 2

The Oshima `oshima-15` longitude is stored as `139.349870`, following the data owner's correction of the original `135.349870` entry. A duplicated Toshima coordinate is retained for audit and collapsed by the clustering analysis.

These rows are **positive detections only**. They cannot estimate detection probability, specificity, false absence, or discoveries per field day without the complete visit/effort log.

## Candidate pool

`frozen_candidate_pool.csv` **does not exist in this repository** and never did;
`frozen_candidate_pool_schema.csv` is a one-row schema example, not data. The
published Campanula numbers came from `run_temporal_external_validation.py`,
which rebuilds the pool from GBIF records through 2025 at run time.

That is a temporal external design, not an archived pre-registration, and it is
the honest description of what exists. Because the taxon is now development
data, the pool is cached for offline iteration instead:

```bash
# needs GBIF and GSI, so run it on a runner via the campanula-development-data workflow
python research/cache_campanula_development_data.py
```

which writes `development_data/{gbif_training_occurrences_through_2025.csv,
candidate_pool.csv, detection_clusters.csv, manifest.json}`.

If a genuinely pre-registered pool is ever wanted for a future expedition, export
it before fieldwork and store it as `frozen_candidate_pool.csv` with at least:

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
