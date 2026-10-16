from __future__ import annotations

import pandas as pd
import pytest

import research.audit_cirsium_fresh_sentinel_v2_fine_worldcover_availability as mod


def _fine_grid(unit: str = "CIR02") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cohort_unit_id": [unit, unit, unit],
            "candidate_cell_id": [f"{unit}-a", f"{unit}-b", f"{unit}-c"],
            "grid_row": [1, 2, 3],
            "grid_col": [4, 5, 6],
            "latitude": [35.0, 35.01, 35.02],
            "longitude": [139.0, 139.01, 139.02],
        }
    )


def test_audit_preserves_denominator_and_indeterminate_semantics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mod,
        "_load_contract",
        lambda: {
            "provider": {"neighbourhood_radius_m": 250.0, "blocked_pixel_chunk": 2048},
            "candidate_denominator": {
                "source_states": [
                    "SOURCE_COMPLETE",
                    "INDETERMINATE_NEIGHBOURHOOD_UNAVAILABLE",
                    "INDETERMINATE_PROVIDER_FAILURE",
                ]
            },
        },
    )

    class Audit:
        source_complete_rows = 1
        neighbourhood_unavailable_rows = 1
        provider_failure_rows = 1
        provider_failure_tile_ids = ("N33E138",)
        source_tile_ids = ("N33E138", "N33E141")
        source_complete_feature_digest_sha256 = "a" * 64
        neighbourhood_radius_m = 250.0
        release_id = "2021_v200"

    def fake_provider(frame, *, radius_m, block_pixels):
        out = frame.copy()
        out["worldcover_source_state"] = [
            "SOURCE_COMPLETE",
            "INDETERMINATE_NEIGHBOURHOOD_UNAVAILABLE",
            "INDETERMINATE_PROVIDER_FAILURE",
        ]
        for column in mod.FEATURE_COLUMNS:
            out[column] = [0.25, float("nan"), float("nan")]
        return out, Audit()

    monkeypatch.setattr(mod, "audit_worldcover_neighbourhood_availability_blocked", fake_provider)
    audited, summary = mod.audit_unit(_fine_grid(), unit_id="CIR02")
    assert len(audited) == 3
    assert audited["candidate_cell_id"].tolist() == ["CIR02-a", "CIR02-b", "CIR02-c"]
    assert summary["source_complete_rows"] == 1
    assert summary["neighbourhood_unavailable_rows"] == 1
    assert summary["provider_failure_rows"] == 1
    assert summary["candidate_denominator_preserved"] is True
    assert summary["source_indeterminate_recoded_as_absence"] is False
    assert summary["source_indeterminate_recoded_as_zero_support"] is False
    assert summary["structural_graph_computed"] is False
    assert summary["field_outcomes_opened"] is False


def test_cir06_cannot_gain_undeclared_worldcover_dependency() -> None:
    with pytest.raises(ValueError, match="no frozen fine WorldCover dependency"):
        mod.audit_unit(_fine_grid("CIR06"), unit_id="CIR06")
