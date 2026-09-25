from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from research.cirsium_fresh_sentinel_paths_v1 import CANONICAL_RANGE_SECTOR_PROVENANCE_REPO_PATH
from research.verify_cirsium_fresh_sentinel_range_sector_provenance_pin_v1 import (
    EXPECTED,
    EXPECTED_UNITS,
    VERIFIED_STATUS,
    validate_range_sector_provenance,
    verify_range_sector_provenance_pin,
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _value() -> dict:
    units = {}
    for unit in EXPECTED_UNITS:
        expected = EXPECTED[unit]
        p02 = bool(expected["p02_required"])
        units[unit] = {
            "species_binomial": expected["species_binomial"],
            "aza3_slot_id": expected["aza3_slot_id"],
            "range_sector_label": expected["range_sector_label"],
            "freeze_status": "FROZEN_FOR_FIELD_COLLECTION",
            "current_occurrence_supported": True,
            "permission_gate_satisfied": True,
            "target_locality_id": f"{unit}-LOCALITY",
            "private_exact_site_record_exists": True,
            "range_sector_geometry_may_now_be_materialized": True,
            "p02_first_validated_wild_population_required": p02,
            "p02_first_validated_wild_population_link_satisfied": p02,
        }
    return {
        "schema_version": "cirsium-fresh-sentinel-range-sector-provenance-v1",
        "status": "PRE_GEOMETRY_RANGE_SECTOR_PROVENANCE_FROZEN",
        "cohort_unit_ids": list(EXPECTED_UNITS),
        "aza3_exact_site_contract_version": "chapter3_exact_site_freeze_v8",
        "upstream_snapshot_commit": "a" * 40,
        "unit_provenance": units,
        "exact_coordinates_included": False,
        "sensitive_access_instructions_included": False,
        "prospective_acsp_field_outcomes_opened": False,
        "acsp_field_outcomes_used_to_define_sector": False,
        "post_geometry_edits_allowed": False,
        "post_outcome_edits_allowed": False,
        "public_safe_to_commit": True,
    }


def _init_repo(repo: Path) -> None:
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "ACSP test")


def test_valid_provenance_requires_p02_link_for_focal_units() -> None:
    value = _value()
    validate_range_sector_provenance(value)
    value["unit_provenance"]["CIR12"]["p02_first_validated_wild_population_link_satisfied"] = False
    with pytest.raises(ValueError, match="P02 dependency linkage"):
        validate_range_sector_provenance(value)


def test_provenance_rejects_unfrozen_exact_site() -> None:
    value = _value()
    value["unit_provenance"]["CIR02"]["freeze_status"] = "EVIDENCE_IN_PROGRESS"
    with pytest.raises(ValueError, match="not frozen for field collection"):
        validate_range_sector_provenance(value)


def test_provenance_rejects_missing_target_locality_id() -> None:
    value = _value()
    value["unit_provenance"]["CIR06"]["target_locality_id"] = ""
    with pytest.raises(ValueError, match="target_locality_id"):
        validate_range_sector_provenance(value)


def test_provenance_pin_is_first_add_immutable_and_precedes_candidate(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    path = repo / CANONICAL_RANGE_SECTOR_PROVENANCE_REPO_PATH
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(_value(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _git(repo, "add", CANONICAL_RANGE_SECTOR_PROVENANCE_REPO_PATH)
    _git(repo, "commit", "-m", "Pin range provenance")
    provenance_pin = _git(repo, "rev-parse", "HEAD")

    candidate = repo / "validation" / "candidate.json"
    candidate.write_text("{}\n", encoding="utf-8")
    _git(repo, "add", "validation/candidate.json")
    _git(repo, "commit", "-m", "Pin candidate")
    candidate_pin = _git(repo, "rev-parse", "HEAD")

    result = verify_range_sector_provenance_pin(
        path,
        repo_root=repo,
        expected_pin_commit=provenance_pin,
        must_be_ancestor_of=candidate_pin,
    )
    assert result["status"] == VERIFIED_STATUS
    assert result["range_sector_provenance_pin_gate_satisfied"] is True
    assert result["private_geometry_opened_by_verifier"] is False


def test_later_recommit_cannot_repin_range_provenance(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    path = repo / CANONICAL_RANGE_SECTOR_PROVENANCE_REPO_PATH
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(_value(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _git(repo, "add", CANONICAL_RANGE_SECTOR_PROVENANCE_REPO_PATH)
    _git(repo, "commit", "-m", "Pin range provenance")

    changed = _value()
    changed["unit_provenance"]["CIR02"]["target_locality_id"] = "CIR02-OTHER"
    path.write_text(json.dumps(changed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _git(repo, "add", CANONICAL_RANGE_SECTOR_PROVENANCE_REPO_PATH)
    _git(repo, "commit", "-m", "Attempt range provenance repin")

    with pytest.raises(ValueError, match="first-add"):
        verify_range_sector_provenance_pin(path, repo_root=repo)
