# Cirsium × aza3 prospective local-discovery bridge

Status: **pre-occurrence-retrieval / pre-field contract frozen**

This bridge uses the independently motivated `aza3` Japan-wide *Cirsium* sampling programme to test and improve ACSP's occurrence-anchored local-discovery line. It does not alter the validated 2.5% robust candidate-patch product or retroactively add a new system to the Ecological Informatics result.

## Scientific division of labour

### aza3

Chooses the biological target:

- operational species concept;
- tree hole / representation slot;
- range sector;
- conservation/acquisition mode;
- permission and exact private locality;
- field-campaign order;
- target-capture, RAD and M01 allocation.

### ACSP

Receives one declared aza3 slot and asks:

> Given the pre-2026 occurrence evidence and declared range sector, which bounded patches justify a current-occurrence search, or should the method abstain?

ACSP does not re-rank phylogenetic priorities.

## Input freeze

The first prospective Cirsium bridge uses only records whose event date is no later than **2025-12-31**. Records from the prospective 2026+ field era cannot silently enter anchor construction.

Taxon matching is exact to the aza3 operational concept or an explicitly reviewed concept/synonym crosswalk. Provider failure, zero records and taxonomic conflict are retained states, not reasons to substitute a nearby taxon.

### Primary local anchor

A primary local anchor requires:

1. reconciled focal taxon identity;
2. decimal coordinates;
3. no provider geospatial-issue flag;
4. declared coordinate uncertainty <=1,000 m, unless a source-backed precision override was frozen before field outcomes;
5. event year 2000–2025;
6. compatibility with the declared aza3 range sector.

Missing coordinate uncertainty is not automatically interpreted as exact.

Precise 1950–1999 records form a legacy sensitivity layer. Pre-1950, date-unknown, obscured, high-uncertainty and region-only records remain context but do not create the primary local-continuation kernel.

## Evidence is typed, not flattened

Each public record retains independent axes for:

- spatial precision;
- temporal class;
- basis/provenance;
- taxon-concept match;
- provider geospatial status;
- stable source occurrence ID.

This matters especially for rare plants: an old specimen, an obscured conservation record and a recent precise observation are not interchangeable evidence even when all have a nominal latitude/longitude field somewhere upstream.

## Two-graph architecture

### `G_E` — ecological support

Construct ecological components before using human accessibility. Candidate structural families may include terrain/topography, substrate, moisture/wetland state, coastal/island structure, vegetation/open-ground structure and ecological barriers. Feature families must be justified from the declared taxon/habitat evidence before field outcomes; ACSP does not build one kitchen-sink feature stack simply because layers are available.

### `G_F` — survey feasibility

Apply access after ecological candidate construction: roads/trails or movement mode, land access, protected-area/conservation restrictions, permission state and physical safety/accessibility.

An ecologically supported but inaccessible patch stays `SUPPORTED_BUT_OPERATIONALLY_UNAVAILABLE`. Human accessibility cannot create ecological support, and access failure cannot become biological absence.

## Discovery regimes

1. **LOCAL_CONTINUATION** — an eligible recent anchor exists in the target ecological component. A known-point exclusion prevents trivial rediscovery.
2. **DETACHED_COMPONENT** — an anchor exists, but a structurally similar candidate component is separated by an ecological gap/barrier.
3. **SENTINEL** — no eligible local anchor exists. Use the broader validated robust-support envelope plus spatially balanced exploration; report separately.
4. **ABSTAIN_LOCAL_PATCH** — public evidence cannot justify a bounded local patch without false precision.

Abstention is a valid result. aza3 may still use local experts, collaborators, herbarium material or a separately designed broad survey, but those routes are not retroactively scored as ACSP local-patch successes.

## Why Cirsium is useful for algorithm development

Campanula development exposed two limits:

- nearest-anchor search recovers many historical clusters only by widening the annulus substantially;
- generic NDVI filtering, including a coverage-constrained hybrid, did not add stable recovery beyond deterministic spatial balance.

Cirsium supplies a different and harder test because its required slots span wetlands, coasts/islands, alpine systems, limestone/serpentine substrates, broad-range species, narrow endemics, public-singleton complements and anchor-poor taxa. This enables a prospective test of **structural ecological continuity** rather than another generic vegetation-score rescue.

The feature family for a slot must be declared before its new field outcome. For example, a wetland taxon may justify a moisture/wetland structural family; a limestone endemic may justify substrate structure. A successful feature family in one taxon cannot be back-propagated to retune already opened Cirsium slots.

## ACSP output

The current scientific layer ends at:

`typed occurrence evidence -> ecological components -> bounded candidate patches -> feasibility state -> patch / abstain`

It does **not** yet estimate optimal field days, total budget, discovery yield per hour or an automatic stopping threshold. Campanula has positive-only field outcomes and therefore cannot identify these quantities.

If the Cirsium campaign accumulates complete visited-patch detections and non-detections with standardized effort, a separate future contract may test effort-aware stopping.

## Prospective field endpoint

Primary ACSP success is a **taxonomically verified current occurrence** of the declared focal taxon after a completed, evaluable search.

Tissue collection is secondary. A verified plant in a no-collection site is an ACSP location-discovery success while remaining an aza3 tissue-acquisition failure/block.

Allowed field states are:

- `SEARCH_COMPLETED_DETECTED_VERIFIED`;
- `SEARCH_COMPLETED_NOT_DETECTED`;
- `SEARCH_COMPLETED_DETECTED_IDENTITY_UNRESOLVED`;
- `ACCESS_FAILED`;
- `PERMISSION_BLOCKED`;
- `PHENOLOGY_NOT_EVALUABLE`;
- `SEARCH_INCOMPLETE_OTHER`.

The last four are not recoded as biological non-detections.

Every evaluated patch records at least search minutes and observer count, with traversed length and searched area when defensibly measured. Exact sensitive coordinates stay in the private aza3 ledger; ACSP stores deidentified patch/locality IDs.

## Comparators and promotion

Anchor-conditioned candidates must beat strong spatial baselines at matched field effort, especially:

- annular nearest-known;
- deterministic spatial balance on the same candidate universe;
- matched-effort random/proportional spatial sampling where feasible.

Sentinel cases also compare with the broad validated robust-support envelope.

The failed Campanula NDVI hybrid is not revived.

A Cirsium result is eligible to support external occurrence-to-survey portability only if the provider/query rules, precision typing, ecological graph, known-point exclusion, candidate construction, abstention rule, field endpoint and comparator assignment were all frozen before the new field outcomes used for that test.

Conservation-sensitive and historical-only slots remain valuable operational applications but are not the primary method-performance denominator when standardized current-occurrence search is impossible.
