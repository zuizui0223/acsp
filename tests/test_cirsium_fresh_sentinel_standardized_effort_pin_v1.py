from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from research.cirsium_fresh_sentinel_paths_v1 import (
    CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH,
)
from research.verify_cirsium_fresh_sentinel_standardized_effort_pin_v1 import (
    EXPECTED_EFFORT,
    EXPECTED_SOURCE_IDENTITY,
    VERIFIED_STATUS,
    verify_standardized_effort_pin,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH


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


def _copy_protocol(repo: Path) -> Path:
    target = repo / CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(SOURCE.read_bytes())
    return target


def test_standardized_effort_pin_accepts_first_add_immutable_protocol(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    protocol = _copy_protocol(repo)
    _git(repo, "add", CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH)
    _git(repo, "commit", "-m", "Pin standardized effort")
    pin = _git(repo, "rev-parse", "HEAD")

    result = verify_standardized_effort_pin(
        protocol,
        repo_root=repo,
        expected_pin_commit=pin,
    )
    assert result["status"] == VERIFIED_STATUS
    assert result["pin_commit"] == pin
    assert result["standardized_effort_protocol_pin_gate_satisfied"] is True
    assert result["prospective_field_outcomes_opened"] is False
    assert result["private_candidate_geometry_opened_by_verifier"] is False

    value = json.loads(protocol.read_text(encoding="utf-8"))
    assert value["protocol_source_identity"] == EXPECTED_SOURCE_IDENTITY
    assert all(row == EXPECTED_EFFORT for row in value["unit_effort"].values())


def test_standardized_effort_pin_rejects_clean_recommit_of_changed_values(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    protocol = _copy_protocol(repo)
    _git(repo, "add", CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH)
    _git(repo, "commit", "-m", "Pin standardized effort")

    value = json.loads(protocol.read_text(encoding="utf-8"))
    value["unit_effort"]["CIR12"]["search_minutes_per_visit"] = 45.0
    protocol.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _git(repo, "add", CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH)
    _git(repo, "commit", "-m", "Attempt effort re-pin")

    with pytest.raises(ValueError):
        verify_standardized_effort_pin(protocol, repo_root=repo)
