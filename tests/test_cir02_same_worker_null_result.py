"""Freeze first real CIR02 same-worker AVX512F trial as a *non-informative* manipulation."""
from __future__ import annotations
import json
from pathlib import Path

import pytest

RESULT = Path(__file__).resolve().parents[1] / 'validation' / 'coverage_then_fine_structure_fresh_sentinel_v2_cir02_same_worker_avx512f_result_v1.json'


def load():
    return json.loads(RESULT.read_text(encoding='utf-8'))


def test_status_is_null_without_dispatch_change():
    report = load()
    assert report['status'] == 'REAL_SOURCE_BOUND_DISPATCH_MANIPULATION_NOT_INFORMATIVE'
    assert report['readout'] == 'DISPATCH_INTERVENTION_NOT_DISTINGUISHABLE_ON_THIS_WORKER'
    assert report['dispatch_effect_identified'] is False
    assert report['cpu_causality_established'] is False


def test_original_provenance_and_evidence_are_pinned():
    v = load()
    assert v['source']['workflow_id'] == 38423447916
    assert v['source']['job_id'] == 115386654176
    assert v['source']['original_artifact_id'] == 11829764004
    assert v['source']['archive_sha256'] == '117b711f158d58670dea973b5be9c13cb0f3bf23716e9adc4938dcecc09c2960'
    assert v['source']['intervention_json_sha256'] == 'e40198f911551296376ecb3e64c4c306281f78f5032dd758b3892acb5c214a32'
    assert v['source']['unchanged_parent_json_sha256'] == '60bec29b710dfd3f4293b19a18272e368000ffa52a36dcf01c71b1c04ad03dc7'


def test_one_original_source_world_kept_frozen():
    v = load()
    orig = v['original_source_world']
    assert orig['candidate_rows'] == 464633
    assert orig['source_complete_rows'] == 383460
    assert orig['selected_dem_chunks'] == 177
    assert orig['sampled_original_cells'] == 72
    assert orig['selected_mosaic_content_sequence_sha256'] == '7ef762da0577e94d4f94bf1f171cfe1aa6f8fc9046cd6c03ee364cd334a43ddf'
    assert v['original_input_files_and_magnitudes_bound'] is True
    assert v['two_within_mode_repetitions_equal'] is True


def test_requested_flag_cannot_be_misdescribed_as_x86_v4_switch():
    v = load()
    m = v['modes']
    assert m['original']['flag'] is None
    assert m['original']['selected_float32_arctan_loop'] == 'X86_V4'
    assert m['intervention']['flag'] == 'AVX512F'
    assert m['intervention']['selected_float32_arctan_loop'] == 'X86_V4'
    assert m['actual_loop_changed'] is False
    assert m['original_and_intervention_arctan_exact_equal'] is True
    assert m['original_and_intervention_arctan_decimal8_equal'] is True
    assert m['original_and_intervention_slope_exact_equal'] is True


def test_no_field_or_full_numeric_or_product_claim():
    v = load()
    assert v['scientific_limits']['no_real_cpu_dispatch_causal_claim'] is True
    assert v['scientific_limits']['not_full_177_chunk_numeric_replay'] is True
    assert v['scientific_limits']['no_field_outcomes_opened'] is True
    assert v['scientific_limits']['no_validated_patch_rule_change'] is True
    assert v['scientific_limits']['original_complete_two_workflow_result_kept_separate'] is True
    dump = RESULT.read_text(encoding='utf-8').lower()
    for private_pattern in ['longitude', 'latitude', 'private-cell-', 'raw_dem', 'candidate_cell_id', '/tmp/acsp-']:
        assert private_pattern not in dump
