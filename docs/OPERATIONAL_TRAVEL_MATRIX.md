# External travel-time matrix and automatic effort contract

ACSP separates biological screening, set-level geographic coverage, and field logistics. The travel-time matrix belongs only to the final logistics layer. It does not alter ecological evidence, the Practical Core, or the geometry-only coverage order.

The default operational question is **not** "how many sites fit in N user-specified days?". Instead, the user supplies the physical movement network that ACSP cannot infer safely, and ACSP estimates the recommended survey size, total effort, and field days from the reachable coverage-effort frontier.

## Input schema

Supply a long-form CSV to `acsp-recommend auto-effort --travel-matrix`.

Required columns:

| column | meaning |
|---|---|
| `from_id` | origin endpoint ID |
| `to_id` | destination endpoint ID |
| `travel_minutes` | one-way operational travel time in minutes |
| `mode` | explicit movement mode such as `walk`, `road`, `trail`, or `ferry` |

Optional columns:

| column | meaning |
|---|---|
| `distance_km` | routed distance for audit only |
| `available` | Boolean availability; false rows are removed before routing |

Candidate endpoint IDs must match the candidate CSV column selected by `--site-column`. The hub endpoint is selected by `--hub-id` and defaults to `__hub__`.

The matrix is directed by default. A missing directed pair means that movement is unavailable. `--undirected-travel-matrix` mirrors every supplied row and must be used only when both directions genuinely have equal travel cost.

## Human movement allow-list

`auto-effort` requires at least one explicit `--allowed-mode`. Repeat the option for every movement mode that is actually available:

```bash
--allowed-mode walk \
--allowed-mode road \
--allowed-mode trail \
--allowed-mode ferry
```

This is an allow-list, not a preference ranking. Every matrix edge whose mode is not in the list is removed. A `flight` edge therefore cannot be used unless the caller explicitly allows `flight`. Missing edges also remain unreachable. ACSP never fabricates a straight-line edge to bridge a gap in the movement network.

Example matrix:

```csv
from_id,to_id,travel_minutes,distance_km,mode,available
__hub__,site-01,35,12.4,road,true
site-01,__hub__,42,12.4,road,true
site-01,site-02,18,3.1,trail,true
site-02,__hub__,55,18.0,ferry,true
```

## Default command: infer the effort

```bash
acsp-recommend auto-effort \
  --input eligible_candidates.csv \
  --output selected_sites.csv \
  --summary-json auto_effort_summary.json \
  --frontier-audit auto_effort_frontier.csv \
  --hub-id __hub__ \
  --taxon-profile plant \
  --coverage-radius-km 1 \
  --max-sites 40 \
  --travel-matrix travel_times.csv \
  --allowed-mode walk \
  --allowed-mode road \
  --allowed-mode trail \
  --allowed-mode ferry
```

There is intentionally no `--days` argument. ACSP reports the recommended site count, total operational hours, and estimated field days.

## Decision sequence

1. The input candidate table has already passed the upstream ecological/domain screen.
2. ACSP constructs a deterministic maximum-coverage order within survey-area boundaries.
3. The travel matrix is normalized and then restricted to explicitly allowed movement modes.
4. Every ordered prefix is scheduled on that reachable network. Missing/disallowed legs make the affected prefix unreachable.
5. ACSP builds the cumulative candidate-coverage versus total-effort frontier.
6. The automatically recommended survey size is the deterministic diminishing-return knee of that frontier.
7. The selected prefix, total hours, estimated field days, full frontier, and unreachable prefixes are exported for audit.

The movement layer never reorders ecological evidence and never creates biological suitability from accessibility.

## Legacy what-if command

`acsp-recommend budget --days N` remains available for a user who explicitly wants to ask a counterfactual question such as "what fits in two days?". It is retained for backward compatibility and scenario exploration, not as the default ACSP decision object.

## What the contract does not validate

The matrix is accepted as operational evidence. ACSP does not verify how it was produced and does not infer:

- roads, trails, ferry links, or other missing topology;
- departure windows, cancellations, overnight transfers, traffic, closures, tides, or weather;
- landowner permission, permits, safety, or individual physical capability;
- occupancy probability, detection probability, discoveries per day, or adaptive survey yield.

Campanula 2026 outcomes are used only in the separate development sandbox to reverse-engineer the architecture. Generalization requires untouched taxa after the development rule is frozen.
