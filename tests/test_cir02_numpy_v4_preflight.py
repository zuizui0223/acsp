"""CPU-only NumPy v2.4 X86_V4 dispatch preflight; no real DEM or field cells."""
from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path
import pytest

from research.preflight_cir02_numpy_v4_dispatch import classify_original_and_disabled, validate_contract


def fixture(loop='X86_V4', disabled='baseline(X86_V2)', same=True):
    one={'mode':'original','python':'3.11.17','numpy':'2.4.6','binary_sha256':'a'*64,
         'source_sha256':'b'*64,'arctan_loop':loop,'arctan_exact_sha256':'c'*64}
    two={**one,'mode':'x86_v4_disabled','arctan_loop':disabled,
         'arctan_exact_sha256':'c'*64 if same else 'd'*64}
    return one,two


def test_preflight_contract_is_frozen_around_v4_not_old_avx512f():
    v=validate_contract()
    assert v['status']=='FROZEN_BEFORE_NUMPY_2_4_NATIVE_X86_V4_CPU_PREFLIGHT'
    assert v['source_kind']=='SYNTHETIC_CPU_ONLY_NO_GSI'
    assert v['numpy_version']=='2.4.6'
    assert v['disable_only_feature']=='X86_V4'
    assert v['repeats_per_mode']==2
    assert v['forbid_real_dem_or_field_records'] is True
    assert v['v1_avx512f_source_result_is_immutable'] is True


def test_actual_loop_switch_sufficient_even_if_synthetic_hash_unchanged():
    a,b=fixture(same=True)
    r=classify_original_and_disabled(a,b)
    assert r['readout']=='NATIVE_X86_V4_DISPATCH_SWITCH_CONFIRMED'
    assert r['loop_changed'] is True
    assert r['synthetic_arctan_exact_equal'] is True


def test_actual_loop_switch_with_numeric_difference_reported_not_assumed():
    a,b=fixture(same=False)
    r=classify_original_and_disabled(a,b)
    assert r['readout']=='NATIVE_X86_V4_DISPATCH_SWITCH_CONFIRMED'
    assert r['synthetic_arctan_exact_equal'] is False


def test_no_v4_on_default_worker_is_inconclusive_not_selection_failure():
    a,b=fixture(loop='baseline(X86_V2)',disabled='baseline(X86_V2)')
    r=classify_original_and_disabled(a,b)
    assert r['readout']=='NATIVE_WORKER_NOT_RUNNING_X86_V4'
    assert r['loop_changed'] is False


def test_requested_flag_did_not_change_actual_loop_is_inconclusive():
    a,b=fixture(loop='X86_V4',disabled='X86_V4')
    r=classify_original_and_disabled(a,b)
    assert r['readout']=='NATIVE_X86_V4_OVERRIDE_UNEFFECTIVE'
    assert r['loop_changed'] is False


def test_unreported_dispatch_is_inconclusive():
    a,b=fixture(loop='not_reported',disabled='not_reported')
    r=classify_original_and_disabled(a,b)
    assert r['readout']=='DISPATCH_LOOP_NOT_REPORTED'


@pytest.mark.parametrize('field,new_value',[
 ('source_sha256','e'*64),('binary_sha256','e'*64),('numpy','3.0.0'),('python','3.14')])
def test_changing_input_or_python_or_numpy_is_rejected(field,new_value):
    a,b=fixture()
    b[field]=new_value
    with pytest.raises(ValueError,match='mismatch'):
        classify_original_and_disabled(a,b)


def test_code_produces_no_private_geography_and_does_not_import_numpy_before_child_flag():
    import research.preflight_cir02_numpy_v4_dispatch as m
    src=Path(m.__file__).read_text()
    assert 'import numpy as np' in src
    assert src.index('import numpy as np') > src.index('def run_child')
    for forbidden in ('longitude','latitude','gbif','field_outcomes','raw_dem','candidate_cell_id'):
        assert forbidden not in src.lower()
