# Practical Rescue prospective production gate

Status: **design specification only; no field outcome has been evaluated**

This gate is deliberately separate from the frozen retrospective 10-km candidate-zone confirmation. A retrospective pass can validate an ecological finite-decision policy, but it cannot establish accessibility, detectability, occupancy, abundance, phenology, or discoveries per field day.

## Required field record

Every planned candidate visit must remain in the data, including failures and non-detections. One row per site-attempt should contain at least:

- `survey_campaign_id`
- `taxon_id` / `scientific_name`
- `region_id`
- `frozen_policy_id` and immutable policy/model fingerprint
- `candidate_id`, planned latitude/longitude, and pre-field rank
- `assignment_arm` (`practical_rescue`, frozen comparator, or declared control)
- `visit_id`, date, start/end time, observer/team ID
- `attempted` (boolean; planned rows may not disappear)
- `access_outcome` (`reached`, `blocked`, `unsafe`, `permission_denied`, `weather_abort`, `other`)
- `access_failure_reason` and optional distance/time lost to access failure
- standardized search effort (`person_minutes` plus method/protocol)
- `detection` (boolean for every reached standardized attempt)
- detection count when meaningful, but count is secondary unless its observation model is predeclared
- phenological/season state and major weather covariates recorded before interpreting non-detection
- optional repeated-visit identifier so detection probability can be separated from occupancy when the design supports it

Rows must not be deleted because a site was inaccessible, a survey was aborted, or the focal taxon was not detected.

## Design requirements before confirmatory field outcomes

1. Freeze the Practical Rescue model and all comparator policies before site assignment.
2. Use the same candidate-generation information cutoff for all assignment arms.
3. Predeclare allocation within taxon-region strata. Prefer randomized or randomized-order assignment where logistically feasible; otherwise use matched strata and record the reason randomization was impossible.
4. Preserve planned sites that cannot be attempted as explicit access/logistics outcomes rather than replacing them post hoc.
5. Standardize the search protocol and record effort for every reached attempt.
6. Where occupancy/detection probability is claimed, use repeated visits or another predeclared design capable of separating the two; a single non-detection is not absence.
7. Freeze the analysis code and confirmatory endpoint before the confirmatory wave. A pilot wave may be used only to estimate variance/sample size and refine logistics; pilot outcomes are excluded from the confirmatory test if they informed the design.

## Promotion endpoints

The production gate has three distinct components and must report all of them.

### A. Execution / accessibility

Report intention-to-survey from every planned assignment:

- fraction attempted;
- fraction reached;
- access-failure fractions by reason;
- travel/search effort consumed per planned and per reached site.

Practical Rescue must not obtain an apparent ecological advantage by silently dropping harder sites. Any non-inferiority margin for reachability must be fixed after a pilot and before the confirmatory wave.

### B. Pragmatic field utility

Primary pragmatic outcome should be predeclared for the final campaign, for example focal detections per standardized person-hour or probability of focal detection during a standardized reached-site attempt. Analyze at the taxon-region level or with a predeclared hierarchical model so heavily sampled taxa/regions cannot dominate.

The final effect threshold and power/sample size are not guessed here. Estimate them from a pilot or external evidence, freeze them before the confirmatory wave, then run the confirmatory analysis once.

### C. Detectability / occupancy interpretation

If repeated visits are available, estimate detection probability separately from site occurrence/occupancy with a predeclared repeated-visit model. Without such a design, wording is limited to pragmatic detection yield; do not claim occupancy or true absence.

## Promotion rule

`production_field_promotion_passed` may become true only after a confirmatory prospective wave has:

- complete intention-to-survey accounting of every frozen planned site;
- no post-assignment site replacement driven by field outcome;
- the predeclared accessibility gate satisfied;
- the predeclared pragmatic field-utility effect gate satisfied with its uncertainty criterion;
- all required effort/non-detection/access fields complete enough for the predeclared analysis;
- no post-outcome retuning of the Rescue model or promotion thresholds.

A retrospective fresh-confirmation pass alone leaves production status as `blocked_pending_prospective_field_attempt_non_detection_effort_and_access_records`.

## Claim boundary

Passing the retrospective 10-km gate supports regional survey-decision recovery only. Passing this prospective gate can support pragmatic field-planning utility under the tested campaigns. Exact-site occupancy, general detectability, abundance, or universal field efficiency require the corresponding study design and cannot be inferred automatically from either gate.
