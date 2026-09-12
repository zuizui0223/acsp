# ACSP Discovery — quick start

`acsp.discovery` is the experimental N4 layer for the question:

> **WHERE can we justify looking next?**

It is deliberately separate from the independently validated Japanese 2.5% / 10-km candidate-patch product.

## Fast path: species name to auditable search lanes

```bash
# 1. Public occurrence evidence. Coordinate uncertainty is preserved, not pre-filtered.
acsp-discovery fetch-gbif "Species name" --country JP --out occurrences.csv

# 2. Collapse records to bounded population evidence and diagnose what is justified.
acsp-discovery assess occurrences.csv --out-dir assessment

# 3A. LOCAL only when an external study contract/source already justifies its outer radius.
acsp-discovery build-frame local \
  --anchors assessment/population_anchors.csv \
  --outer-radius-km 5 \
  --out local_frame.csv

# 3B. Or declare a BROAD geographic frame when LOCAL is insufficient/unsupported.
acsp-discovery build-frame broad \
  --bounds WEST SOUTH EAST NORTH \
  --anchors assessment/population_anchors.csv \
  --out broad_frame.csv

# 4. For terrestrial broad frames, attach ESA WorldCover land components and
#    automatically split components represented by historical populations from others.
acsp-discovery prepare-components \
  --candidate-frame broad_frame.csv \
  --anchors assessment/population_anchors.csv \
  --out-dir components
```

`components/` contains:

- `candidate_components_all_land.csv`;
- `candidate_components_anchored.csv` — physical land components represented by historical populations;
- `candidate_components_other.csv` — other physical land components in the same declared broad frame;
- `worldcover_component_snapshot.tif`;
- `component_audit.json`;
- `source_manifest.json` with pinned WorldCover release and SHA-256.

WorldCover land components are **physical source-backed components, not proof of suitable habitat**. They are a reusable way to stop LOCAL distance from silently defining the entire candidate universe. A biological DETACHED lane still needs ecological justification or a prospective test.

## Template path

```bash
acsp-discovery template --out-dir my-discovery
```

This creates example occurrence/candidate tables and a source-manifest template.

## Evidence states

`acsp-discovery assess` returns a safe state:

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

## Rank a frozen candidate frame

Comparator-only LOCAL run:

```bash
acsp-discovery run \
  --occurrences occurrences.csv \
  --candidate-frame local_frame.csv \
  --regime local \
  --context-note "Predeclared source-backed local component" \
  --out-dir discovery-output
```

This returns **separate** orders, not one blended score. Depending on the declared regime/input, these can include deterministic spatial balance, nearest-known and a structural/process ranking.

Inspect structural families first:

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

For `COASTAL_ISLAND_STRUCTURE`, also declare the component fixed before outcome scoring with `--target-component-id`.

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

ACSP Discovery does **not** invent a universal 2-km or 5-km frame. LOCAL radius or BROAD bounds must be declared/frozen upstream.

### LOCAL versus DETACHED components

When a provider already supplies `ecological_component_id`, the Python API can partition a frozen outer frame without a distance threshold:

```python
from acsp.discovery import partition_candidate_components

anchored_frame, other_frame, audit = partition_candidate_components(
    candidate_frame,
    anchored_component_ids=["component-containing-known-populations"],
)
```

The high-level `prepare-components` command performs this operation for ESA WorldCover without requiring the user to type component IDs.

### Structural sources

Run `acsp-discovery families` for exact provider/raw columns and source roles. Structural runs require a real source manifest with pinned release IDs and SHA-256 digests.

The current structural families are also represented by a declarative recipe engine built from reusable primitives such as relative rank, local continuity, local similarity, edge signals, component membership, distance decay and conjunctive minimum. Existing frozen-family semantics must pass parity tests before recipes replace them in a frozen experiment.

## What ACSP Discovery does not do

It does not claim:

- occupancy probability or exact occupied locations;
- that nearest-known or one structural family is universally best;
- that every unanchored physical component is biologically suitable;
- route, field-day or budget optimality;
- discoveries/hour or a stopping rule.

Human access and movement restrictions belong downstream of ecological candidate generation. Road/trail/access/permission/travel/budget/field-outcome columns are rejected by the ecological ranking workflow. Complete effort plus detection/non-detection logs are required before ACSP can estimate yield, days, budget or stopping.

## Python API

```python
from acsp.discovery import (
    DiscoveryContext,
    assess_occurrence_evidence,
    prepare_worldcover_component_partition,
    rank_discovery_frame,
)

assessment, population_anchors = assess_occurrence_evidence(
    occurrences,
    context=DiscoveryContext(local_component_justified=True),
)

all_land, anchored_components, other_components, component_audit = \
    prepare_worldcover_component_partition(
        broad_candidate_frame,
        population_anchors,
        snapshot_path="worldcover_snapshot.tif",
    )

rankings, audit = rank_discovery_frame(
    candidate_frame,
    assessment=assessment,
    source_manifest=source_manifest,
    feature_family="WETLAND_MOISTURE_STRUCTURE",
)
```

`rankings` is a dictionary of **separate** method orders. Do not select a favorable method after opening field outcomes and then call that method prospective.
