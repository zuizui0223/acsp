"""Synthetic *nonidentification* of two downstream Cirsium medoid-site rules."""
from pathlib import Path
import json
import pytest

from research import prove_cirsium_site_choice_nonidentifiability as m

ROOT=Path(__file__).resolve().parents[1]


def test_same_original_patch_summary_allows_both_zero_and_full_discordance():
    d=m.generate_report()
    assert d['status']=='SOURCE_BOUND_SYNTHETIC_SITE_CHOICE_NOT_IDENTIFIED'
    a,b=d['synthetic_counterexamples']
    assert a['synthetic_topology_signature']==b['synthetic_topology_signature']
    assert a['synthetic_topology_signature']['retained_support_cells']==4
    assert a['synthetic_topology_signature']['complete_link_patch_count']==1
    assert a['synthetic_topology_signature']['global_mask_component_count']==2
    assert a['synthetic_topology_signature']['within_patch_component_total']==2
    assert a['synthetic_topology_signature']['disconnected_patch_count']==1
    assert a['synthetic_topology_signature']['extra_within_patch_components']==1
    assert a['synthetic_topology_signature']['largest_component_size']==3
    assert a['site_choice_discordance_q']==0
    assert b['site_choice_discordance_q']==1
    assert a['actual_field_outcome_used'] is False
    assert b['actual_field_outcome_used'] is False


def test_counterexamples_only_use_valid_existing_representatives():
    for name,points in m.SYNTHETIC_MASKS.items():
        unit='SYNTHETIC_ONLY'
        data={'cohort_unit_id':unit, 'patch_ref':name,
              'member_ids':[f'{unit}_r{r}_c{c}' for r,c in sorted(points)]}
        selected=m.choose_counterfactual_sites(data)
        assert selected['eligible_disconnected'] is True
        assert selected['selected_by_topology'] in data['member_ids']
        assert selected['selected_by_geometry'] in data['member_ids']
        assert selected['counterfactual_site_shared']==(name=='IDENTICAL_SITE_CHOICE')
        assert max((x[0]-y[0])**2+(x[1]-y[1])**2 for x in points for y in points)<=100


def test_original_four_aggregate_upper_envelopes_are_source_locked():
    report=m.generate_report()
    expected={'CIR02':(573,320),'CIR06':(3883,3292),'CIR12':(654,278),'CIR13':(654,278)}
    for unit,(patches,disconnected) in expected.items():
        x=report['original_development_aggregate_envelopes'][unit]
        assert x['original_patch_count']==patches
        assert x['internally_disconnected_patch_count']==disconnected
        assert x['unconditional_q_lower_bound']==0
        assert x['unconditional_q_upper_bound']==pytest.approx(disconnected/patches)
        assert x['eligible_disconnected_only_q_interval']==[0.0,1.0]
        assert x['actual_site_choice_discordance_q'] is None


def test_reference_source_sha_is_checked_against_exact_git_blob():
    report=m.generate_report()
    assert report['original_source_blobs']==m.ORIGINAL_SOURCE_BLOBS


def test_tampered_source_must_fail_closed(tmp_path,monkeypatch):
    import shutil
    for path in m.ORIGINAL_SOURCE_BLOBS:
        target=tmp_path/path
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/path,target)
    monkeypatch.setattr(m,'ROOT',tmp_path)
    assert m.generate_report()['status']=='SOURCE_BOUND_SYNTHETIC_SITE_CHOICE_NOT_IDENTIFIED'
    target=tmp_path/next(iter(m.ORIGINAL_SOURCE_BLOBS))
    target.write_bytes(target.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='git blob'):
        m.generate_report()


def test_empty_or_non_disconnected_population_does_not_become_q_zero():
    result=m.generate_report()
    assert result['future_independent_trial']['actual_new_cohort_q'] is None
    assert result['future_independent_trial']['source_complete_private_patch_memberships_verified'] is False
    assert result['future_independent_trial']['field_eligibility_authorized'] is False
    assert result['future_independent_trial']['prospective_outcomes_opened'] is False


def test_no_private_geographic_or_site_ids_in_public_report():
    s=json.dumps(m.generate_report(),sort_keys=True)
    for word in ['candidate_cell_id','zone_member_site_ids','longitude','latitude','SYNTHETIC_ONLY_r','private_exact_site_record','field_outcome_state']:
        assert word not in s


def test_original_three_arm_and_product_remain_untouched():
    report=m.generate_report()
    flags=report['scientific_limits']
    assert flags['new_independent_biological_confirmation'] is False
    assert flags['validated_2p5percent_1km_robust_core_changed'] is False
    assert flags['frozen_three_arm_field_protocol_changed'] is False
    assert flags['sampled_original_private_candidate_geometry'] is False
    assert flags['real_field_discovery_effect_estimated'] is False


def test_saved_canonical_result_byte_equivalence():
    saved=ROOT/'validation/cirsium_site_choice_aggregate_nonidentifiability_result_v1.json'
    assert saved.is_file()
    assert json.loads(saved.read_text(encoding='utf-8')) == m.generate_report()
