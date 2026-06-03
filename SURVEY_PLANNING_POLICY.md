# Survey planning policy for AI coding agents

This app is a field-survey planning tool, not a full all-record SDM analysis platform.

## Core principle

Do not push all GBIF occurrence records into maps, candidate generation, SDM, or SSDM by default.

Raw records should be preserved for transparency, summaries, and downloads. Downstream app steps should use spatially representative working subsets that are appropriate for field-survey planning.

The goal is not to maximize the number of occurrence records used in every computation. The goal is to identify realistic, field-ready survey candidates quickly, reproducibly, and with reduced observer/access bias.

## Scientific rationale

For field-survey planning, using every public occurrence record is often unnecessary and can be harmful.

Large GBIF/iNaturalist-style datasets are commonly clustered near roads, towns, popular trails, and accessible places. These clusters can make maps slow, bias candidate ranking toward well-observed areas, and make optional SDM/SSDM workflows too heavy for a Streamlit app.

The preferred workflow is therefore:

1. Keep all raw records.
2. Let the user define the active target occurrence set or survey range.
3. Build spatially representative working subsets.
4. Generate observed-data survey candidates from the representative subset.
5. Optionally use SDM/SSDM predictions as weighted support for re-ranking candidates.
6. Validate the candidate ranking through field survey.

This is a deliberate methodological choice, not data loss.

## Default working-set policy

Recommended defaults for normal field-survey planning:

- Raw records: keep all loaded records for summary and download.
- Map display records: about 500 records by default.
- Candidate input records: about 800 records by default.
- SDM presence records: about 300 records by default.
- SSDM presence records: about 150 records per species by default.

For detailed analysis mode, the app may allow higher limits, for example:

- Map display records: about 1000.
- Candidate input records: about 1500.
- SDM presence records: about 500.
- SSDM presence records: about 300 per species.

Custom mode may expose manual caps, but the default should remain lightweight and stable.

## Required data separation

Keep these concepts separate in code and UI:

- `occ_raw`: all cleaned raw records.
- `occ_qc_included`: records after explicit QC exclusions.
- `occ_extent_selected`: active target occurrence set after survey-range selection.
- `occ_map_display`: capped records used only for interactive maps.
- `occ_candidate_input`: spatially representative records used for occurrence-based candidates.
- `occ_sdm_train`: bias-reduced presence records used for optional SDM.

For genus mode, use analogous working sets for richness hotspots and SSDM.

## Target occurrence set and survey range

The user should be able to decide which occurrence records define the survey range.

Main options:

- Use all cleaned records.
- Use only records inside a drawn rectangle.
- Exclude records inside a drawn rectangle.

The rectangle is not the final SDM extent. It only chooses the occurrence records used to build candidates and later optional prediction extents.

Detailed coordinate QC should be advanced/optional, not a required main workflow.

## Candidate generation before SDM/SSDM

Observed occurrence data must generate base survey candidates before any model is run.

SDM/SSDM is optional. It should not replace observed-data candidates and should not be required to proceed.

Candidate ranking should support this structure:

`priority_score = observed_weight * occurrence_support_score + model_weight * model_support_score + optional bonuses`

Recommended default weights:

- observed-data weight: 0.7
- SDM/SSDM model weight: 0.3

If SDM/SSDM has not been run, rank by observed occurrence support only and show that model support is unavailable.

## Survey-planning mode UI

Prefer a simple mode selector rather than many technical controls by default:

- Fast survey planning, recommended default.
- Detailed analysis.
- Custom.

Fast survey planning should use lightweight caps and representative sampling automatically.

Technical controls such as map caps, grid thinning, distance thinning, exact deduplication, DBSCAN parameters, and SDM/SSDM caps should be hidden under advanced settings unless the user chooses custom/detailed mode.

## Validation for publication

The planned paper should test whether representative subsets are sufficient for field-survey planning.

Recommended validation comparisons:

- All records versus representative subsets, such as 1500, 800, 500, and 300 retained records.
- Top-10 or Top-20 candidate overlap.
- Rank correlation between candidate lists.
- Spatial coverage or environmental-space coverage.
- Runtime and map responsiveness.
- Field detection success at ranked candidate sites.

The expected claim is:

Spatially representative occurrence subsets can preserve field-survey-relevant candidate rankings while greatly reducing computational cost and reducing observer/access-bias effects.

## Anti-rollback rule

Do not reintroduce an all-record-first workflow as the default.

Do not make the app depend on rendering or modeling all raw records before the user can access occurrence-based survey candidates.

Preserve raw records, but use representative working subsets for field-survey planning.