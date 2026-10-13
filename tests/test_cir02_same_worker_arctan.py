"""Controlled arctan dispatch on the *same* float32 magnitude array; no real DEM or sites."""
from __future__ import annotations
import json
import os
from pathlib import Path
import numpy as np
import pytest

from research import audit_cir02_same_worker_arctan as m
from research.cir02_angle_operators import AngleProbe


def samples():
    values = np.linspace(np.float32(.00001), np.float32(10), 100000,
                         dtype=np.float32).reshape(400, 250)
    out = []
    for index in (0, 88, 176):
        # original selected ID ordering and native full-float32 two-dimensional arrays
        ids = [f'private-cell-{index:03d}-{j:03d}' for j in range(24)]
        rows = np.asarray([(j * 13 + index) % 400 for j in range(24)], np.int64)
        cols = np.asarray([(j * 7 + index) % 250 for j in range(24)], np.int64)
        out.append(dict(chunk_index=index, ids=ids, rows=rows, cols=cols,
                        dx=values.copy(), magnitude=np.sqrt(values*values)))
    return out


def original_parent_hashes(rows):
    p = AngleProbe()
    for entry in rows:
        mag = entry['magnitude']
        x = entry['dx']
        y = np.zeros_like(x)
        degrees = np.degrees(np.arctan(np.sqrt(x*x+y*y)))
        p.record(entry['chunk_index'],177,'a'*64,entry['ids'],entry['rows'],entry['cols'],x,y,degrees)
    summary = p.summary()
    summary["parent_original_diagnostic_bound"] = True  # fixture substitutes already verified parent contract
    return summary


def test_same_worker_process_intervention_uses_identical_full_arrays_and_private_inputs():
    rows = samples()
    parent = original_parent_hashes(rows)
    record = m.run_intervention(rows, parent)
    assert record['sampled_cells'] == 72
    assert record['same_worker_source_magnitudes_fixed'] is True
    assert record['same_python_numpy_extension_for_modes'] is True
    assert record['original_mode_matches_parent_operator_hashes'] is True
    assert record['same_mode_repeats_exact'] is True
    assert record['modes']['original']['runtime']['disabled_cpu_features'] is None
    assert record['modes']['avx512f_disabled']['runtime']['disabled_cpu_features'] == 'AVX512F'
    assert record['modes']['original']['runtime']['cpu_flags_changed_by_instrument'] is False
    assert record['modes']['avx512f_disabled']['runtime']['cpu_flags_changed_by_instrument'] is True
    assert record['comparison']['gradient_magnitude_exact_equal'] is True
    assert record['comparison']['sampled_candidate_identity_sha_equal'] is True
    assert isinstance(record['comparison']['arctan_radians_exact_equal'], bool)
    assert record['within_worker_intervention_implemented'] is True
    assert record['full_177_chunk_numeric_replay_claimed'] is False
    assert record['field_outcomes_opened'] is False
    assert record['original_gsi_pipeline_modified'] is False
    # Only the aggregate hash/flags may leave the worker.
    exported = json.dumps(record)
    for private in ('private-cell-','magnitude_path','row_index','raster_path','longitude','latitude'):
        assert private not in exported


def test_sampled_arctan_outputs_are_hashed_like_parent_original():
    rows = samples()
    parent = original_parent_hashes(rows)
    record = m.run_intervention(rows, parent)
    v = record['modes']['original']['operators_exact_float64_sha256']
    assert v['gradient_magnitude'] == parent['operators_exact_float64_sha256']['gradient_magnitude']
    assert v['arctan_radians'] == parent['operators_exact_float64_sha256']['arctan_radians']
    assert v['instantaneous_slope'] == parent['operators_exact_float64_sha256']['instantaneous_slope']
    assert record['modes']['original']['sampled_candidate_identity_sha256'] == parent['sampled_candidate_identity_sha256']


def test_rejects_magnitude_array_that_changes_since_parent_capture():
    rows = samples()
    parent = original_parent_hashes(rows)
    rows[0]['magnitude'][rows[0]['rows'][0], rows[0]['cols'][0]] += 1
    with pytest.raises(ValueError, match='original parent'):
        m.run_intervention(rows, parent)


def test_rejects_missing_or_duplicate_original_chunks():
    rows = samples()
    for candidate in (rows[:2], [rows[0], rows[0], rows[2]]):
        with pytest.raises(ValueError, match='original chunk'):
            m.run_intervention(candidate, {'operators_exact_float64_sha256':{}})


def test_rejects_private_geography_in_public_output_and_fails_closed_on_bad_sample():
    rows = samples()
    rows[0]['ids'][0] = 'private-cell-not-sorted'
    with pytest.raises(ValueError, match='original IDs'):
        m.run_intervention(rows, original_parent_hashes(samples()))


def test_same_worker_cpu_dispatch_control_requires_actual_loop_change():
    fake_original = {'status':'reported','loops': {'ff': {'current':'X86_V4'}}}
    fake_same = {'status':'reported','loops': {'ff': {'current':'X86_V4'}}}
    fake_base = {'status':'reported','loops': {'ff': {'current':'baseline(X86_V2)'}}}
    assert m.evaluate_loop_change(fake_original, fake_same) is False
    assert m.evaluate_loop_change(fake_original, fake_base) is True
    assert m.evaluate_loop_change({'status':'not_reported','loops':{}}, fake_base) is None


def test_cpu_features_can_change_arctan_path_without_recomputing_inputs():
    rows = samples()
    record = m.run_intervention(rows, original_parent_hashes(rows))
    # When this machine supports an alternate AVX512 path, intervention is informative.
    if record['comparison']['arctan_loop_changed']:
        assert record['comparison']['first_differing_exact_operator'] in (None, 'arctan_radians')
        if record['comparison']['first_differing_exact_operator'] == 'arctan_radians':
            assert record['causal_readout'] == 'SAME_WORKER_ARCTAN_DISPATCH_EFFECT_ON_SAMPLED_VALUES_OBSERVED'
    else:
        assert record['causal_readout'] == 'DISPATCH_INTERVENTION_NOT_DISTINGUISHABLE_ON_THIS_WORKER'


def test_pre_outcome_contract_freezes_modes_repeats_input_and_scientific_ceiling():
    v = m.validate_contract()
    assert v['status'] == 'FROZEN_BEFORE_REAL_SAME_WORKER_CPU_INTERVENTION'
    assert v['source_world']['original_candidate_rows'] == 464633
    assert v['source_world']['gsi_source_complete_rows'] == 383460
    assert v['source_world']['selected_source_dem_chunks'] == 177
    assert v['sample']['original_chunks'] == [0,88,176]
    assert v['sample']['source_complete_per_chunk'] == 24
    assert v['cpu_intervention']['only_disabled_feature'] == 'AVX512F'
    assert v['cpu_intervention']['fresh_process_repeats_per_mode'] == 2
    assert v['scientific_scope']['no_field_outcomes_or_exact_locations_public'] is True
    assert v['scientific_scope']['no_2p5pct_or_1km_selector_rule_changed'] is True
    assert v['scientific_scope']['cpu_dispatch_causes_historical_rank_change_established'] is False
