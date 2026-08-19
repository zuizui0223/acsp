# Campanula inverse survey-algorithm development contract

## Status

`Campanula microdonta` is **development data, not an independent validation cohort**. The 2026 field outcomes have already been inspected and have already influenced ACSP development. They are used only to diagnose architecture and compression before a rule is frozen for untouched-taxon evaluation.

The frozen cross-taxon Practical Core / retrospective evidence remains separate and unchanged.

## Active problem

The current problem is no longer basic candidate generation.

Using pre-2026 GBIF occurrences plus frozen public GSI DEM and pinned ESA WorldCover NDVI, the full-island candidate universe can recover all **19/19** Campanula field clusters within 1 km. The old 97/102-candidate pools that reached only 13/19 are retained only as historical evidence of the earlier candidate-generation bottleneck.

The active gap is **set compression / ranking**:

- full-island patch universe at the working 5% support envelope: 104 patches;
- best existing outcome-blind complete-recovery spatial policy: 32 patches;
- field-outcome minimum set-cover diagnostic: 11 patches in the current 5% patch universe.

The goal is not to reproduce the 11 field-informed patches directly. It is to identify a simple, outcome-blind set-level rule that closes as much of the 32-to-11 gap as possible and can later be frozen for new taxa.

## Operational planning is reachability-first

The user does **not** choose target days, target site count, or a survey budget. The user supplies only physical constraints ACSP cannot infer safely: hub, explicit movement edges, and allowed movement modes.

The active operational sequence is:

```text
regional ecological/domain screen
        ↓
local candidate / patch universe
        ↓
explicit allowed movement graph
        ↓
directed hub round-trip reachability
        ↓
set-level coverage on reachable candidates
        ↓
coverage-versus-effort frontier
        ↓
automatic diminishing-return knee
        ↓
recommended sites + hours + days
```

Missing movement edges remain missing. ACSP never inserts straight-line sea, cliff, road, trail, ferry, or flight links. The old explicit-day budget CLI and straight-line trip proxy have been removed from the runnable main line.

## Development guardrails

Everything used to construct an inference-time candidate, patch, feature, ordering, or stopping point must be frozen before the 2026 field clusters are opened.

Disallowed inference-time inputs include:

- 2026 field latitude / longitude;
- distance to a 2026 field detection;
- field cluster identifiers;
- whether a candidate or patch recovered a field cluster;
- a stopping point chosen by extending the prefix until all field clusters are recovered.

Allowed use of field outcomes is post-freeze development scoring and diagnosis of why an outcome-blind rule failed.

## Retained development evidence

### Full-island generation solved the 13/19 ceiling

The full-island outcome-blind generator rebuilt from the frozen Campanula development cache and pinned public layers reaches all 19 field clusters. Candidate generation is therefore not the current limiting layer.

### Existing 32-patch spatial policy remains the active outcome-blind reference

The best retained spatial patch policy reaches 19/19 with 32 patches (284 support cells). A matched-random patch set has a very low complete-recovery probability in the frozen development artifact. This policy is not yet a satisfactory final compression rule, but it remains the current outcome-blind benchmark until a simpler rule beats it without reading field labels.

### Minimum-cover family: diagnostic only

A field-outcome set-cover calculation on the 104-patch universe gives a minimum of **11 patches**. Because multiple minimum covers exist, one arbitrary MILP solution must not be treated as the unique target.

The inverse diagnostic therefore classifies patches as:

- `oracle_compatible`: can occur in at least one minimum-size cover;
- `oracle_necessary`: removing the patch forces the optimum above the minimum size.

Current result:

- minimum size: 11;
- oracle-compatible patches: 23;
- oracle-necessary patches: 0;
- four forced-out solves were unresolved within the development time limit and are not interpreted as necessity.

This proves that the 11-patch target is not a single fixed list to memorize.

## Negative experiments retained

### 1. Pointwise inverse classifier — rejected

A transparent logistic classifier was trained only on outcome-blind patch features (support, area cost, occurrence gap, prototype coverage / rarity / breadth, and simple spatial structure) to predict minimum-cover compatibility. Leave-one-island-out predictions were used as the anti-memorization diagnostic.

Result:

- cross-fit first complete-recovery prefix: **82 patches**;
- full-fit first complete-recovery prefix: **86 patches**;
- both are much worse than the existing 32-patch outcome-blind policy.

Interpretation: patch membership is not a useful independent classification target. Even moderately informative pointwise scores do not reproduce a complementary set. The missing object is **state-dependent marginal value after other patches have already been selected**.

This classifier is not a promotion candidate.

### 2. Component environmental-prototype knee — rejected

A second outcome-blind experiment kept the frozen spatial order inside each island but stopped independently at a knee between cumulative occurrence-prototype coverage and patch-cell cost.

Result:

- selected patches: **19**;
- field-cluster recovery: **11/19**;
- maximum nearest field-cluster distance: about **7.49 km**.

The sharp failure is Niijima: the pre-2026 data contain only one local occurrence prototype, so prototype coverage saturates almost immediately even though the 2026 survey contains four distinct field clusters. Therefore **known-prototype saturation is not a valid completeness/stopping signal**.

This stopping rule is rejected.

## Current hypothesis: cover the support envelope, not the known prototypes

The two negative experiments imply a simpler next object.

The occurrence model defines an outcome-blind **support envelope** over the island. The survey selector should value a patch by how much *new spatially distinct support-envelope structure* it covers after accounting for patches already selected. This differs from:

- a pointwise patch score;
- counting how many known occurrence prototypes are represented;
- extending a field-informed prefix until all detections are recovered.

The next experiment therefore uses a deterministic set function over the frozen support envelope:

1. build the 5% outcome-blind support-cell universe and bounded patches;
2. within each disconnected component, let each patch cover nearby support-envelope cells at the already declared patch-neighborhood scale;
3. greedily add the patch with the largest **new support-envelope coverage** (ties prefer smaller patches / stable IDs);
4. stop at a deterministic coverage-versus-patch-area knee fixed before field outcomes are opened;
5. only then measure 2026 field-cluster recovery.

This can continue exploring a component even when only one training occurrence prototype exists, because geographically separated support regions remain distinct survey value.

## Promotion rule

A Campanula-derived rule is not promoted merely because it improves this development dataset. Promotion requires:

1. an explicit outcome-blind algorithm and preprocessing freeze;
2. no 2026 field coordinate or recovery label at inference time;
3. no hidden post-field threshold extension;
4. movement represented only by explicit available edges/modes;
5. untouched taxon-region evaluation after freeze, with failures retained;
6. no retuning on the final untouched cohort.

Until those conditions are met, Campanula results are development evidence only.
