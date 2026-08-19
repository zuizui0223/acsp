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

The inverse diagnostic characterized:

- `oracle_compatible`: can occur in at least one minimum-size cover;
- `oracle_necessary`: removing the patch forces the optimum above the minimum size.

Retained result:

- minimum size: 11;
- oracle-compatible patches: 23;
- oracle-necessary patches: 0;
- four forced-out solves were unresolved within the development time limit and are not interpreted as necessity.

This proves that the 11-patch target is not a single fixed list to memorize.

## Negative experiments retained

### 1. Pointwise inverse classifier — rejected

A transparent logistic classifier used only outcome-blind patch features (support, area cost, occurrence gap, prototype coverage / rarity / breadth, and simple spatial structure) to predict minimum-cover compatibility. Leave-one-island-out predictions were used as the anti-memorization diagnostic.

Result:

- cross-fit first complete-recovery prefix: **82 patches**;
- full-fit first complete-recovery prefix: **86 patches**;
- both are much worse than the existing 32-patch outcome-blind policy.

Interpretation: patch membership is not a useful independent classification target. Even moderately informative pointwise scores do not reproduce a complementary set. The missing object is **state-dependent marginal value after other patches have already been selected**.

The rejected runner has been removed from the active repository path; these results remain here as provenance.

### 2. Component environmental-prototype knee — rejected

A second outcome-blind experiment kept the frozen spatial order inside each island but stopped independently at a knee between cumulative occurrence-prototype coverage and patch-cell cost.

Result:

- selected patches: **19**;
- field-cluster recovery: **11/19**;
- maximum nearest field-cluster distance: about **7.49 km**.

The sharp failure is Niijima: the pre-2026 data contain only one local occurrence prototype, so prototype coverage saturates almost immediately even though the 2026 survey contains four distinct field clusters. Therefore **known-prototype saturation is not a valid completeness/stopping signal**.

The rejected runner has been removed from the active repository path.

### 3. Support-envelope mass coverage — rejected

The next experiment replaced prototype counting with direct set coverage of the 5% outcome-blind support envelope. Support-cell mass was normalized so each island contributed equal total weight; one patch per island was seeded, then patches were added by maximum marginal newly covered support mass within 1 km.

Result:

- support envelope: 1,139 cells across all five islands;
- deterministic knee: **20 patches**;
- support mass represented at the knee: **0.9343**;
- field-cluster recovery at the knee: **13/19**;
- first complete-recovery prefix of this order: **38 patches**, worse than the retained 32-patch policy.

The six failures are structurally concentrated: Niijima cluster 4 and Oshima clusters 11–15. The selector did not omit whole islands; instead it delayed small, spatially separated support fragments because their area contributed little mass. Therefore **support area is not the correct unit of survey value**.

The rejected runner has been removed from the active repository path.

## Current hypothesis: represent distinct support fragments, not support area

The three negative experiments progressively narrow the correct object:

- pointwise patch probability fails because set complementarity is state dependent;
- occurrence-prototype saturation fails because sparse training records do not enumerate the realized within-island structure;
- support-envelope area fails because a small isolated support fragment can be biologically important while contributing little area.

The active experiment therefore treats the already outcome-blind 5% bounded support patches themselves as **structural units**.

1. build the 104 bounded 5% support patches before field outcomes are opened;
2. give every support fragment equal weight within its island and normalize every island to equal total weight;
3. let a selected patch represent same-island support fragments within the already declared 1-km operational radius;
4. seed one representative per disconnected island;
5. greedily add the patch with the largest **newly represented support-fragment weight**;
6. stop at the deterministic fragment-coverage versus selected-patch-fraction knee;
7. only then measure the 2026 field clusters.

This changes the estimand from “how much high-support area has been covered?” to “how many spatially distinct supported structures have been represented?”. No new field-informed threshold is introduced.

## Runnable development path

Only the current set-level hypothesis remains runnable in the Campanula CI path:

- `research/campanula_support_fragment_set_policy.py`
- `.github/workflows/campanula-inverse-development.yml` (workflow display name: `Campanula set-level development`)

Rejected pointwise inverse, prototype-knee, and support-envelope-mass runners are retained only as documented negative results, not competing executable branches.

## Promotion rule

A Campanula-derived rule is not promoted merely because it improves this development dataset. Promotion requires:

1. an explicit outcome-blind algorithm and preprocessing freeze;
2. no 2026 field coordinate or recovery label at inference time;
3. no hidden post-field threshold extension;
4. movement represented only by explicit available edges/modes;
5. untouched taxon-region evaluation after freeze, with failures retained;
6. no retuning on the final untouched cohort.

Until those conditions are met, Campanula results are development evidence only.
