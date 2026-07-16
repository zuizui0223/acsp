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

### Validation status

Not yet accepted. Unit tests establish only implementation semantics. The next required experiment is an adapter to the existing random-taxa benchmark using exactly the same training folds and candidate pools, followed by Campanula temporal external validation and runtime/memory measurement. No production workflow should use this method before those comparisons.

### Rejection rule

Remove or redesign this direction if either condition holds:

1. mean same-pool lift is not positive on development taxa and remains non-positive on untouched confirmation taxa; or
2. any gain is explained by ordinary environmental medoid/coverage sampling rather than graph relations.

The first ablation must therefore compare relation-edge coverage against point-prototype coverage with the same scaling and candidate pool.

### Next idea if rejected

Infer higher-order occurrence simplices only if edge coverage shows signal but systematically misses multi-modal or branching structure. Do not add persistence, routing, accessibility, or adaptive feedback merely to rescue a failed edge object.

## 2026-07-16 — Iteration 1b: relation witness and first ablation

### Hypothesis

The first edge-membership definition used distance to the finite segment between two occurrences. This silently assumed that every environmental state between the endpoints was ecologically supported. Replace that interpolation with a relation witness: a candidate represents an edge only when it is simultaneously close to both observed endpoints.

### Implementation

`acsp/relation_witness.py` computes endpoint kernels and uses their geometric mean. `test_relation_witness.py` checks feature-unit invariance and verifies that support from only one endpoint is insufficient. The Campanula workflow now runs a predeclared `k=3`, Top-5 comparison against current ACSP and point-prototype facility coverage, recording runtime and peak memory.

### Exploratory result before CI rerun

A replay using the previously archived Campanula artifact gave the following 10 km field-cluster recall:

- current unbalanced ACSP Top-5: 0.263;
- point-prototype environmental coverage: 0.632;
- occurrence-relation witness: 0.632.

The relation object therefore produced no observed benefit over node/prototype coverage. The result uses nearest-candidate terrain as a proxy for terrain at historical occurrence coordinates and is not confirmatory, but it is already sufficient to reject a performance claim for graph edges.

### Failure reason

A k-nearest-neighbour edge is a deterministic transformation of occurrence node positions. It introduces no new ecological observation. If candidate-edge membership is constructed only from endpoint distances, the edge-cover objective can collapse to ordinary point-cloud coverage. Adding higher-order simplices would repeat the same mistake because those simplices would also be derived solely from the same nodes.

### Decision

Do not promote occurrence-relation edges to production. Retain the code only as a falsified research branch and benchmark baseline. Do not rescue it with edge weights, persistence, route terms, or parameter search.

### Next mathematical object

The next admissible object must contain information absent from the occurrence point cloud itself. The proposed object is an **ecological contrast operator**: for each geographically independent occurrence, compare its feature vector with the locally available feature distribution and infer recurrent directions of selection. This estimates a transformation from local availability to occupied state, not presence probability and not point geometry.

A minimal formulation is:

`delta_g = robust_rank(x_occurrence_g | A_g) - 0.5`,

where `A_g` is the locally available feature matrix for independent region `g`. Recurrent contrast structure is inferred from the cross-region matrix of `delta_g` vectors. Candidate sets are then chosen to represent distinct recurrent contrast directions. This remains raster-free and accepts arbitrary feature matrices, but unlike the rejected graph it requires explicit local availability information and therefore contains a new empirical relation rather than a graph manufactured from occurrence coordinates alone.
