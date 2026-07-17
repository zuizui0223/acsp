# EOG manuscript execution roadmap

## Target contribution

Environmental occupancy geometry (EOG) is presented as a point-cloud description of occupied environmental states. The manuscript should focus on two primary graph-derived quantities:

1. continuity, describing direct versus tortuous occupation paths;
2. gap strength, describing the strongest internal discontinuity relative to typical local connections.

Span is a supporting breadth quantity. Component count and candidate projection remain diagnostics.

## Phase 1: freeze the method

- [ ] Freeze equations and notation for continuity and gap strength.
- [ ] Add explicit input requirements and edge-case behavior to public docstrings.
- [ ] Add tests for duplicate states, one-dimensional inputs, small sample sizes, missing values, and high-dimensional noise.
- [ ] Record whether robust scaling is part of the formal estimator or a default preprocessing option.
- [ ] Freeze the direct CHELSA variable set used for the main benchmark.
- [ ] Tag an analysis-interface release before expanding the cohort.

## Phase 2: novelty audit

Maintain an auditable literature table containing:

- citation and DOI;
- ecological object analysed;
- graph or topological construction;
- whether an MST is used;
- whether the largest MST edge or diameter/MST ratio is reported;
- relation to niche breadth, hypervolume, fragmentation, or multimodality;
- exact overlap with EOG;
- defensible distinction;
- implication for terminology and claims.

Required comparison families:

- ecological niche and trait hypervolumes;
- convex hull, alpha hull, and kernel hypervolume;
- single-linkage clustering and MST edge cutting;
- graph-based cluster-validity statistics;
- persistent homology and topological data analysis in ecology;
- ecological niche holes and disconnected hypervolumes;
- point-cloud geodesic, elongation, and tortuosity measures;
- environmental novelty and MESS/MOP-style methods;
- occupancy point-process and occurrence-only niche descriptors.

No novelty statement should be finalized until this table is complete.

## Phase 3: expanded frozen validation

- [ ] Predeclare at least 30-50 taxon-region pairs.
- [ ] Stratify across plants, vertebrates, invertebrates, and ferns where technically feasible.
- [ ] Preserve failed and uninformative pairs in the audit output.
- [ ] Separate technical eligibility from metric performance.
- [ ] Use fixed seeds and archived taxon lists.
- [ ] Report full distributions, not only medians and gates.
- [ ] Add sensitivity analyses for record count, dimensionality, scaling, duplicated raster cells, and spatial sampling bias.

## Phase 4: comparator expansion

At minimum compare against:

- PCA breadth;
- covariance or Gaussian volume;
- convex-hull and kernel-hypervolume summaries;
- K-means and single-linkage diagnostics;
- largest single-linkage merge height;
- persistent-homology summaries where computationally feasible;
- nearest-prototype and nearest-occurrence distances.

The goal is not to force EOG to win every benchmark. The analysis should identify which ecological structures each method can and cannot distinguish.

## Phase 5: independent biological case study

Only after the general method and analysis plan are frozen:

- select one biological system with a preregistered ecological hypothesis;
- keep it out of metric development and threshold selection;
- explain what continuity or gap strength means biologically before analysing outcomes;
- compare conclusions with conventional niche summaries;
- avoid treating candidate-site projection as the novelty claim.

## Phase 6: reproducible manuscript bundle

The submission release should include:

- exact environment-source metadata and raster versions;
- frozen taxon-region declarations;
- raw pair-status files;
- repeat-level benchmark outputs;
- summary-generation scripts;
- figure-generation scripts;
- machine-readable software environment;
- CITATION metadata and archived DOI;
- a manuscript-to-artifact provenance table.

## Provisional manuscript structure

1. Introduction: breadth and volume do not fully describe connectedness or internal discontinuity.
2. Methods: point-cloud preprocessing, MST construction, definitions, edge cases, and computational complexity.
3. Synthetic validation: controlled identifiability beyond matched moments.
4. Random taxon-region validation: thinning stability and technical eligibility.
5. Method comparison: conventional and topological comparators.
6. Independent case study.
7. Discussion: interpretation, limits, sampling bias, dimensionality, and relationship to SDMs and hypervolumes.

## Submission decision gate

Do not submit until all are true:

- novelty audit completed and terminology adjusted to prior art;
- method API and equations frozen;
- expanded validation cohort completed;
- at least one hypervolume and one graph/topology baseline implemented;
- independent case study analysed without method tuning;
- all central manuscript numbers trace to archived artifacts.
