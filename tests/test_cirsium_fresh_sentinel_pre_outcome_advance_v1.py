from __future__ import annotations

import json
from pathlib import Path

import pytest

import research.advance_cirsium_fresh_sentinel_pre_outcome_v1 as advance
from research.cirsium_fresh_sentinel_paths_v1 import (
    CANONICAL_CANDIDATE_RECEIPT_REPO_PATH,
    CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH,
    CANONICAL_OPERATIONAL_CAPACITY_PROFILE_REPO_PATH,
    CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH,
)


def _effort_pin() -> dict:
    return {
        "pin_commit": "effort-pin",
        "standardized_effort_protocol_pin_gate_satisfied": True,
    }


def _candidate_pin() -> dict:
    return {
        "pin_commit": "candidate-pin",
        "pre_field_prescription_pin_gate_satisfied": True,
    }


def _movement_pin(km: float = 5.0) -> dict:
    return {
        "pin_commit": "movement-pin",
        "movement_constraint_pin_gate_satisfied": True,
        "movement_constraint_mode": "osm_weighted_transport_network",
        "max_network_transition_km": km,
    }


def _stub_protocol_pins(repo: Path, monkeypatch: pytest.MonkeyPatch, *, movement_km: float = 5.0) -> None:
    movement = repo / CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH
    movement.parent.mkdir(parents=True, exist_ok=True)
    movement.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(advance, "verify_standardized_effort_pin", lambda *a, **k: _effort_pin())
    monkeypatch.setattr(advance, "verify_movement_constraint_pin", lambda *a, **k: _movement_pin(movement_km))


def test_effort_pin_is_checked_before_private_geometry_is_processed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    private = tmp_path / "private"
    bundle = tmp_path / "bundle.geojson"
    bundle.write_text("{}", encoding="utf-8")
    touched = False

    def fail_effort(*args, **kwargs):
        raise ValueError("effort pin missing")

    def should_not_run(*args, **kwargs):
        nonlocal touched
        touched = True
        raise AssertionError("private geometry must not be processed")

    monkeypatch.setattr(advance, "verify_standardized_effort_pin", fail_effort)
    monkeypatch.setattr(advance, "run_full_pre_field_freeze", should_not_run)

    with pytest.raises(ValueError, match="effort pin missing"):
        advance.advance_pre_outcome_pipeline(
            private,
            max_network_transition_km=5.0,
            bundle_geojson=bundle,
            repo_root=repo,
        )
    assert touched is False


def test_missing_movement_constraint_blocks_before_private_geometry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    touched = False
    monkeypatch.setattr(advance, "verify_standardized_effort_pin", lambda *a, **k: _effort_pin())

    def should_not_run(*args, **kwargs):
        nonlocal touched
        touched = True
        raise AssertionError("private geometry must not be processed")

    monkeypatch.setattr(advance, "run_full_pre_field_freeze", should_not_run)
    result = advance.advance_pre_outcome_pipeline(
        tmp_path / "private",
        repo_root=repo,
    )
    assert result["status"] == "BLOCKED_MOVEMENT_CONSTRAINT_DECLARATION"
    assert result["outcome_opening_gate_satisfied"] is False
    assert touched is False


def test_movement_declaration_stops_at_commit_gate_before_geometry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    bundle = tmp_path / "bundle.geojson"
    bundle.write_text("{}", encoding="utf-8")
    touched = False
    monkeypatch.setattr(advance, "verify_standardized_effort_pin", lambda *a, **k: _effort_pin())

    def should_not_run(*args, **kwargs):
        nonlocal touched
        touched = True
        raise AssertionError("private geometry must wait for movement pin")

    monkeypatch.setattr(advance, "run_full_pre_field_freeze", should_not_run)
    result = advance.advance_pre_outcome_pipeline(
        tmp_path / "private",
        max_network_transition_km=5.0,
        bundle_geojson=bundle,
        repo_root=repo,
    )
    assert result["status"] == "MOVEMENT_CONSTRAINT_READY_FOR_COMMIT"
    assert result["public_paths_to_commit"] == [CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH]
    assert (repo / CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH).is_file()
    assert touched is False


def test_missing_bundle_reports_only_external_geometry_blocker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _stub_protocol_pins(repo, monkeypatch)

    result = advance.advance_pre_outcome_pipeline(
        tmp_path / "private",
        max_network_transition_km=5.0,
        repo_root=repo,
    )
    assert result["status"] == "BLOCKED_PRIVATE_RANGE_SECTOR_GEOMETRY"
    assert result["prospective_field_outcomes_opened"] is False
    assert result["standardized_effort_protocol_pin_commit"] == "effort-pin"


def test_new_private_freeze_stops_at_candidate_receipt_commit_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    private = tmp_path / "private"
    bundle = tmp_path / "bundle.geojson"
    bundle.write_text("{}", encoding="utf-8")
    _stub_protocol_pins(repo, monkeypatch)

    def fake_freeze(bundle_path, private_root, candidate_path, *, repo_root):
        private_root.mkdir()
        candidate_path.parent.mkdir(parents=True)
        candidate_path.write_text("{}\n", encoding="utf-8")
        return {"status": "PRIVATE_AND_PUBLIC_HASH_FREEZE_GENERATED_AWAITING_COMMIT"}

    monkeypatch.setattr(advance, "run_full_pre_field_freeze", fake_freeze)
    result = advance.advance_pre_outcome_pipeline(
        private,
        max_network_transition_km=5.0,
        bundle_geojson=bundle,
        repo_root=repo,
    )
    assert result["status"] == "CANDIDATE_RECEIPT_READY_FOR_COMMIT"
    assert result["public_paths_to_commit"] == [CANONICAL_CANDIDATE_RECEIPT_REPO_PATH]
    assert result["outcome_opening_gate_satisfied"] is False


def test_unpinned_candidate_receipt_blocks_capacity_derivation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    private = tmp_path / "private"
    private.mkdir()
    candidate = repo / CANONICAL_CANDIDATE_RECEIPT_REPO_PATH
    candidate.parent.mkdir(parents=True)
    candidate.write_text("{}\n", encoding="utf-8")
    called = False

    _stub_protocol_pins(repo, monkeypatch)
    monkeypatch.setattr(
        advance,
        "verify_public_freeze_pin",
        lambda *a, **k: (_ for _ in ()).throw(ValueError("not committed")),
    )

    def should_not_derive(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("capacity must wait for candidate pin")

    monkeypatch.setattr(advance, "derive_operational_capacity_profile", should_not_derive)
    result = advance.advance_pre_outcome_pipeline(
        private,
        max_network_transition_km=5.0,
        repo_root=repo,
    )
    assert result["status"] == "CANDIDATE_RECEIPT_PIN_NOT_SATISFIED"
    assert called is False


def test_existing_capacity_freezes_the_only_movement_tuning_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    private = tmp_path / "private"
    private.mkdir()
    candidate = repo / CANONICAL_CANDIDATE_RECEIPT_REPO_PATH
    candidate.parent.mkdir(parents=True)
    candidate.write_text("{}\n", encoding="utf-8")
    capacity = repo / CANONICAL_OPERATIONAL_CAPACITY_PROFILE_REPO_PATH
    capacity.write_text(json.dumps({"max_network_transition_km": 4.0}), encoding="utf-8")

    _stub_protocol_pins(repo, monkeypatch)
    monkeypatch.setattr(advance, "verify_public_freeze_pin", lambda *a, **k: _candidate_pin())

    with pytest.raises(ValueError, match="differs from the already-frozen"):
        advance.advance_pre_outcome_pipeline(
            private,
            max_network_transition_km=5.0,
            repo_root=repo,
        )


def test_pinned_candidate_advances_to_commit_ready_schedule_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    private = tmp_path / "private"
    private.mkdir()
    candidate = repo / CANONICAL_CANDIDATE_RECEIPT_REPO_PATH
    candidate.parent.mkdir(parents=True)
    candidate.write_text("{}\n", encoding="utf-8")

    _stub_protocol_pins(repo, monkeypatch)
    monkeypatch.setattr(advance, "verify_public_freeze_pin", lambda *a, **k: _candidate_pin())

    def fake_capacity(private_root, effort_path, *, max_network_transition_km, out_json, repo_root):
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(
            json.dumps({"max_network_transition_km": max_network_transition_km}) + "\n",
            encoding="utf-8",
        )
        return {"status": "PRE_OUTCOME_OPERATIONAL_CAPACITY_FROZEN"}

    def fake_schedule(*args, **kwargs):
        out_path = args[5]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("{}\n", encoding="utf-8")
        return {"status": "PRIVATE_FIELD_SCHEDULE_BUILT_AND_VALIDATED"}

    monkeypatch.setattr(advance, "derive_operational_capacity_profile", fake_capacity)
    monkeypatch.setattr(advance, "build_private_field_schedule", fake_schedule)
    monkeypatch.setattr(
        advance,
        "build_public_field_schedule_receipt",
        lambda *a, **k: {"status": "PUBLIC_FIELD_ALLOCATION_EFFORT_SCHEDULE_READY_FOR_COMMIT"},
    )

    result = advance.advance_pre_outcome_pipeline(
        private,
        max_network_transition_km=5.0,
        repo_root=repo,
    )
    assert result["status"] == "FIELD_SCHEDULE_RECEIPT_READY_FOR_COMMIT"
    assert result["public_paths_to_commit"] == [
        CANONICAL_OPERATIONAL_CAPACITY_PROFILE_REPO_PATH,
        CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH,
    ]
    assert result["outcome_opening_gate_satisfied"] is False
