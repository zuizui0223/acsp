"""Fail-closed source-world diagnostics without private sites or source hashes."""
import copy
import pytest
from research import run_cir02_angle_operators as m


def world():
    return (
        {'candidate_rows': 464633, 'source_complete_rows': 383460},
        {'selected_mosaic_content_sequence_sha256': m.FROZEN_SELECTED_SHA,
         'selected_dem_chunks': 177},
    )


def test_original_world_passes_with_only_named_boolean_gates():
    gsi, selected = world()
    actual = m.require_original_source_world(gsi, selected)
    assert set(actual) == {
        'candidate_rows_match_original',
        'source_complete_rows_match_original',
        'selected_dem_content_sequence_matches_original',
        'selected_dem_chunk_count_matches_original',
    }
    assert all(v is True for v in actual.values())
    assert all(type(v) is bool for v in actual.values())


@pytest.mark.parametrize('field,part,mutated,failed', [
    ('candidate_rows', 'gsi', 464632, 'candidate_rows_match_original'),
    ('source_complete_rows', 'gsi', 383459, 'source_complete_rows_match_original'),
    ('selected_mosaic_content_sequence_sha256','selected','wrong-private-source-123',
     'selected_dem_content_sequence_matches_original'),
    ('selected_dem_chunks', 'selected', 176, 'selected_dem_chunk_count_matches_original'),
])
def test_failure_explains_exact_failed_public_gate_and_does_not_leak_value(field, part, mutated, failed):
    gsi, selected = world()
    target = gsi if part == 'gsi' else selected
    target[field] = mutated
    with pytest.raises(ValueError, match='real source world differs') as info:
        m.require_original_source_world(gsi, selected)
    explanation = str(info.value)
    assert failed in explanation
    assert str(mutated) not in explanation
    assert 'wrong-private-source-123' not in explanation
    assert m.FROZEN_SELECTED_SHA not in explanation


def test_two_independent_failures_both_reported_no_retuning():
    gsi, selected = world()
    gsi['source_complete_rows'] = -12
    selected['selected_mosaic_content_sequence_sha256'] = 'other-private-source-token'
    with pytest.raises(ValueError) as info:
        m.require_original_source_world(gsi, selected)
    detail = str(info.value)
    assert 'source_complete_rows_match_original' in detail
    assert 'selected_dem_content_sequence_matches_original' in detail
    assert 'other-private-source-token' not in detail


@pytest.mark.parametrize('field,part', [
    ('candidate_rows','gsi'),
    ('source_complete_rows','gsi'),
    ('selected_mosaic_content_sequence_sha256','selected'),
    ('selected_dem_chunks','selected'),
])
def test_missing_expected_field_fails_closed_and_reports_only_gate(field, part):
    gsi, selected = world()
    (gsi if part == 'gsi' else selected).pop(field)
    with pytest.raises(ValueError, match='real source world differs') as info:
        m.require_original_source_world(gsi, selected)
    gate = {'candidate_rows': 'candidate_rows_match_original',
            'source_complete_rows': 'source_complete_rows_match_original',
            'selected_mosaic_content_sequence_sha256': 'selected_dem_content_sequence_matches_original',
            'selected_dem_chunks': 'selected_dem_chunk_count_matches_original'}[field]
    assert gate in str(info.value)


def test_bool_cannot_masquerade_as_integer_one():
    gsi, selected = world()
    selected['selected_dem_chunks'] = True
    with pytest.raises(ValueError, match='selected_dem_chunk_count_matches_original'):
        m.require_original_source_world(gsi, selected)
