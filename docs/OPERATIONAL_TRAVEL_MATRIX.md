# Explicit movement graph and automatic survey-effort contract

ACSP separates ecological screening, local set selection, and field logistics. The operational input is a **physical movement graph**, not a user-selected field-day or site-count budget.

The user declares only constraints ACSP cannot infer safely: where the field trip starts, which directed movement edges exist, and which movement modes are actually available. ACSP then determines which candidate sites are reachable, constructs the survey coverage order on that reachable set, and estimates the recommended number of sites, total hours, and field days.

## Movement-edge schema

`acsp-recommend auto-effort --movement-edges movement_edges.csv` accepts a sparse movement graph. `--travel-matrix` remains only as an input-name alias for existing data files; the algorithm treats the rows as graph edges, not as a requirement for a complete pairwise matrix.

Required columns:

| column | meaning |
|---|---|
| `from_id` | origin graph node |
| `to_id` | destination graph node |
| `travel_minutes` | directed edge travel time |
| `mode` | explicit mode such as `walk`, `road`, `trail`, or `ferry` |

Optional `distance_km` is audit metadata. Optional `available=false` removes an edge.

Candidate `site_id` values must appear as graph nodes or be connected through explicit edges. Intermediate road/trail/ferry nodes are allowed and need not be survey candidates.

## Human movement allow-list

Repeat `--allowed-mode` for every mode that can actually be used:

```bash
--allowed-mode walk \
--allowed-mode road \
--allowed-mode trail \
--allowed-mode ferry
```

Edges with any other mode are removed before routing. Thus a `flight` edge does not exist for an analysis that allows only walking/road/trail/ferry. Missing edges remain missing. ACSP never creates a Euclidean shortcut across sea, cliffs, disconnected roads, or other gaps.

## Reachability comes before coverage

```text
regional ecological/domain screen
        ↓
local candidate universe
        ↓
explicit allowed movement graph
        ↓
Dijkstra hub→node and node→hub
        ↓
keep only directed round-trip reachable candidates
        ↓
maximum-coverage order on the reachable set
        ↓
coverage-versus-effort frontier
        ↓
automatic diminishing-return knee
        ↓
recommended sites + hours + days
```

An unreachable high-coverage candidate must not block later reachable candidates. Reachability therefore filters the candidate universe **before** set-level coverage ordering.

The current operational estimator uses explicit shortest hub-to-site and site-to-hub paths. Each selected site is conservatively costed as a hub round trip plus taxon-protocol search effort. This is intentionally conservative; no direct site-to-site shortcut is invented.

## Command

```bash
acsp-recommend auto-effort \
  --input eligible_candidates.csv \
  --output selected_sites.csv \
  --summary-json auto_effort_summary.json \
  --frontier-audit auto_effort_frontier.csv \
  --reachability-audit auto_effort_reachability.csv \
  --movement-edges movement_edges.csv \
  --hub-id __hub__ \
  --taxon-profile plant \
  --allowed-mode walk \
  --allowed-mode road \
  --allowed-mode trail \
  --allowed-mode ferry
```

There is intentionally no `--days`, `--max-sites`, or user survey-budget argument. The internal coverage scale and taxon search protocol are method assumptions, not requested effort targets.

Outputs include every candidate's directed round-trip reachability, the coverage-effort frontier for reachable candidates, the automatically recommended site count, total operational hours, estimated field days, and selected site set.

## Removed legacy paths

The old explicit-day `budget` CLI, straight-line trip proxy, pairwise-prefix budget scheduler, and their operational-development workflows have been removed from the runnable codebase. Their historical protocols and result ledgers may remain as provenance for negative or superseded experiments, but they are not supported planning methods.

## Scientific boundary

Movement is an operational constraint, never ecological evidence. ACSP does not infer missing roads, ferry links, schedules, permissions, weather, safety, occupancy, detection probability, or discoveries per day.

*Campanula microdonta* 2026 outcomes are development labels used to reverse-engineer candidate compression and stopping rules. They are not validation evidence. Any Campanula-derived rule must be frozen before untouched-taxon generalization testing.
