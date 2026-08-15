# Campanula microenvironment development — full-island discovery

Status: **development only**. The 2026 field coordinates have already been inspected and may be used to measure development loss, but they are not independent validation. The candidate generator itself must not read them.

## Why islands

At the scale of the five Izu islands used here, broad climatic rasters can be nearly uniform within an island and are too coarse to identify the local places actually searched in the field. The development hypothesis is therefore that within-island occurrence structure is better resolved by public microenvironment proxies: terrain, vegetation/land cover, vegetation greenness, surface thermal environment, coastal exposure, and their local transitions.

This is not a claim that climate is ecologically irrelevant. Climate remains a broad regional support layer; the immediate discovery problem is to explain the fine spatial separation that remains inside climatically similar islands.

## Frozen development observations

- pre-2026 GBIF training cache: 281 records globally, 56 falling inside the five development island rectangles;
- 500 m spatial thinning leaves 18 island microterrain prototypes;
- 2026 field detections: 28 GPS rows, one duplicate retained for audit;
- 500 m clustering: 19 field-detection clusters;
- old leakage-controlled validation pool: 97 candidates, only 13/19 clusters reachable within 1 km;
- current survey pool: 102 candidates, also only 13/19 clusters reachable within 1 km.

The old failure is therefore upstream of ranking: the candidate universe itself omitted six observed clusters.

## First full-island experiment: microterrain only

`research/campanula_microterrain_discovery.py` removes the old parent-cell refinement bottleneck.

Generator inputs:

1. pre-2026 GBIF occurrences only;
2. public GSI DEM mosaics;
3. no 2026 field coordinate, detection flag, or distance to a 2026 point.

For each GBIF occurrence and each approximately 100 m island grid location, it derives a compact microterrain state from a ~25 m working surface:

- elevation;
- local mean slope and slope heterogeneity;
- local roughness;
- TPI at ~100 m and ~300 m scales;
- local elevation range proxy.

GBIF occurrences are thinned at 500 m, robustly scaled, and treated as occurrence-conditioned microterrain prototypes. Every full-island grid cell receives its nearest prototype distance. Only after the entire candidate universe and distances are frozen are the 2026 clusters read to map the development frontier.

### Result

The first run used 22,784 usable ~100 m grid cells.

| target radius | smallest grid fraction retaining 19/19 | max nearest candidate distance |
|---|---:|---:|
| 1.0 km | 0.0750 | 0.9395 km |
| 0.5 km | 0.3370 | 0.2757 km |
| 0.25 km | 0.5650 | 0.2466 km |
| 0.1 km | 0.8620 | 0.0792 km |

Thus the full-island search removes the previous 13/19 candidate-generation ceiling: **all 19 field clusters are reachable within 1 km using microterrain states learned only from pre-2026 GBIF occurrences.**

## Important negative result / upper bound

Terrain alone is not selective enough for exact local discovery.

At the 1 km frontier, about 7.5% of all usable grid cells remain. A same-island random set with the same number of points reaches all 19 clusters frequently, so 19/19 at 1 km is not sufficient evidence that the terrain score has identified the biologically relevant local patches.

At 500 m the terrain-only frontier requires about 34% of the grid, and at 250 m about 57%. These fractions are too broad to be a useful final field-discovery product. This is the current **terrain-only information ceiling**: terrain can recover the observed microenvironment support envelope, but cannot by itself localize the occupied patches sharply enough.

## Next data layers — add only when they shrink the frontier

The next experiments should add public layers one at a time, always keeping the generator blind to 2026 outcomes:

1. land-cover class / neighborhood composition at 10 m;
2. NDVI or vegetation-composite statistics at 10 m;
3. land-surface temperature / thermal contrast at Landsat scale;
4. coast distance / exposure and terrain–cover transition features;
5. only after those static features are tested, persistent patch structure across thresholds and scales.

A new layer is retained only if it reduces the candidate-grid fraction or route/search budget needed for complete recovery without creating a new miss. Raw 19/19 alone is not a promotion criterion.

## Development objective

The practical target is a Pareto frontier, not an unconstrained perfect fit:

- maximize recovery of all 19 development clusters;
- minimize candidate area / candidate count;
- minimize equal-area random success;
- stabilize the selected patches across thresholds, feature subsets, and occurrence thinning;
- explicitly report the best attainable frontier if 100% recovery cannot coexist with useful selectivity.

After this method is frozen, `Campanula microdonta` must not be reused as validation evidence. Generalization is tested on random taxon–region cohorts with untouched outcomes.
