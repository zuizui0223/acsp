# ACSP - Adaptive Complementarity-based Survey Prioritization

ACSP is a Streamlit app for turning occurrence records into ranked, field-ready survey-site sets.

The app is no longer just a GBIF map builder. It integrates known records, optional SDM/SSDM prediction, local habitat-analogue discovery, accessibility proxies, and field-validation feedback to help researchers decide where to survey next.

## Reusable packages

The repository includes early ACSP methods packages for Python and R. They expose survey-area quotas, occurrence-count/spatial-span partition selection, and manuscript-ready SDM method records without depending on Streamlit.

Python development install:

```bash
python -m pip install -e .
```

```python
from acsp import choose_spatial_partition, recommend_candidates

recommended = recommend_candidates(candidates, per_area=3)
partition, reason = choose_spatial_partition(86, geographic_span_degrees=1.8)
```

R development install:

```r
remotes::install_local("r-acsp")
library(acsp)

recommended <- acsp_recommend(candidates, per_area=3)
partition <- acsp_sdm_partition(86, geographic_span_degrees=1.8)
```

## Automatic workflow

The main screen asks for a species or genus name. ACSP fetches a representative GBIF subset, applies occurrence QC, and builds observed-data candidates. Users may draw one or more survey areas; each area receives an independent candidate pool and recommendation quota.

The app shows two directly comparable results:

1. `Candidates without SDM/SSDM`, based on observed records and local habitat evidence.
2. `Candidates with SDM/SSDM`, generated only after the optional model action.

Both maps show the full candidate pool and highlight recommended sites. SDM/SSDM diagnostics report spatial validation, ensemble members, best individual model, environmental variables, QC counts, and exportable method metadata. Researcher-owned CSV input and the detailed legacy analysis functions remain in the codebase for compatibility.

For widespread taxa, the app no longer mixes nationwide sites into one trip. Region recommendations use compact approximately 40 km-radius hubs. Every field day now begins and ends at the selected hub, uses a 35 km/h average road speed, a 1.35 road-distance factor, and keeps a 15% operational reserve for navigation, parking, breaks, and delay. Search time, access time, usable daily hours, repeat visits, and interpretation cautions are inferred from broad GBIF taxonomy (for example plant, bird, amphibian, arthropod, mammal, or fish). Candidate count is reduced until each day fits. These are transparent reconnaissance defaults, not a road-routing or species-method guarantee.

The Known distribution map remains available in the ordinary result flow. Users can choose another suggested region or draw a rectangle/polygon and rebuild within their own study area without making map drawing a prerequisite for receiving an answer.

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

- `Habitat-match`: environmentally similar to known sites but not yet recorded.
- `Survey-gap`: similar habitat with low local record density.
- `Environmental-test`: deliberately different or edge-like habitat to test limits and learn absence/contrast information.

The app builds a local known-site habitat profile from variables such as:

- elevation
- slope
- aspect
- terrain roughness
- topographic position index
- coastline distance proxy
- optional OpenStreetMap road, trail, and forest-edge distance proxies

Candidate cells are scored with interpretable local metrics such as Mahalanobis environmental distance, environmental similarity, survey-gap score, environmental novelty, and accessibility proxies.

Local DEM, NDVI, and land-cover GeoTIFFs can be uploaded directly. ACSP-Discover prevents false precision by choosing a cell width no finer than the coarsest supplied raster, the 75th percentile of coordinate uncertainty, or the practical field-search scale. Without a local raster, the built-in approximately 4.5 km elevation layer limits the effective cell width accordingly.

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

The default v1 result presents three plans made from the same eligible pool:

- `Balanced`: balances discovery, learning, representation, access, and movement.
- `Discovery`: prioritizes likely new populations and feasible access.
- `Learning`: prioritizes uncertainty, environmental boundaries, and representation.

Known hard constraints are applied before scoring, with a downloadable exclusion/unknown-data audit. Advanced legacy modes remain available for comparison, including:

- `Simple top-ranked`
- `Complementarity-based batch selection`
- `Habitat analogue survey`
- `Exploration-focused active survey`
- `Phylogeographic gap-filling`

Outputs include selected-site tables, Google Maps links, CSV, KML, HTML, and field-validation CSV templates.

## Field-Validation Learning

ACSP can ingest a previous validation CSV with matching `site_id` values and a standard `result` field (`found`, `not_found`, `flowering_absent`, `inaccessible`, or `uncertain_id`), as well as older result columns such as `target_species_found`, `found`, or `detected`. Only determinate `found`/`not_found` outcomes train the presence-support model.

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
