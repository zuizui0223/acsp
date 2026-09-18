from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import research.derive_cirsium_fresh_sentinel_movement_capacity_v1 as mod


def _frame() -> pd.DataFrame:
    return pd.DataFrame({
        "candidate_cell_id": ["z", "a", "b", "c", "d"],
        "coverage_cell_id": ["cell1", "cell1", "cell2", "cell3", "cell3"],
        "latitude": [35.0, 35.001, 35.01, 35.02, 35.021],
        "longitude": [139.0, 139.001, 139.01, 139.02, 139.021],
        "structural_support": [0.99, 0.01, 0.5, 0.2, 0.8],
    })


def test_coarse_representative_ignores_structural_score_and_is_stable() -> None:
    first = mod.build_outcome_blind_coarse_representatives(_frame(), unit_id="CIR02")
    changed = _frame().copy()
    changed["structural_support"] = list(reversed(changed["structural_support"].tolist()))
    second = mod.build_outcome_blind_coarse_representatives(changed, unit_id="CIR02")
    pd.testing.assert_frame_equal(first, second)
    assert first["candidate_patch_id"].tolist() == ["cell1", "cell2", "cell3"]
    assert set(first["patch_merge_distance_m"]) == {5000.0}
    assert set(first["representative_rule"]) == {"STABLE_HASH_WITHIN_FROZEN_COARSE_CELL_V1"}


def test_explicit_reachability_selected_count_becomes_prefix_depth() -> None:
    reps = mod.build_outcome_blind_coarse_representatives(_frame(), unit_id="CIR02")
    edges = pd.DataFrame({
        "from_patch_id": ["cell1", "cell2"],
        "to_patch_id": ["cell2", "cell3"],
    })
    depth, audit = mod.automatic_prefix_depth_from_reachability(reps, edges)
    assert depth >= 1
    assert depth <= len(reps)
    assert audit["user_site_count_required"] is False
    assert audit["user_coverage_target_required"] is False
    assert audit["final_coverage_fraction"] == 1.0
    assert audit["coverage_scale_km"] == 5.0


def _effort() -> dict:
    return {
        "schema_version": mod.EFFORT_SCHEMA,
        "status": mod.EFFORT_STATUS,
        "cohort_unit_ids": list(mod.UNITS),
        "protocol_source_identity": "SYNTHETIC_FIXED_PROTOCOL",
        "unit_effort": {
            unit: {
                "visits_per_candidate": 2,
                "search_minutes_per_visit": 20,
                "observer_count": 1,
            }
            for unit in mod.UNITS
        },
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used_to_set_effort": False,
        "candidate_identity_used_to_set_effort": False,
        "arm_specific_effort_allowed": False,
        "movement_constraint_used_to_set_effort": False,
        "post_outcome_effort_edits_allowed": False,
    }


def test_effort_protocol_rejects_outcome_informed_or_arm_specific_values() -> None:
    value = _effort()
    value["field_outcomes_used_to_set_effort"] = True
    with pytest.raises(ValueError):
        mod.validate_effort_protocol(value)
    value = _effort()
    value["arm_specific_effort_allowed"] = True
    with pytest.raises(ValueError):
        mod.validate_effort_protocol(value)


def test_live_derivation_fails_closed_on_movement_provider_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    private = tmp_path / "private"
    effort_path = tmp_path / "effort.json"
    effort_path.write_text(json.dumps(_effort()), encoding="utf-8")
    for unit in mod.UNITS:
        path = private / unit / "candidate_frame_pre_field.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        _frame().to_csv(path, index=False)

    def fake_osm(*args, **kwargs):
        empty = pd.DataFrame(columns=["from_patch_id", "to_patch_id"])
        return empty, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {
            "provider": {"successful_area_count": 0, "failed_area_count": 1}
        }

    monkeypatch.setattr(mod, "build_osm_patch_reachability_edges", fake_osm)
    with pytest.raises(RuntimeError, match="provider unavailable"):
        mod.derive_operational_capacity_profile(
            private,
            effort_path,
            max_network_transition_km=5.0,
            out_json=tmp_path / "capacity.json",
            repo_root=repo,
        )
