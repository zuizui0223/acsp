from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pytest

import research.run_cirsium_fresh_sentinel_freeze_v1 as entry
from research.cirsium_fresh_sentinel_paths_v1 import (
    CANONICAL_ANALYSIS_PLAN_REPO_PATH,
    CANONICAL_CANDIDATE_RECEIPT_REPO_PATH,
    CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH,
    CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH,
    CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH,
    CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH,
    CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH,
)
from research.freeze_cirsium_fresh_sentinel_movement_constraint_v1 import build_movement_constraint
from research.verify_cirsium_fresh_sentinel_public_freeze_pin_v1 import (
    VERIFIED_STATUS,
    verify_public_freeze_pin,
)


def _public_receipt(
    *,
    effort_pin_commit: str = "effort-pin",
    movement_pin_commit: str = "movement-pin",
    effort_sha256: str = "e" * 64,
    movement_sha256: str = "a" * 64,
) -> dict:
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
        "canonical_receipt_repo_path": CANONICAL_CANDIDATE_RECEIPT_REPO_PATH,
        "canonical_field_schedule_receipt_repo_path": CANONICAL_FIELD_SCHEDULE_RECEIPT_REPO_PATH,
        "field_evaluation_contract": CANONICAL_FIELD_EVALUATION_CONTRACT_REPO_PATH,
        "analysis_plan": CANONICAL_ANALYSIS_PLAN_REPO_PATH,
        "field_log_template": CANONICAL_FIELD_LOG_TEMPLATE_REPO_PATH,
        "public_safe_to_commit": True,
        "pre_geometry_standardized_effort_pin_commit": effort_pin_commit,
        "pre_geometry_standardized_effort_sha256": effort_sha256,
        "pre_geometry_movement_constraint_pin_commit": movement_pin_commit,
        "pre_geometry_movement_constraint_sha256": movement_sha256,
        "pre_geometry_protocol_pins_verified_before_private_execution": True,
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
    monkeypatch.setattr(
        entry,
        "verify_standardized_effort_pin",
        lambda *a, **k: {"pin_commit": "effort-pin", "protocol_sha256": "e" * 64},
    )
    monkeypatch.setattr(
        entry,
        "verify_movement_constraint_pin",
        lambda *a, **k: {"pin_commit": "movement-pin", "protocol_sha256": "a" * 64},
    )
    result = entry.run_full_pre_field_freeze(
        bundle,
        private,
        Path(CANONICAL_CANDIDATE_RECEIPT_REPO_PATH),
        repo_root=repo,
    )
    assert calls == ["private", "public"]
    assert result["status"] == entry.ENTRYPOINT_STATUS
    assert result["outcome_opening_authorized"] is False
    assert result["public_receipt_repo_path"] == CANONICAL_CANDIDATE_RECEIPT_REPO_PATH
    written = json.loads((repo / result["public_receipt_repo_path"]).read_text())
    assert written["outcome_opening_authorized_by_generation_alone"] is False
    assert written["public_receipt_commit_required_before_outcome_opening"] is True
    assert written["pre_geometry_standardized_effort_pin_commit"] == "effort-pin"
    assert written["pre_geometry_movement_constraint_pin_commit"] == "movement-pin"
    assert written["pre_geometry_protocol_pins_verified_before_private_execution"] is True


def test_single_entry_rejects_missing_pregeometry_pin_before_private_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    bundle = tmp_path / "bundle.geojson"
    bundle.write_text("{}", encoding="utf-8")
    touched = False

    monkeypatch.setattr(
        entry,
        "verify_standardized_effort_pin",
        lambda *a, **k: (_ for _ in ()).throw(ValueError("effort pin missing")),
    )

    def should_not_run(*args, **kwargs):
        nonlocal touched
        touched = True
        raise AssertionError("private execution must not start before protocol pins")

    monkeypatch.setattr(entry, "run_private_pre_field_pipeline", should_not_run)
    with pytest.raises(ValueError, match="effort pin missing"):
        entry.run_full_pre_field_freeze(
            bundle,
            tmp_path / "private",
            Path(CANONICAL_CANDIDATE_RECEIPT_REPO_PATH),
            repo_root=repo,
        )
    assert touched is False


def test_single_entry_rejects_existing_public_receipt_before_private_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    (repo / "validation").mkdir(parents=True)
    existing = repo / CANONICAL_CANDIDATE_RECEIPT_REPO_PATH
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


def test_single_entry_rejects_alternate_public_receipt_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    bundle = tmp_path / "bundle.geojson"
    bundle.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="canonical repo path"):
        entry.run_full_pre_field_freeze(
            bundle,
            tmp_path / "private",
            Path("validation/alternate-freeze.json"),
            repo_root=repo,
        )


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def _init_repo(repo: Path) -> None:
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "ACSP test")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _effort_protocol() -> dict:
    units = ["CIR02", "CIR06", "CIR12", "CIR13"]
    return {
        "schema_version": "cirsium-fresh-sentinel-standardized-effort-protocol-v1",
        "status": "PRE_OUTCOME_STANDARDIZED_EFFORT_PROTOCOL_FROZEN",
        "cohort_unit_ids": units,
        "protocol_source_identity": "ACSP_CIRSIUM_FIXED_TIMED_SEARCH_3X30MIN_1OBSERVER_V1",
        "unit_effort": {
            unit: {
                "visits_per_candidate": 3,
                "search_minutes_per_visit": 30.0,
                "observer_count": 1,
            }
            for unit in units
        },
        "prospective_field_outcomes_opened": False,
        "field_outcomes_used_to_set_effort": False,
        "candidate_identity_used_to_set_effort": False,
        "arm_specific_effort_allowed": False,
        "movement_constraint_used_to_set_effort": False,
        "post_outcome_effort_edits_allowed": False,
    }


def _commit_pregeometry_protocols(repo: Path) -> tuple[str, str, str]:
    effort = repo / CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH
    movement = repo / CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH
    effort.parent.mkdir(parents=True, exist_ok=True)
    effort.write_text(json.dumps(_effort_protocol(), sort_keys=True) + "\n", encoding="utf-8")
    movement.write_text(json.dumps(build_movement_constraint(), sort_keys=True) + "\n", encoding="utf-8")
    _git(repo, "add", CANONICAL_STANDARDIZED_EFFORT_PROTOCOL_REPO_PATH, CANONICAL_MOVEMENT_CONSTRAINT_REPO_PATH)
    _git(repo, "commit", "-m", "Pin pre-geometry protocols")
    return _git(repo, "rev-parse", "HEAD"), _sha256(effort), _sha256(movement)


def _commit_initial_receipt(repo: Path) -> tuple[Path, str]:
    protocol_pin, effort_sha, movement_sha = _commit_pregeometry_protocols(repo)
    receipt = repo / CANONICAL_CANDIDATE_RECEIPT_REPO_PATH
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(
        json.dumps(
            _public_receipt(
                effort_pin_commit=protocol_pin,
                movement_pin_commit=protocol_pin,
                effort_sha256=effort_sha,
                movement_sha256=movement_sha,
            ),
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    _git(repo, "add", CANONICAL_CANDIDATE_RECEIPT_REPO_PATH)
    _git(repo, "commit", "-m", "Pin public fresh sentinel freeze")
    return receipt, _git(repo, "rev-parse", "HEAD")


def test_pin_verifier_requires_actual_commit_and_allows_descendant_head(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    protocol_pin, effort_sha, movement_sha = _commit_pregeometry_protocols(repo)
    receipt = repo / CANONICAL_CANDIDATE_RECEIPT_REPO_PATH
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(
        json.dumps(
            _public_receipt(
                effort_pin_commit=protocol_pin,
                movement_pin_commit=protocol_pin,
                effort_sha256=effort_sha,
                movement_sha256=movement_sha,
            ),
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="not tracked"):
        verify_public_freeze_pin(receipt, repo_root=repo)

    _git(repo, "add", CANONICAL_CANDIDATE_RECEIPT_REPO_PATH)
    _git(repo, "commit", "-m", "Pin public fresh sentinel freeze")
    pin = _git(repo, "rev-parse", "HEAD")
    verified = verify_public_freeze_pin(receipt, repo_root=repo, expected_pin_commit=pin)
    assert verified["status"] == VERIFIED_STATUS
    assert verified["pin_commit"] == pin
    assert verified["pin_rule"].startswith("first commit")
    assert verified["pre_field_prescription_pin_gate_satisfied"] is True
    assert verified["outcome_opening_gate_satisfied"] is False
    assert "allocation/effort schedule" in verified["remaining_pre_outcome_gate"]
    assert verified["prospective_field_outcomes_opened"] is False

    (repo / "README.md").write_text("later non-receipt change\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "Later descendant commit")
    descendant = verify_public_freeze_pin(receipt, repo_root=repo, expected_pin_commit=pin)
    assert descendant["pin_commit"] == pin
    assert descendant["verified_head"] != pin
    assert descendant["outcome_opening_gate_satisfied"] is False


def test_pin_verifier_rejects_receipt_with_false_pregeometry_hash_provenance(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    protocol_pin, effort_sha, movement_sha = _commit_pregeometry_protocols(repo)
    receipt = repo / CANONICAL_CANDIDATE_RECEIPT_REPO_PATH
    receipt.write_text(
        json.dumps(
            _public_receipt(
                effort_pin_commit=protocol_pin,
                movement_pin_commit=protocol_pin,
                effort_sha256="0" * 64,
                movement_sha256=movement_sha,
            ),
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    _git(repo, "add", CANONICAL_CANDIDATE_RECEIPT_REPO_PATH)
    _git(repo, "commit", "-m", "Attempt false pre-geometry provenance")
    with pytest.raises(ValueError, match="standardized-effort hash"):
        verify_public_freeze_pin(receipt, repo_root=repo)


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
    _git(repo, "add", CANONICAL_CANDIDATE_RECEIPT_REPO_PATH)
    _git(repo, "commit", "-m", "Attempt to re-pin changed receipt")
    with pytest.raises(ValueError, match="first-add"):
        verify_public_freeze_pin(receipt, repo_root=repo)
    with pytest.raises(ValueError):
        verify_public_freeze_pin(receipt, repo_root=repo, expected_pin_commit=original_pin)
