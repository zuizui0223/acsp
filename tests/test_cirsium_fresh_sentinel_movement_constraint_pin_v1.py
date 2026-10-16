from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from research.cirsium_fresh_sentinel_paths_v1 import CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH
from research.freeze_cirsium_fresh_sentinel_movement_constraint_v1 import (
    ALGORITHM_DERIVED_MAX_NETWORK_TRANSITION_KM,
    DERIVATION_IDENTITY,
    FROZEN_COARSE_COVERAGE_CELL_SIZE_M,
    build_movement_constraint,
    freeze_movement_constraint,
)
from research.verify_cirsium_fresh_sentinel_movement_constraint_pin_v1 import (
    VERIFIED_STATUS,
    verify_movement_constraint_pin,
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _init_repo(repo: Path) -> None:
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "ACSP test")


def test_movement_constraint_is_deterministic_outcome_blind_and_not_user_tuned() -> None:
    value = build_movement_constraint()
    assert value["status"] == "PRE_GEOMETRY_MOVEMENT_CONSTRAINT_FROZEN"
    assert value["movement_constraint_mode"] == "osm_weighted_transport_network"
    assert value["derivation_identity"] == DERIVATION_IDENTITY
    assert value["max_network_transition_km"] == ALGORITHM_DERIVED_MAX_NETWORK_TRANSITION_KM == 5.0
    assert value["derived_from_coarse_coverage_cell_size_m"] == FROZEN_COARSE_COVERAGE_CELL_SIZE_M == 5000.0
    assert value["user_declared_value"] is False
    assert value["private_range_sector_geometry_opened_when_declared"] is False
    assert value["candidate_identity_used_to_set_constraint"] is False
    assert value["prospective_field_outcomes_opened"] is False
    assert value["survey_days_input"] is False
    assert value["monetary_budget_input"] is False
    assert value["user_site_count_input"] is False


def test_freeze_requires_canonical_path_and_refuses_overwrite(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(ValueError, match="canonical repo path"):
        freeze_movement_constraint(
            out_json=Path("validation/alternate-movement.json"),
            repo_root=repo,
        )
    target = repo / CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH
    freeze_movement_constraint(repo_root=repo)
    assert target.is_file()
    with pytest.raises(ValueError, match="overwrite"):
        freeze_movement_constraint(repo_root=repo)


def test_pin_is_first_add_immutable_and_must_precede_candidate_pin(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    target = repo / CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(build_movement_constraint(), indent=2) + "\n", encoding="utf-8")
    _git(repo, "add", CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH)
    _git(repo, "commit", "-m", "Pin movement constraint")
    movement_pin = _git(repo, "rev-parse", "HEAD")

    candidate = repo / "validation" / "candidate.json"
    candidate.write_text("{}\n", encoding="utf-8")
    _git(repo, "add", "validation/candidate.json")
    _git(repo, "commit", "-m", "Pin candidate prescription")
    candidate_pin = _git(repo, "rev-parse", "HEAD")

    result = verify_movement_constraint_pin(
        target,
        repo_root=repo,
        expected_pin_commit=movement_pin,
        must_be_ancestor_of=candidate_pin,
    )
    assert result["status"] == VERIFIED_STATUS
    assert result["movement_constraint_pin_gate_satisfied"] is True
    assert result["pin_commit"] == movement_pin
    assert result["derivation_identity"] == DERIVATION_IDENTITY
    assert result["user_declared_value"] is False
    assert result["max_network_transition_km"] == 5.0


def test_same_commit_as_candidate_is_not_accepted_as_pre_geometry_pin(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    target = repo / CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(build_movement_constraint(), indent=2) + "\n", encoding="utf-8")
    candidate = repo / "validation" / "candidate.json"
    candidate.write_text("{}\n", encoding="utf-8")
    _git(repo, "add", "validation")
    _git(repo, "commit", "-m", "Attempt simultaneous movement and candidate pin")
    same_commit = _git(repo, "rev-parse", "HEAD")

    with pytest.raises(ValueError, match="earlier commit"):
        verify_movement_constraint_pin(
            target,
            repo_root=repo,
            must_be_ancestor_of=same_commit,
        )


def test_clean_recommit_cannot_repin_changed_movement_constraint(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    target = repo / CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(build_movement_constraint(), indent=2) + "\n", encoding="utf-8")
    _git(repo, "add", CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH)
    _git(repo, "commit", "-m", "Pin movement constraint")

    # Keep the protocol semantically valid but alter its serialized bytes.
    # This reaches the first-add immutability guard rather than the semantic guard.
    changed = build_movement_constraint()
    target.write_text(json.dumps(changed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _git(repo, "add", CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH)
    _git(repo, "commit", "-m", "Attempt byte-only movement re-pin")
    with pytest.raises(ValueError, match="first-add"):
        verify_movement_constraint_pin(target, repo_root=repo)


def test_derivation_bytes_cannot_be_replaced_by_another_positive_value(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    target = repo / CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH
    target.parent.mkdir(parents=True)
    changed = build_movement_constraint()
    changed["max_network_transition_km"] = 6.0
    target.write_text(json.dumps(changed, indent=2) + "\n", encoding="utf-8")
    _git(repo, "add", CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH)
    _git(repo, "commit", "-m", "Invalid movement constraint")
    with pytest.raises(ValueError, match="deterministic frozen-scale derivation"):
        verify_movement_constraint_pin(target, repo_root=repo)
