# E8 observation-architecture diagnostic — terminal result

## Question

The validated Japanese ACSP confirmation produced mean held-out lift of:

- animals: **+0.11415**
- plants: **+0.05702**

Does that approximately twofold contrast remain interpretable after accounting for differences in biodiversity observation architecture?

This was a retrospective mechanism diagnostic, not part of the original untouched confirmation.

## Information order

The diagnostic deliberately separated two stages.

First, for the same 96 frozen taxa, it queried **count-only GBIF metadata** within the frozen taxon-region rectangles:

- current coordinate-record count;
- HUMAN_OBSERVATION fraction;
- MACHINE_OBSERVATION fraction;
- PRESERVED_SPECIMEN fraction;
- 2021–2025 fraction;
- largest-dataset share.

No row-level occurrence coordinates were requested.

Second, a frozen propensity-overlap gate determined whether the already-open historical pair-level recovery artifact could be used for an observation-balanced decomposition.

If the gate failed, the outcome artifact was not downloaded.

## Result

Metadata were complete for **96/96 taxa**.

However, animal and plant observation architectures did not overlap sufficiently:

- propensity range: **0.0378–0.9869**;
- fraction within the frozen 0.10–0.90 overlap region: **0.5833**;
- required: **≥0.75**.

Effective sample size after stabilized weighting was adequate:

- animals: **29.79**
- plants: **30.27**
- required: **≥24** each.

But covariate balance was not.

Post-weight absolute standardized mean differences:

- log current record count: **0.099**
- human-observation fraction: **0.181**
- machine-observation fraction: **0.166**
- preserved-specimen fraction: **0.354**
- recent 2021–2025 fraction: **0.450**
- top-dataset share: **0.608**

Frozen maximum allowed absolute SMD: **0.25**.

Therefore both the overlap-fraction gate and the all-covariate balance gate failed.

## Terminal decision

**observation_architecture_not_balanceable_in_current_cohort**

The workflow consequently skipped:

- downloading the pair-level recovery result artifact;
- computing an IPW-adjusted animal-minus-plant lift.

This is the intended fail-closed behavior.

## Ecological consequence

The raw validated difference — animals +0.114 versus plants +0.057 — remains a descriptive subgroup contrast only.

This cohort does **not** identify whether that difference reflects:

- biological differences in environmental support;
- taxonomic differences in detectability/distribution;
- citizen-science versus specimen architecture;
- temporal coverage;
- dataset concentration;
- or combinations of these.

The largest residual imbalances were dataset concentration, recent-record fraction, and preserved-specimen fraction.

## Next test

Do not repair this cohort post hoc.

The next admissible E8 design is a **fresh observation-balanced paired cohort**:

1. define taxon-region candidates using identity/count metadata only;
2. calculate the same six observation-architecture descriptors before ACSP outcomes;
3. pair or subclass animals and plants within region and observation architecture;
4. freeze the paired denominator;
5. build ACSP support from historical/training records;
6. open held-out recovery only after the observation-balance gate passes.

That design can test whether an animal–plant ecological contrast survives when observation architecture is balanced by construction.

## Provenance

Workflow run: 36287169007  
Artifact: 10920832880  
Digest: sha256:073fcb4b603d927c6da186c5bed40b585490a735215e720aeb6f0961a2c66257

No pair-level recovery outcome was opened by this diagnostic run.
