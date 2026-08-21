# AGENTS.md

This repository contains a Streamlit app for GBIF-based field-survey planning.

## Authoritative validated-product boundary

Before changing candidate generation, scientific claims, validation logic, ranking, routing, SDM/SSDM integration, or field-planning behavior, read `VALIDATED_PRODUCT_CONTRACT.md`.

`VALIDATED_PRODUCT_CONTRACT.md` is authoritative for the independently validated ACSP product. If older planning, positioning, README, legacy, or research prose conflicts with that contract, the contract takes precedence for the current validated path.

The validated core produces **non-ranked robust candidate patches**. Historical ranking, zone scoring, routing, day/budget estimation, SDM/SSDM re-ranking, access weighting, and adaptive field-learning code may remain available as operational, compatibility, exploratory, or research layers, but must not be silently reintroduced into the validated candidate-patch path.

## Source of truth

GitHub is the only source of truth for this project.

Before editing, every AI coding agent must read the latest relevant files from the current GitHub branch, preferably `main` unless the user explicitly specifies another branch.

Do not use local files, old workspace copies, previous conversation memory, old Codex/Claude thread state, or previously generated snippets as the baseline for edits unless they are first compared against the latest GitHub version.

If local code differs from GitHub, treat GitHub as authoritative.

If there is any uncertainty about whether a feature already exists or has changed, inspect the latest GitHub file first and preserve the current behavior.

## Required design and research policy

Before changing workflow, sampling, candidate generation, SDM, SSDM, large-dataset behavior, map selection, exports, or field-validation behavior, read:

- `VALIDATED_PRODUCT_CONTRACT.md`
- `SURVEY_PLANNING_POLICY.md`
- `RESEARCH_POSITIONING.md`

`VALIDATED_PRODUCT_CONTRACT.md` defines the current independently validated scientific product and claim ceiling.

`SURVEY_PLANNING_POLICY.md` defines broader application and operational workflow constraints outside that validated core.

`RESEARCH_POSITIONING.md` defines broader scientific purpose, publication history, intended users, hypotheses, and field-validation goals; statements there do not broaden the validated claim beyond `VALIDATED_PRODUCT_CONTRACT.md`.

This app is a field-survey planning tool, not a general all-record SDM analysis platform.

The app should convert occurrence records into practical survey-site decisions. Occurrence-supported candidates must work without SDM. Optional SDM is especially useful for sparse or incomplete records and may identify exploratory model-only sites. Genus / SSDM workflows should support multi-species, taxonomic, phylogeographic, and evolutionary sampling.

## Repository layout rule

The repository root is the **survey-planning tool**: `gbif_fieldmap_builder_app.py`, `acsp/`, `acsp_discover.py`, `r-acsp/`, and their tests.

Validation, benchmark, comparator, and cohort-sampling code belongs in `research/`, not the root. When adding a script, decide which side it is on before choosing its path. Frozen data artifacts (`validation/`, `benchmark_results/`, `benchmark_methods/`, `paper/`, `field_validation/`) stay at the root because protocol fingerprints and provenance records were written against those paths.

Research scripts resolve data paths relative to the repository root and are run from there. CI sets `PYTHONPATH` for workflows that reach into `research/`.

## The validated core must work without a model or planner

The independently validated ACSP path must reach a complete candidate-patch set with no SDM, SSDM, historical integrated score, priority ranking, route optimizer, day-count target, or monetary budget in the loop.

Operational planning features may consume those patches downstream, but they must not alter validated patch membership unless a new scientific method is explicitly frozen and revalidated.

Do not make a model a precondition for candidate-patch generation, do not present model support as part of the validated patch claim, and do not let a model failure block or degrade the validated non-model product.

## Core rule

Do not remove existing features unless the user explicitly asks for removal.

Existing features that must be preserved:

- GBIF paginated occurrence download
- Flexible CSV upload with latitude/longitude auto-detection
- Map-click occurrence exclusion
- Rectangle/batch occurrence exclusion when implemented
- Red QC-only excluded occurrence points
- Ensemble SDM
- VIF stepwise filtering with a user-defined threshold
- Spatial partition diagnostics for AUC
- Raster-style SDM prediction map
- SDM-high exploration candidate ranges
- Selected survey site list
- Genus-level occurrence richness map when implemented
- SSDM mode when implemented
- HTML/CSV downloads

Preserving these software features does not make them part of the validated candidate-patch scientific claim.

## Anti-rollback rules

AI agents must not roll back recent work.

Before making changes, check the latest `CHANGELOG_AI.md` and the current target file on GitHub.

Preserve any feature described in `CHANGELOG_AI.md` unless the user explicitly asks to remove or hide it.

Do not reintroduce UI elements or older workflows that were intentionally removed or hidden, such as:

- preliminary straight-line day splitting as a main workflow
- required `Survey days` blocks as a main workflow
- duplicated `Priority survey ranges` table at the bottom, if it has been removed
- daily sampling route layers, if they have been removed
- redundant occurrence buffer plus survey range layers, if they have been simplified
- all-record-first model workflows as the default

Do not weaken these scientific design concepts:

- validated robust candidate patches remain planner-free and non-ranked;
- occurrence-supported candidates must remain available without SDM;
- SDM must remain optional and especially useful for sparse occurrence data;
- SDM-high exploration candidates must remain clearly labeled exploratory;
- Step 2 survey-area selection must not automatically become the SDM extent;
- researcher-owned CSV uploads must remain a first-class input;
- genus / SSDM workflows must remain relevant to multi-species and evolutionary sampling;
- field validation must remain part of the intended workflow;
- the interface should remain map-first and fieldwork-oriented.

If a requested change conflicts with an existing feature, make the smallest safe change without deleting unrelated functionality.

## Collaboration rules for AI coding agents

1. Read this file before editing.
2. Read `VALIDATED_PRODUCT_CONTRACT.md`, `SURVEY_PLANNING_POLICY.md`, and `RESEARCH_POSITIONING.md` before changing workflow, sampling, candidate generation, SDM, SSDM, selection, exports, or field-validation behavior.
3. Read the latest relevant files from GitHub before editing.
4. Prefer small diffs over full-file rewrites.
5. Do not push directly to `main` unless the user explicitly asks.
6. Use feature branches and pull requests when possible.
7. After every code change, update `CHANGELOG_AI.md`.
8. Run the following before finishing:

```bash
python -m py_compile gbif_fieldmap_builder_app.py
```

9. If routing or survey-site-list code is changed, confirm the app still works both before and after SDM is built.
10. If occurrence-exclusion code is changed, confirm that red QC points remain visible but are not used for SDM, prediction extent, candidate generation, or survey site lists.
11. If SDM code is changed, confirm that VIF, spatial partition options, prediction maps, and SDM-high exploration candidates still exist.
12. If genus diversity or SSDM code is changed, confirm that the single-species workflow still works.
13. If UI labels are changed, keep the distinction clear:
    - Included points = used for analysis
    - Excluded QC points = visible but not used for analysis
    - Raw records = preserved for transparency/download
    - Working subsets = used for candidates, SDM, and SSDM
    - Occurrence-supported candidates = based on known records
    - SDM-high exploration candidates = model-only, exploratory, and field-validation required

## Large-file editing rule

Avoid rewriting the entire `gbif_fieldmap_builder_app.py` file unless absolutely necessary.

For bug fixes, edit only the smallest relevant section.

For new features, prefer adding helper functions and connecting them with minimal changes.

Before replacing any function, compare the latest GitHub version and ensure no recent behavior is lost.

## Route-planning / survey-site-list note

The app should not pretend to solve real road routing.

Straight-line routing does not account for roads, ferries, mountains, cliffs, restricted access, or island barriers. Field routes should be verified in Google Maps before fieldwork.

The preferred operational workflow is:

- start from the validated candidate-patch product or other explicitly labeled candidate sources;
- select candidate survey sites downstream;
- show one unified selected survey site list;
- open selected sites in Google Maps or export CSV/HTML;
- keep any day-splitting or route optimization as optional or hidden unless explicitly requested.

Route choices are operational outputs and are not part of the validated candidate-patch claim.

## Genus / SSDM note

Genus-level richness and SSDM workflows can be expensive.

Do not run full SSDM automatically. Use lightweight defaults, record caps, species caps, progress reporting, and shared variable filtering.

Occurrence richness maps and SSDM predicted richness maps must be clearly distinguished:

- Occurrence richness = observed species richness from occurrence records.
- SSDM richness = predicted richness from stacked species-level SDMs.

Genus / SSDM outputs should support biodiversity, taxonomic, phylogeographic, and evolutionary sampling decisions rather than prediction maps alone. They remain outside the independently validated single-species robust candidate-patch claim unless separately validated.

## Changelog requirement

Every AI edit must add an entry to `CHANGELOG_AI.md` with:

- Date
- Agent
- Changed files
- Summary
- Features preserved
- Known risks / TODO

The changelog should mention when a feature is intentionally hidden or removed, so later agents do not accidentally restore it.
