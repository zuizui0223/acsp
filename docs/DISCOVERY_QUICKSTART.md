# ACSP Discovery — quick start

`acsp.discovery` is the experimental N4 layer for the question:

> **WHERE can we justify looking next?**

It is deliberately separate from the independently validated Japanese 2.5% / 10-km candidate-patch product.

## 1. Make templates

```bash
acsp-discovery template --out-dir my-discovery
```

This creates:

- `occurrences.csv` — provider-neutral occurrence evidence;
- `candidate_frame.csv` — a minimal frozen candidate frame example;
- `source_manifest.json` — source/provenance template;
- `README.txt` — the next commands.

## 2. Assess occurrence evidence first

```bash
acsp-discovery assess my-discovery/occurrences.csv
```

The command collapses coordinate records into bounded population evidence and returns a safe state:

- `READY_FOR_DECLARED_LOCAL_FRAME` — a separately justified local component has exact-enough population anchors;
- `READY_FOR_DETACHED_COMPONENT_FRAME` — a detached ecological component is justified;
- `READY_FOR_SENTINEL_FRAME` — only broad/context/uncertainty evidence supports search;
- `CONTEXT_REQUIRED` / `ABSTAIN_INSUFFICIENT_EXACT_EVIDENCE` — do not manufacture a local patch search.

Having many occurrence records **does not automatically turn on LOCAL mode**. Repeated records are first collapsed to bounded complete-link population clusters.

If you already have a source-backed ecological/range/component justification, declare it and record the reason:

```bash
acsp-discovery assess occurrences.csv \
  --regime local \
  --context-note "Species is restricted to the predeclared island component from source X"
```

`--regime local` is not a way to make weak data pass. The note is saved with the assessment so the decision remains auditable.

## 3. Rank one already frozen candidate frame

Comparator-only run:

```bash
acsp-discovery run \
  --occurrences occurrences.csv \
  --candidate-frame candidate_frame.csv \
  --regime local \
  --context-note "Predeclared source-backed local component" \
  --out-dir discovery-output
```

This returns separate full rankings, not one blended score:

- deterministic spatial balance;
- nearest-known when LOCAL and `nearest_anchor_km` is available.

For a structural/process model, first inspect the available families:

```bash
acsp-discovery families
```

Then supply the required **pre-graph raw columns** and real source provenance:

```bash
acsp-discovery run \
  --occurrences occurrences.csv \
  --candidate-frame enriched_candidate_frame.csv \
  --source-manifest source_manifest.json \
  --feature-family WETLAND_MOISTURE_STRUCTURE \
  --regime local \
  --context-note "Wetland component is predeclared from the cited vegetation/hydrology source" \
  --out-dir discovery-output
```

For `COASTAL_ISLAND_STRUCTURE`, also declare the ecological component that was fixed before outcome scoring:

```bash
--target-component-id WORLDCOVER_LAND_COMPONENT_1
```

The structural ranking is kept separate from nearest-known and spatial balance. ACSP does not fit a post-hoc distance/environment or distance/structure weight.

## Input contracts

### Occurrence evidence

Required columns:

- `occurrence_id`
- `latitude`
- `longitude`
- `event_year`
- `coordinate_uncertainty_m`
- `provider_id`

The simple CLI treats only records with **declared** uncertainty <= 1000 m as exact-anchor candidates, then clusters them with a bounded 0.5-km complete-link rule. These are transparent development defaults, not universal biological constants. The CLI intentionally does not offer a shortcut that treats missing uncertainty as exact evidence.

### Candidate frame

Required columns:

- `candidate_cell_id`
- `latitude`
- `longitude`
- `grid_row`
- `grid_col`

`nearest_anchor_km` is optional and is used only by the LOCAL nearest-known comparator.

ACSP Discovery does **not** invent a universal 2-km or 5-km frame. The frame must be declared/frozen upstream from a justified regional, local, detached, or sentinel component.

### LOCAL versus DETACHED components

When a provider/ecological graph already supplies `ecological_component_id`, the Python API can partition a frozen outer frame without a distance threshold:

```python
from acsp.discovery import partition_candidate_components

local_frame, detached_frame, audit = partition_candidate_components(
    candidate_frame,
    anchored_component_ids=["component-containing-known-populations"],
)
```

LOCAL contains components represented by historical populations. DETACHED contains other source-backed components in the same already frozen outer frame. The partition itself uses no held-out outcome, access layer or distance threshold.

### Structural sources

Run:

```bash
acsp-discovery families
```

for the exact provider/raw columns and source roles required by each family. Structural runs require a real source manifest with pinned release IDs and SHA-256 digests.

The current structural families are now also represented by a declarative recipe engine built from reusable primitives such as relative rank, local continuity, local similarity, edge signals, component membership, distance decay and conjunctive minimum. Existing frozen-family semantics must pass parity tests before the recipe engine can replace them in a frozen experiment.

## What the command does not do

It does not claim:

- occupancy probability;
- exact occupied locations;
- that nearest-known is the best method;
- that one structural family is universally correct;
- route, field-day, or budget optimality;
- discoveries/hour or a stopping rule.

Human access and movement restrictions belong downstream of ecological candidate generation. `distance_to_road`, trail/access, permission, route, travel, budget and field-outcome columns are rejected by the ecological ranking workflow. Field effort, detection/non-detection and complete visit logs are required before ACSP can estimate yield, days, budget or stopping.

## Python API

```python
from acsp.discovery import (
    DiscoveryContext,
    assess_occurrence_evidence,
    rank_discovery_frame,
)

assessment, population_anchors = assess_occurrence_evidence(
    occurrences,
    context=DiscoveryContext(local_component_justified=True),
)

rankings, audit = rank_discovery_frame(
    candidate_frame,
    assessment=assessment,
    source_manifest=source_manifest,
    feature_family="WETLAND_MOISTURE_STRUCTURE",
)
```

`rankings` is a dictionary of **separate** method orders. Do not select the favorable method after opening field outcomes and then call that method prospective.
