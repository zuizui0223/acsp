"""No field outcome; exactly frozen public counts + synthetic preview bounds."""
from __future__ import annotations
import copy
import json
from pathlib import Path

import pytest
from research import assess_cirsium_topology_site_first_stage as m

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / 'examples/synthetic_topology_site_preview.json'


def test_source_pins_and_public_result_are_in_original_state():
    sources = m.read_bound_sources()
    assert set(sources['topology']['units']) == set(m.UNITS)
    assert sources['trial']['cohort_identity_frozen'] is False
    assert sources['exposure']['ready_for_field_assignment_count'] == 0
    assert sources['exposure']['independent_confirmatory_unit_count'] == 0


def test_historical_exhaustive_envelope_counts_without_optimizing_a_budget():
    result = m.generate_public_report()
    envelope = result['historical_full_frame_counterfactual_only']
    assert envelope['total_internally_disconnected_patches'] == 4168
    assert envelope['total_unique_sites_if_all_assigned'] == 4168
    assert envelope['total_person_minutes_if_all_assigned'] == 375120
    assert envelope['total_active_person_hours_if_all_assigned'] == 6252
    assert envelope['all_four_units_are_independent_biological_replicates'] is False
    assert envelope['any_actual_visits_authorized'] is False
    assert envelope['units']['CIR02']['planned_person_hours'] == 480
    assert envelope['units']['CIR06']['planned_person_hours'] == 4938
    assert envelope['units']['CIR12']['planned_person_hours'] == 417
    assert envelope['units']['CIR13']['planned_person_hours'] == 417


def test_full_frame_counterfactual_does_not_create_new_sector_eligibility():
    result = m.generate_public_report()
    assert result['status'] == 'PRE_FIELD_FIRST_STAGE_UNKNOWN_NO_FIELD_OUTCOMES'
    for name in ('actual_new_taxon_sector_patch_count', 'actual_new_taxon_sector_discordant_site_fraction'):
        assert result['future_independent_trial'][name] is None
    assert result['future_independent_trial']['field_assignments_authorized'] is False
    assert result['future_independent_trial']['independent_cohort_count_confirmed'] == 0
    assert result['claims']['field_efficiency_established'] is False
    assert result['claims']['validated_patch_generator_changed'] is False


def test_synthetic_preview_reports_max_bound_but_never_field_effect():
    p = json.loads(EXAMPLE.read_text())
    s = m.summarize_public_preview(p)
    assert s['by_cohort']['NEW01']['assigned_patch_count'] == 4
    assert s['by_cohort']['NEW01']['distinct_site_choices'] == 4
    assert s['by_cohort']['NEW01']['identical_site_choices'] == 0
    assert s['by_cohort']['NEW01']['site_choice_discordance_fraction'] == 1.0
    assert s['by_cohort']['NEW01']['max_abs_site_only_expected_binary_effect_if_same_site_has_equal_detection_process'] == 1.0
    assert s['by_cohort']['NEW01']['scheduled_active_person_hours_if_both_arms_visited'] == 6.0
    assert s['field_effect_estimated'] is False
    assert s['actual_site_source_authenticated'] is False


def test_shared_counterfactual_site_caps_true_averaged_site_only_effect():
    p = json.loads(EXAMPLE.read_text())
    p['by_cohort']['NEW01']['shared_counterfactual_count'] = 3
    s = m.summarize_public_preview(p)
    assert s['by_cohort']['NEW01']['site_choice_discordance_fraction'] == 0.25
    assert s['by_cohort']['NEW01']['max_abs_site_only_expected_binary_effect_if_same_site_has_equal_detection_process'] == 0.25
    assert s['by_cohort']['NEW01']['planned_person_minutes_per_arm'] == 180


def test_all_shared_sites_cannot_identify_site_selection_difference():
    p = json.loads(EXAMPLE.read_text())
    p['by_cohort']['NEW01']['shared_counterfactual_count'] = 4
    s = m.summarize_public_preview(p)
    assert s['by_cohort']['NEW01']['site_choice_discordance_fraction'] == 0
    assert s['by_cohort']['NEW01']['site_selection_first_stage'] == 'NONE_DIFFERENT_IN_PREVIEW'
    assert s['field_effect_estimated'] is False


def test_zero_assigned_is_none_not_fake_zero_effect():
    p = json.loads(EXAMPLE.read_text())
    p['by_cohort']['NEW01']['assigned_topology'] = 0
    p['by_cohort']['NEW01']['assigned_geometry'] = 0
    p['by_cohort']['NEW01']['shared_counterfactual_count'] = 0
    p['by_cohort']['NEW01']['planned_person_minutes_per_arm'] = 0
    p['by_cohort']['NEW01']['balance_reserve_count'] = 0
    p['assigned_patch_count'] = 0
    p['unassigned_odd_balance_reserve_count'] = 0
    s = m.summarize_public_preview(p)
    assert s['by_cohort']['NEW01']['site_choice_discordance_fraction'] is None
    assert s['by_cohort']['NEW01']['site_selection_first_stage'] == 'NO_ASSIGNED_PATCHES'


@pytest.mark.parametrize('mutation', [
    'unequal_arms', 'bad_effort', 'bad_total', 'too_many_shared', 'extra_geography',
    'true_field_outcome', 'true_field_schedule', 'confirmed', 'bad_digest',
    'bad_reserve', 'negative_count', 'bool_count', 'unknown_cohort_exposure',
])
def test_synthetic_preview_is_fail_closed_for_bad_provenance_and_counts(mutation):
    p = json.loads(EXAMPLE.read_text())
    q = p['by_cohort']['NEW01']
    if mutation == 'unequal_arms': q['assigned_geometry'] = 3
    if mutation == 'bad_effort': q['planned_person_minutes_per_arm'] = 200
    if mutation == 'bad_total': p['assigned_patch_count'] = 6
    if mutation == 'too_many_shared': q['shared_counterfactual_count'] = 5
    if mutation == 'extra_geography': p['secret_latitude'] = 35.5
    if mutation == 'true_field_outcome': p['actual_field_effect_estimated'] = True
    if mutation == 'true_field_schedule': p['field_schedule_frozen'] = True
    if mutation == 'confirmed': p['fresh_independent_biological_validation'] = True
    if mutation == 'bad_digest': p['private_assignments_sha256'] = 'none'
    if mutation == 'bad_reserve': q['balance_reserve_count'] = 2
    if mutation == 'negative_count': q['ineligible_connected_patch_count'] = -1
    if mutation == 'bool_count': q['assigned_topology'] = True
    if mutation == 'unknown_cohort_exposure': q['cohort_exposure'] = 'CONFIRMED_FIELD_READY'
    with pytest.raises(ValueError):
        m.summarize_public_preview(p)


def test_predeclared_sources_failing_any_original_git_sha_must_stop(tmp_path, monkeypatch):
    copied = tmp_path / 'validation'
    copied.mkdir()
    for name in m.SOURCE_BLOBS:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes((ROOT / name).read_bytes())
    monkeypatch.setattr(m, 'ROOT', tmp_path)
    assert m.read_bound_sources()['exposure']['candidate_pool_count'] == 9
    target = tmp_path / next(iter(m.SOURCE_BLOBS))
    target.write_bytes(target.read_bytes()+b' ')
    with pytest.raises(ValueError,match='source blob'):
        m.read_bound_sources()


def test_saved_public_report_reproduces_without_raw_private_patch_coordinates(tmp_path):
    result = m.generate_public_report()
    s = json.dumps(result,sort_keys=True,ensure_ascii=False)
    for private in ('candidate_cell_id','private_patch_ref','longitude','latitude','zone_member_site_ids','private_cell_ids'):
        assert private not in s
    assert not any(x in s for x in ('NEW01_r', 'CIR02_r'))
    assert m.generate_public_report() == result
    path = tmp_path/'out.json'
    m.write_public_json(path,result)
    assert json.loads(path.read_text()) == result
    with pytest.raises(FileExistsError): m.write_public_json(path,result)
