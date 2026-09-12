# N4 discovery generalization package

Status: **development-only package architecture**. This does not broaden the independently validated 2.5% / 10-km regional candidate-patch product.

## Why a package boundary is needed

The current research line accumulated useful mechanics inside Campanula and Cirsium scripts, but the scientific question is taxon-neutral:

> Given prior occurrence evidence and an explicit geographic universe, where can we justify looking next without pretending to know occupancy?

A reusable implementation must therefore separate biological evidence semantics from species names, country-specific data providers, movement constraints, and held-out outcomes.

## Package decision

Keep the implementation inside the existing `acsp-survey` distribution for now, under an **explicitly imported experimental subpackage**:

```text
acsp.discovery
```

Do **not** create a second PyPI distribution yet. Splitting into `acsp-discovery` before the science is frozen would create version drift between the validated robust core and the experimental discovery layer. A separate distribution becomes reasonable only after an independent N4 validation contract has passed.

`acsp.discovery` is intentionally not imported by `acsp.__init__`; importing the validated package path therefore does not activate planning/discovery dependencies or broaden the validated claim.

## Architecture

```text
provider-specific evidence
        |
        v
standard occurrence schema
        |
        v
bounded complete-link populations
        |
        v
population medoids / typed evidence
        |
        v
explicit evidence-adequacy gate
        |
        +----------------+----------------+----------------+
        |                |                |                |
      LOCAL           DETACHED         SENTINEL         ABSTAIN
        |                |                |
        +----------------+----------------+
                         |
                         v
              declared candidate frame
                         |
                         v
              source-backed G_E support
                         |
             +-----------+-----------+
             |           |           |
        structural   nearest      spatial
          order      baseline     baseline
             |           |           |
             +-----------+-----------+
                         |
                         v
                  pre-outcome freeze
                         |
                         v
             G_F movement feasibility
                         |
                         v
             prospective field effort
```

The ecological graph `G_E` and human movement/feasibility graph `G_F` remain separate. Roads, permissions, safety and travel time cannot create ecological support.

## Implemented generic APIs

### `acsp.discovery.evidence`

- deterministic complete-link occurrence clustering;
- bounded cluster diameter rather than single-link chaining;
- one observed medoid per population cluster;
- no taxon-specific rule.

### `acsp.discovery.regimes`

- `LOCAL_CONTINUATION`;
- `DETACHED_COMPONENT`;
- `SENTINEL`;
- `ABSTAIN_LOCAL_PATCH`.

The gate deliberately does **not** infer LOCAL from anchor count. `local_component_justified` must come from a separately frozen evidence-adequacy rule. This prevents the post-result 8+ anchor diagnostic from becoming a hidden production threshold.

### `acsp.discovery.frames`

- deterministic metric-grid annular frames;
- explicit known-point exclusion;
- explicit outer radius;
- optional predeclared WGS84 sector clipping;
- no occurrence-outcome or access input.

### `acsp.discovery.structural`

- outcome-blind `G_E` construction;
- frozen raw-layer adapters;
- row-min conjunctive support;
- full deterministic structural order;
- provenance hash over source semantics and family identity.

The current structural families are implementations, not universal truths:

- wetland/moisture;
- alpine topographic;
- open grassland;
- coastal/island;
- forest edge.

Additional families require a new source-backed contract; they must not be fitted by inspecting held-out discoveries.

### `acsp.discovery.comparators`

- complete nearest-anchor order;
- memory-safe stable-start geographic maximin selection.

The maximin implementation is O(n) memory and O(n*k) time. A full ranking of a very large candidate grid is still quadratic time. The package must never silently switch comparator algorithms because a frame is large; any scalable alternative (for example a space-filling design) needs an explicit method identity and its own frozen comparison contract.

## Provider abstraction and Japan/global portability

The discovery core consumes standardized tables rather than fetching GSI/GBIF/WorldCover internally. Concrete providers are adapters outside the scientific core.

A provider bundle has four independent responsibilities:

1. **geographic frame provider** — declares the broad search universe;
2. **occurrence provider** — supplies typed historical evidence with precision provenance;
3. **environment/structure provider** — supplies the raw variables required by a frozen family;
4. **movement provider (`G_F`)** — applies human feasibility after ecological candidates exist.

This is the main generalization lesson from the Japan/global experiments. A globally portable ecological rule is not enough: provider coverage, candidate-surface density and temporal observability must each be auditable. Missing provider support must return `ABSTAIN`/not-evaluable, not silently substitute a different scientific method.

### Current Japan bundle

The current development implementation can use public GBIF occurrence evidence and Japanese GSI terrain; some families additionally require ESA WorldCover and a frozen coastline/component source. This is a provider bundle, not part of the mathematical definition of N4 discovery.

### Global bundle

A global bundle should implement the same normalized schemas with explicitly pinned global providers. It must pass provider-coverage and candidate-generation audits **before** held-out outcome retrieval. No automatic Japan-specific fallback is allowed.

## Validation ladder

The package intentionally reports different evidence levels.

1. **mechanics** — deterministic unit tests, leakage guards, provenance hashing;
2. **development** — consumed/opened taxa used to reject or diagnose methods;
3. **nomination** — unchanged method beats strong same-frame comparators on development data;
4. **independent confirmation** — new disjoint taxon/region cohort with no rescue or retuning;
5. **provider portability** — the same end-to-end contract passes across provider/geographic strata;
6. **field efficiency** — only after complete prospective effort plus detection/non-detection logs.

The validated regional 2.5% robust core is already at a different, closed validation endpoint and remains untouched.

## What should not be generalized yet

Do not package the following as scientific defaults:

- a fixed anchor-count cutoff for LOCAL;
- a fitted distance/environment blend;
- a universal 2-km or 5-km local radius;
- automatic family selection from held-out outcomes;
- route/day/budget optimization as part of ecological candidate membership;
- discoveries/hour or stopping rules without complete prospective effort data.

## Near-term implementation target

The next reusable unit should be a provider-normalization layer that converts a source bundle into:

```text
occurrence_evidence.parquet
candidate_frame.parquet
source_manifest.json
```

with standard column/provenance checks. The algorithm above those files can then be identical for a Japanese Cirsium, another Japanese taxon, or a global taxon; only provider adapters and the predeclared structural family change.
