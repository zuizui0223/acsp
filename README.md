# ACSP - Adaptive Complementarity-based Survey Prioritization

ACSP is a Streamlit app for turning occurrence records into ranked, field-ready survey-site sets.

The app is no longer just a GBIF map builder. It integrates known records, optional SDM/SSDM prediction, local habitat-analogue discovery, accessibility proxies, and field-validation feedback to help researchers decide where to survey next.

## Core Idea

ACSP is designed for field-survey planning, not as a full all-record SDM platform.

The central workflow is:

1. Organize known occurrence records.
2. Generate occurrence-supported survey candidates.
3. Optionally use SDM/SSDM as a broad macro-scale filter.
4. Search for local habitat analogues and informative contrast sites.
5. Select a complementary set of survey sites under fieldwork constraints.
6. Export sites, visit them, and feed validation results back into the ranking.

## Four App Layers

### 1. Known Records

- GBIF occurrence download or researcher-owned coordinate CSV upload.
- Flexible latitude/longitude column detection.
- Coordinate QC and exclusion of suspect records.
- Date, year, and flowering-season summaries when available.
- DBSCAN-based occurrence cluster candidates.
- Known-distribution and survey-area maps.

This layer identifies occurrence-supported sites where the species is already known or strongly supported by records.

### 2. SDM / SSDM

- Optional single-species ensemble SDM.
- Optional genus-level SSDM for stacked species distribution modeling.
- WorldClim/environmental predictors with VIF and correlation diagnostics.
- Spatial validation options: block, checkerboard, random holdout, random k-fold, and jackknife.
- Raster-style SDM predict maps.
- SDM-high and SSDM-high exploratory candidates.

This layer is a macro-scale filter. SDM/SSDM support can re-rank candidates or identify model-only exploration sites, but occurrence-supported candidates remain usable without SDM.

### 3. Potential Survey Sites

Potential Survey Sites is a local habitat-discovery layer.

It builds grid-cell candidates beyond known occurrence clusters:

- `Habitat analogue`: environmentally similar to known sites but not yet recorded.
- `Under-surveyed analogue`: similar habitat with low local record density.
- `Environmental contrast`: deliberately different or edge-like habitat to test limits and learn absence/contrast information.

The app builds a local known-site habitat profile from variables such as:

- elevation
- slope
- aspect
- terrain roughness
- topographic position index
- coastline distance proxy
- optional OpenStreetMap road, trail, and forest-edge distance proxies

Candidate cells are scored with interpretable local metrics such as Mahalanobis environmental distance, environmental similarity, survey-gap score, environmental novelty, and accessibility proxies.

SDM remains separate: it can be used as a broad search-frame filter, while local habitat analogue scoring remains the main Potential Survey Sites logic.

### 4. ACSP Set Selection and Export

ACSP selects survey-site sets, not only individual high-score points.

The greedy marginal-gain selection considers:

- base occurrence/model priority
- geographic complementarity
- environmental complementarity
- exploration value
- sampling-gap coverage
- local habitat-analogue support
- field-validation learning support
- access feasibility
- redundancy penalty
- travel penalty

Available modes include:

- `Simple top-ranked`
- `Complementarity-based batch selection`
- `Habitat analogue survey`
- `Exploration-focused active survey`
- `Phylogeographic gap-filling`

Outputs include selected-site tables, Google Maps links, CSV, KML, HTML, and field-validation CSV templates.

## Field-Validation Learning

ACSP can ingest a previous validation CSV with matching `site_id` values and result columns such as `target_species_found`, `found`, or `detected`.

When enough positive and negative outcomes are available, the app learns a lightweight `field_validation_support_score` and uses it as one optional component in future ranking.

This is currently a practical re-ranking tool, not a full online occupancy model.

## Current Scientific Status

Implemented and usable:

- occurrence-supported candidate generation
- optional SDM/SSDM support
- local habitat analogue candidates
- under-surveyed and environmental-contrast candidates
- app-provided terrain and access/edge proxies
- ACSP complementary set selection
- field-validation score feedback
- fieldwork-oriented exports

Still under active development:

- app-provided NDVI and land-cover sources
- stronger survey-effort modeling using broader all-taxa records
- explicit discovery-value vs learning-value modes
- real travel-time routing and ferry/day constraints
- richer field-result modeling for detectability, access failure, and flowering state
- retrospective validation experiments against hidden occurrence records

## Local Install

```bash
python -m pip install -r requirements.txt
```

## Run Locally

```bash
python -m streamlit run gbif_fieldmap_builder_app.py
```

## Streamlit Community Cloud

Use:

- Repository: `zuizui0223/acsp` or the redirected legacy repository
- Branch: `main`
- Main file path: `gbif_fieldmap_builder_app.py`

## Notes

Google Maps links are provided for field verification. ACSP does not guarantee road access, ferry feasibility, trail safety, permission, or detectability. Field validation remains part of the intended workflow.
