from __future__ import annotations
import hashlib
import json
import numpy as np
import pytest
from research import cir02_angle_operators as m


def gradients():
    x=np.linspace(-7, 10, 1024, dtype=np.float32).reshape(32,32)
    y=np.linspace(3, -6, 1024, dtype=np.float32).reshape(32,32)
    x[0,0]=np.nan
    return x,y


def test_exact_parent_angle_and_original_inputs_unchanged():
    x,y=gradients(); a=x.copy();b=y.copy()
    expected=np.degrees(np.arctan(np.sqrt(x*x+y*y)))
    observed=m.angle_arrays(x,y,expected)
    assert list(observed)==['dx_squared','dy_squared','squared_sum','gradient_magnitude','arctan_radians','instantaneous_slope']
    assert all(v.dtype==np.float32 for v in observed.values())
    assert np.array_equal(observed['instantaneous_slope'],expected,equal_nan=True)
    assert np.array_equal(x,a,equal_nan=True) and np.array_equal(y,b,equal_nan=True)


def record(probe, chunk, *, suffix='', bad_parent=False):
    x,y=gradients(); angle=np.degrees(np.arctan(np.sqrt(x*x+y*y)))
    if bad_parent:angle[2,2]+=np.float32(1)
    ids=[f'private-marker-{chunk:03d}-{i:02d}{suffix}' for i in range(24)]
    rows=np.full(24,2,dtype=np.int64);cols=np.arange(24,dtype=np.int64)
    source=hashlib.sha256(f'synthetic-original-{chunk}'.encode()).hexdigest()
    probe.record(chunk,177,source,ids,rows,cols,x,y,angle)


def test_complete_hash_only_record():
    p=m.AngleProbe()
    for chunk in (0,88,176):record(p,chunk)
    s=p.summary()
    assert s['status']=='CIR02_ANGLE_SUBSTAGES_COMPLETE'
    assert s['source_complete_cells_probed']==72
    assert s['probed_chunk_count']==3
    assert len(s['operators_exact_float64_sha256'])==6
    assert len(s['parent_gradient_exact_float64_sha256'])==2
    assert s['actual_CIR02_operator_cause_identified'] is False
    assert s['private_values_or_ids_exported'] is False
    encoded=json.dumps(s)
    assert 'private-marker' not in encoded
    assert 'latitude' not in encoded and 'longitude' not in encoded
    assert all(len(v)==64 for v in s['operators_exact_float64_sha256'].values())


def test_incomplete_does_not_expose_partial_operator_verdict():
    p=m.AngleProbe();record(p,0)
    s=p.summary()
    assert s['status']=='CIR02_ANGLE_SUBSTAGES_INCOMPLETE'
    assert s['operators_exact_float64_sha256']=={}
    assert s['operators_decimal_sha256']=={}


@pytest.mark.parametrize('kind',['float64','shape','parent','infinity'])
def test_array_contract_rejects_changes(kind):
    x,y=gradients();expected=np.degrees(np.arctan(np.sqrt(x*x+y*y)))
    if kind=='float64':x=x.astype('float64')
    elif kind=='shape':y=y[:2]
    elif kind=='parent':expected[5,5]=np.nextafter(expected[5,5],np.float32(np.inf))
    else:x[1,1]=np.inf
    with pytest.raises(ValueError):m.angle_arrays(x,y,expected)


@pytest.mark.parametrize('chunk,total',[(1,177),(0,176),(88,177)])
def test_wrong_chunk_denominator_or_order_rejected(chunk,total):
    p=m.AngleProbe();x,y=gradients();a=np.degrees(np.arctan(np.sqrt(x*x+y*y)))
    with pytest.raises(ValueError):
        p.record(chunk,total,'f'*64,[f'id{i}' for i in range(24)],
                 np.full(24,2),np.arange(24),x,y,a)


def test_duplicate_and_failed_parent_leave_state_uncommitted():
    p=m.AngleProbe()
    with pytest.raises(ValueError):record(p,0,bad_parent=True)
    assert p.summary()['probed_chunk_count']==0
    record(p,0)
    with pytest.raises(ValueError):record(p,0)
    assert p.summary()['probed_chunk_count']==1


@pytest.mark.parametrize('kind',['short','duplicate','indices','source','nonfinite'])
def test_invalid_sample_fails_closed(kind):
    p=m.AngleProbe();x,y=gradients();a=np.degrees(np.arctan(np.sqrt(x*x+y*y)))
    ids=[f'id{i:02}' for i in range(24)];r=np.full(24,2);c=np.arange(24);source='e'*64
    if kind=='short':ids=ids[:-1]
    elif kind=='duplicate':ids[-1]=ids[0]
    elif kind=='indices':r[0]=32
    elif kind=='source':source='not-a-digest'
    else:r[0]=0;c[0]=0
    with pytest.raises(ValueError):p.record(0,177,source,ids,r,c,x,y,a)
    assert p.summary()['probed_chunk_count']==0


def test_identity_binding_changes_hash_even_for_identical_values():
    a=m.AngleProbe();b=m.AngleProbe()
    for chunk in (0,88,176):record(a,chunk);record(b,chunk,suffix='changed')
    aa=a.summary();bb=b.summary()
    assert aa['sampled_mosaics_content_order_sha256']==bb['sampled_mosaics_content_order_sha256']
    assert aa['sampled_candidate_identity_sha256']!=bb['sampled_candidate_identity_sha256']
    assert aa['operators_exact_float64_sha256']!=bb['operators_exact_float64_sha256']


def test_runtime_metadata_does_not_infer_unreported_dispatch():
    s=m.runtime_metadata()
    assert s['numpy']==np.__version__
    assert len(s['numpy_extension_sha256'])==64
    assert set(s['operator_dispatch'])=={'multiply','add','sqrt','arctan','degrees'}
    for name,entry in s['operator_dispatch'].items():
        assert entry['status'] in ('reported','not_reported','unavailable')
        if entry['status']!='reported':assert entry['loops']=={}
    assert 'node' not in s and 'hostname' not in s


def parent_for(child):
    return {
        'status':'ORIGINAL_REAL_DEM_CIR02_THREE_CHUNK_STAGE_AUDIT_COMPLETE',
        'cohort_unit_id':'CIR02','source_chunk_count':177,
        'probed_chunk_count':3,'source_complete_cells_probed':72,
        'all_predeclared_chunks_eligible':True,
        'sampled_mosaics_content_order_sha256':child['sampled_mosaics_content_order_sha256'],
        'stages_exact_float64_sha256':dict(child['parent_gradient_exact_float64_sha256'],
            instantaneous_slope=child['parent_angle_exact_float64_sha256']),
        'field_outcomes_opened':False,
        'stage_sampled_individual_coordinates_or_ids_public':False,
        'individual_slope_values_public':False,
    }


def test_bind_parent_proves_sample_and_source_compatibility():
    p=m.AngleProbe()
    for c in (0,88,176):record(p,c)
    child=p.summary();parent=parent_for(child)
    assert m.bind_parent(parent,child)['parent_original_diagnostic_bound'] is True


@pytest.mark.parametrize('bad',['source','dx','angle','count','privacy'])
def test_bind_parent_rejects_fake_compatibility(bad):
    p=m.AngleProbe()
    for c in (0,88,176):record(p,c)
    child=p.summary();parent=parent_for(child)
    if bad=='source':parent['sampled_mosaics_content_order_sha256']='a'*64
    elif bad=='dx':parent['stages_exact_float64_sha256']['gradient_dx']='b'*64
    elif bad=='angle':parent['stages_exact_float64_sha256']['instantaneous_slope']='c'*64
    elif bad=='count':parent['source_complete_cells_probed']=71
    else:parent['individual_slope_values_public']=True
    with pytest.raises(ValueError):m.bind_parent(parent,child)


def bound_fixture():
    p=m.AngleProbe()
    for c in (0,88,176):record(p,c)
    child=p.summary()
    return m.bind_parent(parent_for(child),child)


def test_pair_localizes_first_operator_without_causal_promotion():
    import copy
    a=bound_fixture();b=copy.deepcopy(a)
    b['operators_exact_float64_sha256']['arctan_radians']='d'*64
    b['operators_decimal_sha256']['arctan_radians']['8']='e'*64
    o=m.compare_bound_operators(a,b)
    assert o['status']=='BOUNDED_OPERATOR_HASHES_COMPARED'
    assert o['first_differing_exact_operator']=='arctan_radians'
    assert o['first_differing_decimal8_operator']=='arctan_radians'
    assert o['first_differing_decimal2_operator'] is None
    assert o['actual_CIR02_operator_cause_identified'] is False
    assert o['independent_runner_provenance_verified'] is False


@pytest.mark.parametrize('field',['sampled_mosaics_content_order_sha256','sampled_candidate_identity_sha256','parent_gradient_exact_float64_sha256'])
def test_pair_blocks_different_input_samples(field):
    import copy
    a=bound_fixture();b=copy.deepcopy(a)
    if field=='parent_gradient_exact_float64_sha256':b[field]['gradient_dx']='b'*64
    else:b[field]='b'*64
    r=m.compare_bound_operators(a,b)
    assert r['status']=='INPUTS_DIFFER_NO_OPERATOR_VERDICT'
    assert r['per_operator']=={}
    assert r['first_differing_exact_operator'] is None


@pytest.mark.parametrize('bad',['unbound','truncated','causal_claim'])
def test_pair_rejects_unbound_missing_or_overclaimed_records(bad):
    import copy
    a=bound_fixture();b=copy.deepcopy(a)
    if bad=='unbound':b['parent_original_diagnostic_bound']=False
    elif bad=='truncated':b['operators_exact_float64_sha256'].pop('arctan_radians')
    else:b['actual_CIR02_operator_cause_identified']=True
    with pytest.raises(ValueError):m.compare_bound_operators(a,b)
