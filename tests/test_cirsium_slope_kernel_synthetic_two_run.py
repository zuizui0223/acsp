from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from research.audit_cirsium_slope_kernel_synthetic_two_run import (
    STAGES, _fingerprint, audit_synthetic_slope, validate_contract,
)
from research.compare_cirsium_synthetic_slope_kernel_runs import (
    compare_public_slope_kernel_runs,
)


def _two_runs(tmp_path: Path):
    a = audit_synthetic_slope(tmp_path / "a" / "source.tif")
    b = audit_synthetic_slope(tmp_path / "b" / "source.tif")
    return a, b


def test_independent_synthetic_files_are_byte_identical_and_match_production(tmp_path: Path):
    validate_contract()
    a, b = _two_runs(tmp_path)
    assert a["source_dem_byte_sha256"] == b["source_dem_byte_sha256"]
    assert a["stage_count"] == len(STAGES) == 9
    assert a["stage_sha256"] == b["stage_sha256"]
    assert a["synthetic_stage_source_compared_to_production"] is True
    assert a["replay_same_process_exact"] is True
    compared = compare_public_slope_kernel_runs(a, b)
    assert compared["status"] == "ALL_SYNTHETIC_KERNEL_STAGES_REPRODUCED_ACROSS_TWO_RUNNERS"
    assert compared["first_differing_stage"] is None
    assert all(compared["stages_equal"].values())
    assert compared["original_real_CIR02_slope_cause_identified"] is False
    assert "candidate_cell_id" not in json.dumps(compared)
    assert "latitude" not in json.dumps(compared)


def test_injected_intermediate_slope_hash_change_is_reported_at_first_stage(tmp_path: Path):
    a, b = _two_runs(tmp_path)
    b["stage_sha256"]["gradient_dx"] = "0" * 64
    result = compare_public_slope_kernel_runs(a, b)
    assert result["status"] == "SYNTHETIC_KERNEL_STAGE_DIVERGENCE_DETECTED"
    assert result["first_differing_stage"] == "gradient_dx"
    assert result["stages_equal"]["slope100"] is True
    assert result["original_real_CIR02_slope_cause_identified"] is False


def test_synthetic_source_byte_mismatch_aborts_numeric_inference(tmp_path: Path):
    a, b = _two_runs(tmp_path)
    b["source_dem_byte_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="input DEM bytes/pixels differ"):
        compare_public_slope_kernel_runs(a, b)


@pytest.mark.parametrize("mode", ["missing_stage", "field_open", "causal_promotion", "private_dem"])
def test_public_stage_cohort_and_claims_fail_closed(tmp_path: Path, mode: str):
    a, b = _two_runs(tmp_path)
    if mode == "missing_stage":
        b["stage_sha256"].pop("slope100")
    elif mode == "field_open":
        b["prospective_field_outcomes_opened"] = True
    elif mode == "causal_promotion":
        b["real_CIR02_root_cause_identified"] = True
    else:
        b["private_dem_or_candidate_locations_opened"] = True
    with pytest.raises(ValueError):
        compare_public_slope_kernel_runs(a, b)
