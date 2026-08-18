# External travel-time matrix contract

ACSP separates biological screening, set-level geographic coverage, and field logistics. The travel-time matrix belongs only to the final logistics layer. It does not alter ecological evidence, the Practical Core, or the geometry-only coverage order.

## Input schema

Supply a long-form CSV to `acsp-recommend budget --travel-matrix`.

Required columns:

| column | meaning |
|---|---|
| `from_id` | origin endpoint ID |
| `to_id` | destination endpoint ID |
| `travel_minutes` | one-way operational travel time in minutes |

Optional columns:

| column | meaning |
|---|---|
| `distance_km` | routed distance for audit only |
| `mode` | free-text mode such as `road`, `trail`, or `ferry` |
| `available` | Boolean availability; false rows are removed before routing |

Candidate endpoint IDs must match the candidate CSV column selected by `--site-column`. The hub endpoint is selected by `--hub-id` and defaults to `__hub__`.

The matrix is directed by default. A missing directed pair means that movement is unavailable. `--undirected-travel-matrix` mirrors every supplied row and must be used only when both directions genuinely have equal travel cost. It is usually inappropriate for ferry timetables, one-way roads, or slope-dependent walking times.

Example:

```csv
from_id,to_id,travel_minutes,distance_km,mode,available
__hub__,site-01,35,12.4,road,true
site-01,__hub__,42,12.4,road,true
site-01,site-02,18,3.1,trail,true
site-02,__hub__,55,18.0,ferry,true
```

## Command

```bash
acsp-recommend budget \
  --input eligible_candidates.csv \
  --output selected_sites.csv \
  --summary-json budget_summary.json \
  --prefix-audit prefix_audit.csv \
  --hub-latitude 34.7500 \
  --hub-longitude 139.3600 \
  --hub-id __hub__ \
  --days 2 \
  --taxon-profile plant \
  --coverage-radius-km 1 \
  --max-sites 40 \
  --travel-matrix travel_times.csv
```

## Decision sequence

1. The input candidate table is assumed to have already passed the upstream ecological/domain screen.
2. ACSP constructs a deterministic maximum-coverage order. When multiple survey areas are present, candidate coverage is calculated within area boundaries and never across them.
3. Every prefix of that fixed order is evaluated against the supplied pairwise costs, field-day length, per-site effort, and daily return to the declared hub.
4. ACSP returns the longest feasible prefix. The travel matrix never changes the upstream membership order or biological score.

The daily route is a nearest-feasible heuristic inside each prefix. It can use explicit road, trail, or ferry costs encoded in the matrix. There is no hidden straight-line fallback: missing required legs make the affected prefix infeasible.

## What the contract does not validate

The matrix is accepted as user-supplied operational evidence. ACSP does not verify how it was produced and does not infer:

- road or trail topology;
- ferry departure windows, cancellations, or overnight transfers;
- traffic, closures, tides, weather, or seasonal access;
- landowner permission, permits, safety, or physical accessibility;
- detection probability, non-detection, discoveries per day, or adaptive survey yield.

Time-window scheduling, multiple overnight hubs, vehicle capacity, and prospective field-yield learning remain separate future layers. Attempted-site records with effort and non-detections are still required before any discovery-efficiency claim.
