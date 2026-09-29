# E8 terminal closeout — taxonomic lift difference remains unidentifiable

## Target question

The validated Japanese ACSP cohort showed a descriptive recovery-lift contrast:

- animals: +0.11415;
- plants: +0.05702.

E8 asked whether that difference remains after biodiversity observation architecture is balanced before ecological outcomes are opened.

## Sequence

### Existing 96-pair cohort

A response-blind propensity/balance diagnostic failed before the pair-level recovery artifact was opened for adjustment.

### Fresh v1

192 metadata-only candidates produced 48 proposed taxa, but top-dataset concentration remained badly imbalanced (max |SMD| 0.553). No ACSP outcome was opened.

### Technical v2

Global taxon uniqueness was added prospectively; the same observation-balance problem remained (max |SMD| 0.550). No ACSP outcome was opened.

### Fresh v3

A new matching rule was developed using **only consumed, outcome-free v1 metadata** and then frozen. All taxa seen in the validated cohort and in v1/v2 metadata were excluded.

Authoritative run: 36509230701.

The v3 candidate metadata were complete for 192/192 fresh taxa and had zero overlap with all prior E8 candidate sets.

The frozen matching rule produced:

- 10/12 required regions;
- 20/24 required animal–plant matched pairs;
- 40/48 required taxa.

Balance diagnostics among those matched taxa:

- propensity overlap: 1.000;
- ESS: animal 18.84, plant 18.02;
- max pair distance: 2.566 (<3.0);
- log record-count |SMD|: 0.122;
- human-observation fraction: 0.170;
- machine-observation fraction: 0;
- preserved-specimen fraction: 0.229;
- top-dataset share: 0.041;
- recent 2021–2025 fraction: **0.546**.

The frozen balance ceiling was 0.15.

Therefore the exact denominator and global balance gates failed.

## Information firewall

At terminal closure:

- ACSP candidate generation: **not run**;
- held-out recovery: **not opened**;
- pre-frozen 24-pair confirmatory endpoint: **not activated**.

The E8 outcome therefore cannot be rescued by choosing another matching rule after seeing ecological performance.

## Decision

**Close E8 in the current programme.**

The approximately twofold animal-versus-plant lift in the validated ACSP cohort remains descriptive only. Three response-blind attempts show that taxonomic identity is strongly entangled with biodiversity observation architecture in the available Japanese sampling frames.

The most defensible conclusion is not “animals benefit more from ACSP”, but:

> **The available cohort does not identify a plant–animal difference in environmental-support recovery independently of observation architecture.**

No further E8 candidate hunting or matching-weight tuning is authorized within this programme.
