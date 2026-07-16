# ACSP algorithm research notes

This file is append-only. Each iteration records a falsifiable hypothesis, the smallest implementation used to test it, and the decision made from validation.

## 2026-07-16 — Iteration 1: occurrence relation graph

### Repeated failure pattern

Previous experiments changed resolution, local covariates, candidate subdivision, ranking weights, spatial allocation, routing, or patch aggregation. These improved software behavior and field presentation, but retained the same mathematical object: a scalar attribute attached to each candidate cell or point. The five-kilometre audit showed that candidate generation retained some recovery headroom while learned candidate rankers generalized below random. Fine terrain, WorldCover point classes, patch interiors, landscape composition, and strict child-cell replacement did not improve recovery. The common failure is therefore not primarily raster resolution. It is the assumption that independently scoring candidate attributes is sufficient to reconstruct occurrence structure.

### Mathematical diagnosis

Let `x_i` denote candidate features. The existing family ultimately computes or learns a scalar `s(x_i)` and then adds diversity, allocation, or route rules after scoring. Even when the score is called support rather than suitability, it remains pointwise. Sparse presence-only data do not identify a transferable pointwise response at fine scales, and local refinements introduce many nearly exchangeable candidates with no new species-specific information. The ranking problem becomes high variance while the downstream heuristics cannot repair the missing object.

### Hypothesis

Occurrence records contain more stable information about *relations among observed ecological states* than about an absolute response surface. Infer a sparse occurrence relation graph in arbitrary feature space, then choose survey candidates that collectively cover its edges. The inferred object is the graph itself, not a raster or suitability vector.

### Minimal implementation

`acsp/relations.py` adds three operations:

1. robustly scale an arbitrary occurrence feature matrix;
2. infer mutual k-nearest-neighbour edges among occurrences;
3. calculate candidate membership near each finite graph edge and greedily maximize weighted relation coverage.

The set objective is

`F(S) = sum_e w_e max_{i in S} r(i,e)`.

Repeated candidates on the same ecological relation therefore have diminishing return. No pseudo-absence, background sample, classifier, raster, geographic coordinate, or presence probability is required. The only structural parameter is the neighbour count `k`.

### Components that already exist in the literature

- Mutual k-nearest-neighbour graphs, robust scaling, distance to a line segment, facility-location coverage, and greedy maximization of monotone submodular objectives are established mathematical components.
- Graph ecology and landscape connectivity infer relations among habitat patches or populations, usually in geographic space and commonly from resistance or dispersal assumptions.
- Point-process models estimate occurrence intensity; occupancy models estimate latent occupancy and detection; SDM/ENM/MaxEnt estimate a response or relative intensity over environmental/geographic space.
- GRTS and spatially balanced designs spread samples over a target frame; adaptive and cluster sampling expand sampling based on observed outcomes; active learning selects observations to improve a predictive model.
- Manifold learning, principal graphs, and topological data analysis infer geometric or topological structure from point clouds.

### Proposed novelty boundary

The potentially novel contribution is not any component above. It is the ecological decision object and coupling:

> infer a species-specific graph of local relations among occurrence states in replaceable feature space, and select field sites by coverage of those occurrence relations rather than by predicted presence, spatial balance, or model uncertainty.

This claim must be weakened or abandoned if literature review finds a method with the same occurrence-graph-to-survey-set formulation, or if validation shows no reproducible benefit over current ACSP and same-pool random selection.

### Tests added

- mutual local relations are recovered on a two-cluster example;
- results are invariant to changes in feature units;
- relation coverage selects two distinct relations rather than duplicate high-membership candidates;
- deterministic tie handling;
- arbitrary feature dimension.

### Validation result and decision

The initial line-segment relation membership was replaced by a stricter relation witness because a line segment incorrectly assumes support for unobserved intermediate states. In the frozen Campanula candidate pool, fixed `k=3` relation witness and point-prototype coverage both produced 10 km recovery of 0.632 with the same median nearest-detection distance of about 3.82 km. The graph therefore added no measurable information beyond the occurrence nodes. Because k-nearest-neighbour edges are deterministic functions of node locations, edge coverage can collapse to ordinary point-cloud coverage.

**Decision: reject the occurrence-relation graph as the central algorithm.** Keep the implementation and benchmark only as a documented negative result. Do not add edge weights, persistence, routing, higher simplices, or access heuristics to rescue it.

## 2026-07-16 — Iteration 2: local ecological contrast operator

### Hypothesis

Absolute environmental values transfer poorly across islands and regions because the entire available environment shifts. A more stable ecological object may be the transformation from locally available environments to occupied relative states. For region `g`, each occupied feature is mapped to its centred empirical rank within the availability frame `A_g`:

`delta_gj = 2 * rank(x_gj | A_gj) - 1`.

The inferred object is the set of group-level occupied contrast vectors and their robust cross-group median, not a suitability surface.

### Minimal implementation

`acsp/contrast.py` implements:

1. empirical contrast transformation in arbitrary feature space;
2. group-balanced fitting of occupied contrasts against matched local availability;
3. feature reliability from cross-group agreement;
4. candidate transformation against the availability of its own target group;
5. batch selection by marginal coverage of observed contrast states.

Only empirical ranks are used, so the operator is invariant to group-specific location shifts and monotone feature rescaling. Constant features map to zero. No pseudo-absence, classifier, raster grid, or presence probability is fitted.

### Tests

- constant features carry zero contrast;
- identical relative selection is invariant to large group-specific environmental shifts;
- candidates are transformed only against their own availability group;
- contrast-state coverage avoids duplicate selections;
- shifted regions with the same relative occupied state match the same operator.

### Campanula validation design

The frozen 2025-or-earlier GBIF records, frozen candidate pool, and independent 2026 detections are retained. Because the archived occurrence table lacks sampled terrain values, each historical occurrence is provisionally mapped to the nearest candidate environment within the same island. This approximation is exported and must not be hidden. The comparison uses identical area balancing and Top-5 size for:

- current ACSP;
- absolute environmental prototype coverage;
- ecological contrast.

Runtime and peak memory are recorded. The 2026 detections are read only for final evaluation.

### Acceptance rule

Do not adopt the contrast operator unless it exceeds both the area-balanced absolute prototype and same-quota random selection in cross-taxon leave-one-region-out validation. Campanula improvement alone is insufficient. If performance depends strongly on the availability definition or direct occurrence-environment extraction removes the signal, reject or reformulate the operator.
