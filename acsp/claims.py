"""Machine-readable interpretation boundary for ACSP outputs."""
from __future__ import annotations

import pandas as pd

CLAIM_MATRIX: tuple[dict[str, str], ...] = (
    {
        "claim_id": "regional_top5_10km",
        "status": "validated",
        "scope": "Frozen plant and animal policies in independent Japanese taxon-region cohorts",
        "permitted_wording": "ACSP Top-5 regional selections recovered more held-out occurrences within 10 km than random Top-5 sets from the identical candidate pools.",
        "prohibited_wording": "ACSP predicts occupied exact sites.",
    },
    {
        "claim_id": "selection_component_attribution",
        "status": "secondary_support",
        "scope": "Predeclared 2026-07-24 reconstruction benchmark on the same frozen taxon-region cohorts using refreshed GBIF records and newly generated spatial folds",
        "permitted_wording": "The secondary comparator benchmark supports focal-taxon local-habitat ranking as the principal observed selection signal. Animal ACSP was not detectably better than local-evidence-only Top-5, while ACSP exceeded generic environmental maximin; differences from geographic maximin were unresolved.",
        "prohibited_wording": "Geographic complementarity has been independently validated as the source of ACSP performance.",
    },
    {
        "claim_id": "general_5km_precision",
        "status": "not_supported",
        "scope": "General name-only workflow",
        "permitted_wording": "Five-kilometre results are sensitivity analyses and remain unsupported as a general exact-location claim.",
        "prohibited_wording": "ACSP is validated to 5 km.",
    },
    {
        "claim_id": "full_integrated_score",
        "status": "software_feature_not_independently_validated",
        "scope": "Production observed/local/macro/gap/access/field-feedback score",
        "permitted_wording": "The application exposes a transparent integrated evidence score outside the validated paper core.",
        "prohibited_wording": "All production score components are cross-taxon validated.",
    },
    {
        "claim_id": "access_detectability_efficiency",
        "status": "not_validated",
        "scope": "Access, detectability, abundance, phenology and discoveries per field day",
        "permitted_wording": "These quantities require prospective standardized field records.",
        "prohibited_wording": "Recommended zones are reachable, occupied, or more efficient in the field.",
    },
    {
        "claim_id": "sdm_relationship",
        "status": "positioned",
        "scope": "Relationship between ACSP finite-set survey decisions and fitted species distribution models",
        "permitted_wording": "SDMs estimate a pointwise model quantity such as relative suitability, intensity, or occurrence probability depending on model design, whereas ACSP produces a finite regional survey decision under a candidate budget. ACSP can use SDM output as one optional evidence channel rather than replacing the SDM estimand.",
        "prohibited_wording": "ACSP and SDM estimate the same quantity, or ACSP replaces species distribution modeling.",
    },
    {
        "claim_id": "sdm_decision_comparison",
        "status": "secondary_decision_contrast_complete",
        "scope": "Predeclared untouched 24-pair same-training-fold, same-candidate-pool Top-5 comparison with ACSP's production fitted-SDM ranking",
        "permitted_wording": "In the frozen matched-pool benchmark, ACSP and fitted-SDM Top-5 ranking had similar 10-km regional recovery but usually selected different candidates: among 101 SDM-evaluable folds, the mean Top-5 Jaccard overlap was 0.264 and exact set agreement occurred in one fold. This supports an operational distinction between pointwise fitted-model ranking and occurrence-conditioned finite-set survey selection, not universal superiority of either method.",
        "prohibited_wording": "ACSP is better than SDM, SDM is generally inferior for survey planning, or similar recall proves that ACSP and SDM are equivalent methods.",
    },
)


def claim_status_table() -> pd.DataFrame:
    return pd.DataFrame(CLAIM_MATRIX).copy()
