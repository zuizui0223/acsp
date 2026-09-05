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

The command collapses coordinate records into bounded population evidence and returns one of four safe states:

- `READY_FOR_DECLARED_LOCAL_FRAME` — a separately justified local component has exact-enough population anchors;
- `READY_FOR_DETACHED_COMPONENT_FRAME` — a detached ecological component is justified;
- `READY_FOR_SENTINEL_FRAME` — only broad/context/uncertainty evidence supports search;
- `CONTEXT_REQUIRED` / `ABSTAIN_INSUFFICIENT_EXACT_EVIDENCE` — do not manufacture a local patch search.

Having many occurrence records **does not automatically turn on LOCAL mode**. Repeated records are first collapsed to bounded complete-link population clusters.

A source-backed local context can be declared explicitly:

```bash
acsp-discovery assess occurrences.csv --regime local
```

`--regime local` means that an external ecological/range/component justification already exists. It is not a way to make weak data pass.

## 3. Rank one already frozen candidate frame

Comparator-only run:

```bash
acsp-discovery run \
  --occurrences occurrences.csv \
  --candidate-frame candidate_frame.csv \
  --regime local \
  --out-dir discovery-output
```

This returns separate full rankings, not one blended score:

- deterministic spatial balance;
- nearest-known when LOCAL and `nearest_anchor_km` is available.

For a structural/process model, first inspect the available families:

```bash
acsp-discovery families
```

Then supply the required raw columns and real source provenance:

```bash
acsp-discovery run \
  --occurrences occurrences.csv \
  --candidate-frame enriched_candidate_frame.csv \
  --source-manifest source_manifest.json \
  --feature-family WETLAND_MOISTURE_STRUCTURE \
  --regime local \
  --out-dir discovery-output
```

The structural ranking is kept separate from nearest-known and spatial balance. ACSP does not fit a post-hoc distance/environment weight.

## Input contracts

### Occurrence evidence

Required columns:

- `occurrence_id`
- `latitude`
- `longitude`
- `event_year`
- `coordinate_uncertainty_m`
- `provider_id`

The development default treats only records with declared uncertainty <= 1000 m as exact-anchor candidates, then clusters them with a bounded 0.5-km complete-link rule. These are transparent development defaults, not universal biological constants.

### Candidate frame

Required columns:

- `candidate_cell_id`
- `latitude`
- `longitude`
- `grid_row`
- `grid_col`

`nearest_anchor_km` is optional and is used only by the LOCAL nearest-known comparator.

ACSP Discovery does **not** invent a universal 2-km or 5-km frame. The frame must be declared/frozen upstream from a justified regional, local, detached, or sentinel component.

### Structural sources

Run:

```bash
acsp-discovery families
```

for the exact raw columns and source roles required by each family. Structural runs require a real source manifest with pinned release IDs and SHA-256 digests.

## What the command does not do

It does not claim:

- occupancy probability;
- exact occupied locations;
- that nearest-known is the best method;
- that one structural family is universally correct;
- route, field-day, or budget optimality;
- discoveries/hour or a stopping rule.

Human access and movement restrictions belong downstream of ecological candidate generation. Field effort, detection/non-detection and complete visit logs are required before ACSP can estimate yield, days, budget or stopping.

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
