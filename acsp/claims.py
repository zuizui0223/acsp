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
        "claim_id": "sdm_superiority",
        "status": "not_tested",
        "scope": "Comparison with SDM-led and other established site-selection methods",
        "permitted_wording": "ACSP addresses a downstream finite-set decision estimand and has not established universal superiority over SDMs or survey-design algorithms.",
        "prohibited_wording": "ACSP is better than SDM.",
    },
)


def claim_status_table() -> pd.DataFrame:
    return pd.DataFrame(CLAIM_MATRIX).copy()
