"""Safety and provenance checks for the original, synthetic-only native V4 preflight."""
from __future__ import annotations
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "validation/coverage_then_fine_structure_fresh_sentinel_v2_cir02_numpy24_x86v4_preflight_result_v1.json"

@pytest.fixture
def evidence():
    return json.loads(RESULT.read_text(encoding="utf-8"))


def test_original_source_identity_and_successful_workflow(evidence):
    assert evidence["status"] == "NATIVE_CPU_ONLY_PREFLIGHT_COMPLETED_INELIGIBLE"
    assert evidence["source_workflow"]["run_id"] == 38493683528
    assert evidence["source_workflow"]["conclusion"] == "success"
    assert evidence["source_workflow"]["attempt"] == 1
    assert evidence["source_workflow"]["job_id"] == 115624489337
    assert evidence["source_workflow"]["head_sha"] == "162aa3614242a39faf6e1681b8266c768c334401"
    assert evidence["source_artifact"]["id"] == 11863436251
    assert evidence["source_artifact"]["zip_sha256"] == "c786d07816cc22290db0f72afa4d633a3d63919b78ab1de00aeeea5941b27839"


def test_original_software_and_source_world_are_unchanged(evidence):
    r = evidence["original_native_result"]
    assert r["status"] == "NATIVE_CPU_ONLY_PREFLIGHT_COMPLETE"
    assert r["schema_version"] == "cirsium-numpy24-x86-v4-dispatch-preflight-result-v1"
    assert r["source_kind"] == "SYNTHETIC_CPU_ONLY_NO_GSI"
    assert r["real_original_gsi_input_used"] is False
    assert r["intervention_flag"] == "X86_V4"
    assert r["same_worker_fresh_processes"] is True
    assert r["same_mode_repeats_exact"] is True


def test_same_binary_and_synthetic_data_for_both_modes(evidence):
    m = evidence["original_native_result"]["modes"]
    assert set(m) == {"original", "x86_v4_disabled"}
    a, b = m["original"], m["x86_v4_disabled"]
    assert a["python"] == b["python"] == "3.11.17"
    assert a["numpy"] == b["numpy"] == "2.4.6"
    for key in ("binary_sha256", "source_sha256"):
        assert a[key] == b[key]
        assert len(a[key]) == 64
    assert a["arctan_exact_sha256"] == b["arctan_exact_sha256"]


def test_non_switch_is_not_a_negative_causal_effect(evidence):
    r = evidence["original_native_result"]
    assert r["modes"]["original"]["arctan_loop"] == "baseline(X86_V2)"
    assert r["modes"]["x86_v4_disabled"]["arctan_loop"] == "baseline(X86_V2)"
    assert r["comparison"] == {
        "eligible_for_separately_frozen_original_source_trial": False,
        "loop_changed": False,
        "readout": "NATIVE_WORKER_NOT_RUNNING_X86_V4",
        "synthetic_arctan_exact_equal": True,
    }
    assert evidence["interpretation"]["cpu_dispatch_causal_effect_established"] is False
    assert evidence["interpretation"]["switch_intervention_succeeded"] is False


def test_fail_closed_next_gate_prevents_hardware_hunting(evidence):
    i = evidence["interpretation"]
    assert i["run_was_synthetic_only"] is True
    assert i["new_real_GSI_acquisition_triggered"] is False
    assert i["no_positive_outcome_based_hardware_resampling"] is True
    assert i["future_real_trial_eligible_from_this_result"] is False
    assert i["original_PR271_AVX512F_result_untouched"] is True
    assert i["existing_cross_worker_arctan_difference_retained"] is True
    assert i["main_validated_product_changed"] is False


def test_no_unsupported_ecology_or_private_sites(evidence):
    i = evidence["interpretation"]
    for key in ("field_efficiency_validated", "occupancy_inferred", "rank_swap_magnitude_known",
                "all_177_original_GSI_chunks_numerically_reproduced", "historical_CIR02_numeric_cause_proven"):
        assert i[key] is False
    raw = RESULT.read_text(encoding="utf-8")
    for forbidden in ("candidate_cell_id", "longitude", "latitude", "private_dem", "private_raster", "private-cell-", "source_mosaic_path"):
        assert forbidden not in raw


def test_frozen_protocol_not_rewritten(evidence):
    assert evidence["frozen_protocol"]["status"] == "FROZEN_BEFORE_NUMPY_2_4_NATIVE_X86_V4_CPU_PREFLIGHT"
    assert evidence["frozen_protocol"]["file_git_blob_sha"] == "a11f0d480f1db1a0dfb6e8886225612158c642ae"
    assert evidence["frozen_protocol"]["prior_original_AVX512F_trial_reinterpreted"] is False
