# Occurrence-anchored local discovery development line

## Status and boundary

This is a **development-only** redesign motivated by inspected *Campanula microdonta*
field outcomes. It does not alter or weaken the independently confirmed ACSP
robust candidate-patch product, whose validated endpoint remains 10-km held-out
occurrence enrichment inside the fixed Japanese regional frame.

The new line addresses a different question:

> Given one or more known occurrence clusters, where should a field team search
> next for an unrecorded local population or a detached continuation of the same
> population system?

It is not an occupancy model, a global name-only survey planner, or an argument
that all new populations occur near old records.

## Why the current ecological core does not localize unknown populations

The existing robust-support core can reconstruct a broad occurrence-conditioned
support envelope. In the Campanula development data, full-island generation
places support within 1 km of all 19 inspected field clusters, but only by
retaining a broad candidate envelope. Terrain alone needed roughly 7.5% of all
usable island cells at the 1-km frontier, about 34% at 500 m, and about 57% at
250 m. Generic WorldCover categories and terrain refinements did not shrink that
frontier reliably.

This means that the failure is no longer simply “the unknown point was absent
from the candidate universe.” The harder problem is **non-identifiability within
the support envelope**: many cells share the same coarse terrain or vegetation
state, while only some contain an occupied patch.

The present field table contains positive detections only. Without a complete
visited-site and effort log, it cannot identify detection probability, false
absence, or expected discoveries per hour. Any adaptive yield model must
therefore remain unavailable until standardized detection and non-detection
records exist.

## Descriptive anchor audit

`research/diagnose_campanula_occurrence_anchor.py` assigns pre-2026 GBIF records
to the five frozen island rectangles and measures the nearest same-island
historical occurrence for each 500-m 2026 detection cluster.

This audit is descriptive development evidence. The field outcomes have already
been inspected, so the resulting distance bands cannot be treated as independent
validation or used to claim a universal search radius.

The audit separates three data regimes:

1. **local continuation** — an existing same-island anchor is nearby;
2. **detached or regional tail** — an anchor exists, but the new cluster is
   separated enough that pure nearest-neighbour search can miss it;
3. **anchor-absent exploration** — no prior same-island occurrence exists.

These regimes must not be pooled into one score and then interpreted as one
general discovery problem.

## Proposed estimand

For a declared movement-feasible search graph \(G\), retained known occurrence
clusters \(O\), and standardized field effort \(E\), the eventual estimand is:

\[
\Pr(\text{new detection cluster in patch } P
\mid O, G, \text{microhabitat state}, E).
\]

Until effort-aware field outcomes exist, development is limited to
outcome-blind candidate construction and positive-cluster recovery diagnostics.

## Candidate construction

### 1. Cluster historical occurrences before searching

Raw GBIF rows are not independent anchors. Records are spatially clustered
before candidate generation. Duplicate specimens, repeated observations, and
multiple records from the same local population must not create artificial
support.

### 2. Build a movement-feasible local graph

Candidate nodes are generated from roads, trails, coastlines, terrain-supported
land cells, and other reachable search surfaces. Edges are allowed only when the
user-specified movement mode permits traversal. The user supplies movement
constraints only; the algorithm determines the search extent, patch count, field
days, and stopping point from marginal expected value.

### 3. Exclude trivial rediscovery

A small exclusion buffer around retained known occurrence clusters is assigned
zero “new discovery” value. The exact buffer is a development parameter and
must be frozen before untouched evaluation. This prevents a method from winning
by returning the coordinates already supplied as input.

### 4. Score local continuation and detached fragments separately

A local-continuation score should combine:

- distance along the feasible landscape graph, not straight-line distance alone;
- similarity to the anchor cluster in species-relevant microhabitat;
- continuity of edge, slope, substrate, moisture, vegetation state, and
  disturbance proxies;
- a penalty for ecological or movement barriers;
- a novelty term that rewards an unvisited continuation without rewarding
  unsupported extrapolation.

A detached-fragment score should search for a similar microhabitat component
separated by a short barrier or gap. It is not merely a larger distance bonus.

A generic form is:

\[
S(P)=K_{\mathrm{anchor}}(P)\,
H_{\mathrm{micro}}(P)\,
C_{\mathrm{graph}}(P)\,
N_{\mathrm{unvisited}}(P)
-\lambda\,C_{\mathrm{field}}(P),
\]

where the anchor kernel is annular rather than monotone: already-known points
are excluded, nearby continuations are favored, and support decays before
unbounded extrapolation.

### 5. Keep anchor-absent exploration separate

An island or component with no historical anchor cannot be evaluated as a
failure of local continuation. It enters a separate sentinel mode using the
broader robust-support envelope and spatially balanced exploration. Sentinel
performance is reported separately and cannot rescue or dilute the
anchor-conditioned endpoint.

### 6. Stop automatically

Patches are added in descending marginal expected new-cluster yield per unit
field cost. The algorithm stops when the marginal gain falls below a frozen
abstention threshold or when all remaining candidates are unsupported. Users do
not choose the number of sites, days, or budget in this scientific layer.

## Development evaluation

### Campanula diagnosis

Campanula remains development data only.

- primary spatial unit: 500-m occurrence/detection cluster;
- local endpoint: recovery within 1 km;
- sensitivity endpoints: 250 m and 500 m;
- retained-known exclusion: frozen before each experiment;
- reporting: recovery, selected search area or route length, equal-effort random
  success, and distance-band-specific performance.

### Leakage-resistant internal simulation

The development analogue of “unknown population” is leave-one-occurrence-cluster
out, not random row holdout.

For each fold:

1. remove the entire focal historical cluster;
2. remove its coordinates from all feature construction and anchor distances;
3. construct anchor-conditioned candidates from the retained clusters;
4. open the hidden cluster only for scoring;
5. retain failures and anchor-absent folds explicitly.

Spatially isolated folds and folds with no retained same-component anchor are
reported as a separate estimand rather than silently dropped.

### Comparators

At matched field effort, compare against:

- annular nearest-known search;
- full-island robust-support patches;
- local habitat-only ranking;
- proportional GRTS with the same candidate frame;
- same-area or same-route-length random search.

The new method must beat the annular nearest-known comparator, not only random
selection, before it is eligible for untouched confirmation.

## Required new field data

Each visited patch must record at least:

- patch and route identifier;
- date and phenological suitability;
- searched duration or traversed length;
- observer count;
- accessible area actually searched;
- detection / non-detection;
- reason for incomplete search;
- coordinates of every new detection cluster.

Access failure is not a biological non-detection.

## Promotion rule

A method derived here can be frozen only after:

1. the anchor-conditioned and sentinel modes are fully separated;
2. candidate generation is outcome-blind;
3. the known-point exclusion and stopping rule are fixed;
4. Campanula development diagnostics are closed;
5. an untouched taxon-region cohort is selected before outcomes are opened;
6. performance is evaluated against annular nearest-known and equal-effort
   spatial baselines with failures retained.

The current validated 10-km robust candidate-patch product remains unchanged
regardless of the outcome of this development line.
