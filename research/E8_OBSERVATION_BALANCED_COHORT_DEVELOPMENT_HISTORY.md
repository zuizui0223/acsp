# E8 observation-balanced cohort development history

## Retrospective 96-pair diagnostic

The existing validated ACSP cohort could not separate animal–plant lift from observation architecture. The frozen IPW overlap gate failed before pair-level outcomes were opened in the diagnostic run.

## Fresh cohort v1

Response-blind metadata only.

- 192 candidate taxa;
- 48 proposed matched taxa;
- overlap fraction 1.0;
- ESS about 22–23 per group;
- max |SMD| 0.55265, driven by top-dataset share;
- no ACSP candidate generation or recovery opened.

Terminal: STOP.

## Fresh cohort v2

A technical successor frozen before the v1 result was opened added global scientific-name uniqueness. It did not change the matching rule.

- 192 candidate taxa;
- 48 unique proposed matched taxa;
- max |SMD| 0.55006;
- no ACSP candidate generation or recovery opened.

Terminal: STOP.

## Metadata-only matching development

Because v1/v2 contained no ACSP outcome, the consumed v1 metadata were used to define one new matching metric before v3.

Frozen weights:

- log current record count: 1.1;
- human observation: 1;
- machine observation: 1;
- preserved specimen: 1;
- recent 2021–2025: 1;
- top-dataset share: 6.

On consumed v1 metadata, this rule yields max |SMD| 0.13772 with maximum pair distance 2.96875.

This is development evidence only.

## Fresh v3

v3 excludes every taxon seen in:

- the validated 96-pair cohort;
- all 192 v1 candidate metadata rows;
- all 192 v2 candidate metadata rows;
- the repository's prior frozen development/confirmation cohorts.

The matching rule and gate are frozen before v3 metadata are opened.

If v3 passes, only then may a separate post-merge contract open ACSP candidate generation and held-out recovery.
