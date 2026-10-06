from __future__ import annotations

import math

import pandas as pd

import research.materialize_cirsium_fresh_sentinel_v2_primary_fine_grid as mod


def _outer() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "candidate_cell_id": ["a", "b", "c", "d"],
            "latitude": [35.0, 35.01, 36.0, 36.01],
            "longitude": [139.0, 139.01, 140.0, 140.01],
        }
    )


def _order() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "candidate_cell_id": ["a", "b", "c", "d"],
            "source_state": [mod.READY, mod.READY, "SOURCE_INDETERMINATE_RETAIN", "SOURCE_INDETERMINATE_RETAIN"],
            "coarse_evidence_rank": pd.array([1, 2, pd.NA, pd.NA], dtype="Int64"),
        }
    )


def test_primary_grid_is_exact_union_and_excludes_indeterminate(monkeypatch) -> None:
    monkeypatch.setattr(mod, "EXPECTED_CANDIDATES", 4)
    monkeypatch.setattr(mod, "SUPPORT_FRACTION", 0.5)

    centers = mod._restore_centers(_order(), _outer(), "CIR02")
    assert centers["candidate_cell_id"].tolist() == ["a"]
    forward, _ = mod._transformers()
    x, y = forward.transform(float(centers.iloc[0]["longitude"]), float(centers.iloc[0]["latitude"]))
    expected_count = len(mod._cell_set_for_center(float(x), float(y), mod.PRIMARY_RADIUS_KM * 1000.0))

    contract = {
        "fine_grid": {"projection_identity": "JAPAN_CENTERED_AEQD_V1"},
        "expected_unit_cell_counts_from_frozen_audit": {"CIR02": expected_count},
    }
    size_result = {
        "unit_results": {"CIR02": {"primary_2km": {"unioned_100m_cells": expected_count}}}
    }
    monkeypatch.setattr(mod, "_load_contracts", lambda: (contract, size_result))

    frame, summary = mod.materialize_unit_primary_fine_grid(_order(), _outer(), "CIR02")
    assert len(frame) == expected_count
    assert frame["candidate_cell_id"].is_unique
    assert not frame[["grid_row", "grid_col"]].duplicated().any()
    assert summary["retained_coarse_center_count"] == 1
    assert summary["source_indeterminate_included"] is False
    assert summary["ecological_sources_attached"] is False
    assert summary["structural_graph_computed"] is False
    assert summary["field_outcomes_opened"] is False


def test_primary_grid_cell_centers_are_on_shared_100m_lattice(monkeypatch) -> None:
    monkeypatch.setattr(mod, "EXPECTED_CANDIDATES", 4)
    monkeypatch.setattr(mod, "SUPPORT_FRACTION", 0.5)
    centers = mod._restore_centers(_order(), _outer(), "CIR02")
    forward, _ = mod._transformers()
    x, y = forward.transform(float(centers.iloc[0]["longitude"]), float(centers.iloc[0]["latitude"]))
    expected_count = len(mod._cell_set_for_center(float(x), float(y), mod.PRIMARY_RADIUS_KM * 1000.0))
    monkeypatch.setattr(
        mod,
        "_load_contracts",
        lambda: (
            {
                "fine_grid": {"projection_identity": "JAPAN_CENTERED_AEQD_V1"},
                "expected_unit_cell_counts_from_frozen_audit": {"CIR02": expected_count},
            },
            {"unit_results": {"CIR02": {"primary_2km": {"unioned_100m_cells": expected_count}}}},
        ),
    )
    frame, _ = mod.materialize_unit_primary_fine_grid(_order(), _outer(), "CIR02")
    assert ((frame["projected_x_m"] / 100.0 - 0.5) - frame["grid_col"]).abs().max() < 1e-9
    assert ((frame["projected_y_m"] / 100.0 - 0.5) - frame["grid_row"]).abs().max() < 1e-9
    assert frame["primary_local_radius_km"].eq(2.0).all()
    assert frame["grid_spacing_m"].eq(100.0).all()
