# ACSP scale-separated survey architecture

Status: **development architecture**, not a new superiority claim.

This document records the structure that survives the full development history through the failed cross-island q10 confirmation and the subsequent coverage-equivalent budget experiment. The machine-readable evidence ledger is `research/acsp_algorithm_component_ledger.json`.

## Current algorithmic object

ACSP is no longer being developed as a universal cell-wise suitability model or a universal weighted cell-ranking formula. The current target is a **scale-separated survey decision procedure**:

```text
training occurrences O
        |
        v
[1] domain / information adequacy
        |
        v
[2] regional occurrence-conditioned ecological screen
    (frozen Practical Core role; no new fine-scale claim)
        |
        v
[3] full local land candidate universe
        |
        v
[4] geometry-only set-level maximum coverage
        |
        v
[5] operational budget translation
    (days / route proxy / site effort)
        |
        v
field survey site set
```

The important separation is now **scale**, not another environmental weight:

- ecological occurrence evidence is retained at the regional decision scale where the parsimonious Practical Core survived simplification;
- within a selected local survey domain, repeated attempts to use NDVI/microenvironment as a transferable fine-scale filter failed;
- local site selection therefore falls back to the strongest surviving structure: non-overlapping set-level geographic coverage;
- route, patch and time are downstream operational representations, not biological truth criteria.

Optional SDM/SSDM remains a separate evidence source in the production app and is not required for this non-model decision path.

## 1. Domain and information adequacy

A terrestrial survey policy must not be forced onto an unsupported domain. The research-layer domain gate uses training-surface support before held-out outcomes. Taxonomy is only a conservative prior.

The failed cross-island confirmation also exposed a second distinction:

- **deployment information adequacy**: enough training information exists to generate a survey plan;
- **retrospective benchmark evaluability**: enough independent spatial blocks exist to estimate held-out recovery reliably.

These must be reported separately. A species can be deployable but difficult to benchmark with five independent folds.

## 2. Regional ecological screen

The frozen Practical Core remains the ecological survey-decision baseline:

- candidate pool built from training occurrences only;
- known/occurrence-supported candidates removed before ranking;
- Top-5 by `component_local_habitat_score`;
- same rule for plants and animals;
- score interpreted as **occurrence-conditioned local environmental support**, not occupancy or calibrated suitability probability.

Its scientific fingerprint remains `3dafe65b6bef09b1878d688730d5feb64a8de58843b06ff9fb14a876512d4905` and its separate 192-pair protocol remains isolated from this development line.

This regional ecological role must not be confused with the rejected fine-scale NDVI experiments below.

## 3. Fine-scale ecological support: development conclusion

The Campanula case was useful as a stress-test system but did not produce a transferable microenvironmental ranking rule.

The development sequence was:

1. old candidate pools imposed an upstream ceiling (13/19 Campanula field clusters within 1 km);
2. full-island generation removed that ceiling;
3. terrain was real but insufficiently selective;
4. static WorldCover composition failed;
5. NDVI state compressed the Campanula field case;
6. the Campanula 0.90 NDVI + 0.10 microclimate rule failed the predeclared 16-taxon Izu transfer;
7. independent environmental Top-cell ranking failed under low-budget sweeps;
8. strong set-level maximum coverage dominated weak geometry controls;
9. a q=0.10 NDVI eligibility mask retained a narrow K=5 Izu development signal (+0.030 versus q=1 geometry-only);
10. prototype-LOO q selection failed;
11. fully nested within-taxon q selection failed;
12. MST multimodal support failed;
13. k=2/3 local prototype agreement failed;
14. point/100 m/250 m NDVI scale adaptation failed;
15. cross-taxon jackknife consistently selected q=0.10 at K=5, motivating one frozen external test;
16. that frozen K5/q10 method **failed** on 24 new taxa / 12 new island domains: eligible n=15, mean lift +0.0209, bootstrap 95% CI crossing zero, exact p=0.156, and eligibility rate 0.625;
17. a new development cohort then replaced fixed K with equal land-grid design-footprint targets; q=0.10 still failed, with normalized-AUC lift +0.00275, bootstrap CI crossing zero and p=0.356.

Therefore:

> **NDVI q10 is rejected as a transferable fine-scale operational modifier in the current ACSP line.**

This is stronger than saying that the threshold was wrong. Fixed K, q adaptation, multimodality, prototype agreement, spatial aggregation and equal-coverage budget representations were all tested without producing stable transfer.

A future ecological micro-support family would require a genuinely new biological representation and a new development cohort. It must not be created by retuning q, NDVI features or thresholds on any inspected cohort above.

## 4. Set-level local optimization

This is the strongest surviving fine-scale component.

A field survey is a **set decision**, not independent high-scoring cells. The exact sparse selector greedily maximizes newly covered land-grid cells at every step and uses a deterministic tie break. This absorbs the useful part of earlier geographic complementarity without retaining a fixed additive geography weight.

Current local transferable core:

```text
full local land candidate grid
        |
        v
exact sparse maximum-new-coverage order
        |
        v
operational budget translator
```

The geometry layer is deliberately ecology-free at this scale because the tested ecological micro-support modifiers did not transfer reliably.

## 5. Operational field budget and output

Candidate count is not itself a field budget. The 793-point / 1-km Campanula design showed that large buffered candidate sets can nearly saturate an island and make random selection appear strong.

The operational layer should translate the fixed geometry sequence into quantities the field team actually controls:

- survey days;
- site-search time;
- access buffer time;
- route-distance proxy;
- number of survey stops;
- ultimately real road/trail/ferry constraints when those data are available.

The active experiment is outcome-free: it keeps the geometry coverage order fixed and uses the existing production `estimate_default_short_trip` plus the production vascular-plant reconnaissance defaults to find the largest prefix fitting 1–5 days. Route estimates **do not reorder** the biological/coverage sequence. Five deterministic hub proxies test sensitivity to the arbitrary benchmark hub location.

Patch persistence remains an operational presentation option. It is not a required biological gate.

## Rejected / demoted components

Do not return these to the main line without a new predeclared rationale and genuinely new evidence:

- universal fixed evidence-weight sums as the scientific core;
- independent environmental Top-cell ranking as a transferable local selector;
- Campanula's fixed 90% NDVI + 10% microclimate correction;
- q=0.10 NDVI eligibility as a transferable fine-scale operational modifier;
- within-taxon q adaptation;
- prototype-LOO environmental reconstruction as policy selection;
- equal-opportunity MST multimodal support;
- k=2/3 nearest-prototype agreement;
- point-only / 100 m-only / 250 m-only NDVI scale adaptation;
- static WorldCover composition;
- the current NDVI transition/gradient representation;
- mandatory persistent-patch filtering;
- NDVI-driven between-island allocation;
- training-occurrence-count island allocation;
- fixed geographic complementarity bonuses applied to every taxon.

Negative results are retained as constraints on the method.

## Retained components

- full-domain candidate generation;
- spatial occurrence thinning as duplicate-control, not a biological constant;
- occurrence-conditioned local environmental evidence at its validated/frozen regional role;
- training-only domain/information adequacy;
- strong same-budget controls;
- exact sparse set-level maximum geographic coverage at fine scale;
- survey budget as an external operational input;
- leakage-safe nested and untouched validation;
- route/patch/time as downstream operational outputs;
- explicit fallback instead of forcing unsupported ecological detail.

## Development rule from this point

1. Finish the outcome-free geometry-to-1–5-day operational robustness experiment.
2. If operational translation is stable, freeze the **scale-separated procedure**: regional Practical Core role + local geometry coverage + field-budget translation.
3. Add real access/road/trail/ferry information only as explicit operational constraints, never as inferred biological suitability.
4. Claims about discoveries per day, detection probability or realized route efficiency require prospective attempted-site data including non-detections and effort.
5. The frozen 192-pair Practical Core cohort remains separate and untouched.

The next scientific gain should come from a better definition of the survey decision problem or prospective field outcomes—not another search over fine-scale NDVI weights.
