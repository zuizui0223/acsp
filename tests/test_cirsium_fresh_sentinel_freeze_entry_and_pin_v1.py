from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

import research.run_cirsium_fresh_sentinel_freeze_v1 as entry
from research.verify_cirsium_fresh_sentinel_public_freeze_pin_v1 import (
    VERIFIED_STATUS,
    verify_public_freeze_pin,
)


def _public_receipt() -> dict:
    return {
        "schema_version": "cirsium-fresh-sentinel-public-pre-field-freeze-v1",
        "status": "PUBLIC_HASH_FREEZE_READY_FOR_COMMIT",
        "coordinate_bearing_data_included": False,
        "private_paths_included": False,
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used_to_choose_or_rank": False,
        "outcome_opening_authorized_by_generation_alone": False,
        "public_receipt_commit_required_before_outcome_opening": True,
        "public_receipt_commit_verified": False,
        "public_safe_to_commit": True,
    }


def test_single_entry_runs_private_then_writes_commit_ready_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    bundle = tmp_path / "private-range-sectors.geojson"
    bundle.write_text("{}", encoding="utf-8")
    private = tmp_path / "private-freeze"
    calls: list[str] = []

    def fake_private(bundle_path: Path, private_root: Path) -> dict:
        calls.append("private")
        assert bundle_path == bundle.resolve()
        assert private_root == private.resolve()
        private_root.mkdir()
        return {
            "status": "ALL_FOUR_PRE_FIELD_METHOD_AND_COMPARATORS_FROZEN",
            "ready_for_public_hash_receipt_freeze": True,
            "ready_for_future_prospective_outcome_opening": False,
        }

    def fake_public(private_root: Path) -> dict:
        calls.append("public")
        assert private_root == private.resolve()
        return _public_receipt()

    monkeypatch.setattr(entry, "run_private_pre_field_pipeline", fake_private)
    monkeypatch.setattr(entry, "build_public_freeze_receipt", fake_public)
    result = entry.run_full_pre_field_freeze(
        bundle,
        private,
        Path("validation/fresh-public-freeze.json"),
        repo_root=repo,
    )
    assert calls == ["private", "public"]
    assert result["status"] == entry.ENTRYPOINT_STATUS
    assert result["outcome_opening_authorized"] is False
    assert result["public_receipt_repo_path"] == "validation/fresh-public-freeze.json"
    written = json.loads((repo / result["public_receipt_repo_path"]).read_text())
    assert written["outcome_opening_authorized_by_generation_alone"] is False
    assert written["public_receipt_commit_required_before_outcome_opening"] is True


def test_single_entry_rejects_existing_public_receipt_before_private_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    (repo / "validation").mkdir(parents=True)
    existing = repo / "validation" / "freeze.json"
    existing.write_text("{}", encoding="utf-8")
    bundle = tmp_path / "bundle.geojson"
    bundle.write_text("{}", encoding="utf-8")
    called = False

    def should_not_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("private execution must not start")

    monkeypatch.setattr(entry, "run_private_pre_field_pipeline", should_not_run)
    with pytest.raises(ValueError, match="overwrite"):
        entry.run_full_pre_field_freeze(bundle, tmp_path / "private", existing, repo_root=repo)
    assert called is False


def test_single_entry_requires_public_receipt_under_validation(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    bundle = tmp_path / "bundle.geojson"
    bundle.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="validation"):
        entry.run_full_pre_field_freeze(
            bundle,
            tmp_path / "private",
            Path("other/freeze.json"),
            repo_root=repo,
        )


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def _init_repo(repo: Path) -> None:
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "ACSP test")


def _commit_initial_receipt(repo: Path) -> tuple[Path, str]:
    receipt = repo / "validation" / "fresh-freeze.json"
    receipt.parent.mkdir()
    receipt.write_text(json.dumps(_public_receipt(), sort_keys=True) + "\n", encoding="utf-8")
    _git(repo, "add", "validation/fresh-freeze.json")
    _git(repo, "commit", "-m", "Pin public fresh sentinel freeze")
    return receipt, _git(repo, "rev-parse", "HEAD")


def test_pin_verifier_requires_actual_commit_and_allows_descendant_head(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    receipt = repo / "validation" / "fresh-freeze.json"
    receipt.parent.mkdir()
    receipt.write_text(json.dumps(_public_receipt(), sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="not tracked"):
        verify_public_freeze_pin(receipt, repo_root=repo)

    _git(repo, "add", "validation/fresh-freeze.json")
    _git(repo, "commit", "-m", "Pin public fresh sentinel freeze")
    pin = _git(repo, "rev-parse", "HEAD")
    verified = verify_public_freeze_pin(receipt, repo_root=repo, expected_pin_commit=pin)
    assert verified["status"] == VERIFIED_STATUS
    assert verified["pin_commit"] == pin
    assert verified["pin_rule"].startswith("first commit")
    assert verified["outcome_opening_gate_satisfied"] is True
    assert verified["prospective_field_outcomes_opened"] is False

    (repo / "README.md").write_text("later non-receipt change\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "Later descendant commit")
    descendant = verify_public_freeze_pin(receipt, repo_root=repo, expected_pin_commit=pin)
    assert descendant["pin_commit"] == pin
    assert descendant["verified_head"] != pin


def test_pin_verifier_rejects_uncommitted_receipt_change(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    receipt, _ = _commit_initial_receipt(repo)
    receipt.write_text(json.dumps({**_public_receipt(), "tampered": True}, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="uncommitted"):
        verify_public_freeze_pin(receipt, repo_root=repo)


def test_pin_verifier_rejects_clean_but_recommitted_receipt_change(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    receipt, original_pin = _commit_initial_receipt(repo)
    receipt.write_text(json.dumps({**_public_receipt(), "tampered_after_pin": True}, sort_keys=True) + "\n", encoding="utf-8")
    _git(repo, "add", "validation/fresh-freeze.json")
    _git(repo, "commit", "-m", "Attempt to re-pin changed receipt")
    with pytest.raises(ValueError, match="first-add"):
        verify_public_freeze_pin(receipt, repo_root=repo)
    with pytest.raises(ValueError):
        verify_public_freeze_pin(receipt, repo_root=repo, expected_pin_commit=original_pin)
