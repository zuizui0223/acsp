from __future__ import annotations

import pandas as pd
import pytest

from research.build_cirsium_private_sector_structural_grid_v1 import expected_family
from research.materialize_cirsium_fresh_sentinel_public_sources_v1 import (
    EXPECTED_UNITS,
    _unit_row,
    qualified_uncertainty_evidence,
)


def test_fresh_source_materializer_is_restricted_to_frozen_unopened_units() -> None:
    assert EXPECTED_UNITS == ("CIR02", "CIR06", "CIR12", "CIR13")
    for unit_id in EXPECTED_UNITS:
        cohort, requirements = _unit_row(unit_id)
        assert cohort["outcome_opened"].lower() == "false"
        assert cohort["fresh_field_outcome_eligible"].lower() == "true"
        assert requirements["occurrence_problem_class"] == "SENTINEL"

    with pytest.raises(ValueError):
        _unit_row("CIR01")


def test_uncertainty_materializer_matches_frozen_broad_evidence_rule() -> None:
    records = [
        {
            "key": 1,
            "year": 2022,
            "decimalLatitude": 40.1,
            "decimalLongitude": 140.2,
            "coordinateUncertaintyInMeters": 1500,
            "issues": [],
        },
        {
            "key": 2,
            "year": 2022,
            "decimalLatitude": 40.2,
            "decimalLongitude": 140.3,
            "coordinateUncertaintyInMeters": 1000,
            "issues": [],
        },
        {
            "key": 3,
            "year": 1999,
            "decimalLatitude": 40.3,
            "decimalLongitude": 140.4,
            "coordinateUncertaintyInMeters": 3000,
            "issues": [],
        },
        {
            "key": 4,
            "year": 2023,
            "decimalLatitude": 40.4,
            "decimalLongitude": 140.5,
            "coordinateUncertaintyInMeters": 2500,
            "informationWithheld": "generalized",
            "issues": [],
        },
        {
            "key": 5,
            "year": 2024,
            "decimalLatitude": 40.5,
            "decimalLongitude": 140.6,
            "coordinateUncertaintyInMeters": 2500,
            "issues": ["COUNTRY_COORDINATE_MISMATCH"],
        },
        {
            "key": 6,
            "year": 2025,
            "decimalLatitude": 40.6,
            "decimalLongitude": 140.7,
            "coordinateUncertaintyInMeters": 4000,
            "issues": [],
        },
    ]
    out = qualified_uncertainty_evidence(records)
    assert isinstance(out, pd.DataFrame)
    assert out["gbif_key"].tolist() == ["1", "6"]
    assert (out["coordinate_uncertainty_m"] > 1000).all()
    assert out["year"].tolist() == [2022, 2025]


def test_sector_context_builder_has_only_predeclared_nonfootprint_units() -> None:
    assert expected_family("CIR06") == "ALPINE_TOPOGRAPHIC_STRUCTURE"
    assert expected_family("CIR13") == "OPEN_GRASSLAND_STRUCTURE"
    for forbidden in ("CIR01", "CIR02", "CIR04", "CIR07", "CIR08", "CIR12"):
        with pytest.raises(ValueError):
            expected_family(forbidden)
