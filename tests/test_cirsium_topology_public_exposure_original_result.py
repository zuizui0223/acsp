"""Post-execution original artifact and claim boundary for public source-only cohort screen."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from research.audit_cirsium_topology_cohort_exposure_screen import SOURCE_GIT_BLOBS, EXPOSED_TOPOLOGY_UNITS

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / 'validation/cirsium_topology_new_cohort_public_exposure_screen_result_v1.json'
PROVENANCE = ROOT / 'validation/cirsium_topology_public_exposure_screen_artifact_provenance_v1.json'


def records():
    return json.loads(RESULT.read_text()), json.loads(PROVENANCE.read_text())


def test_original_json_exact_provenance_and_public_status():
    report, origin = records()
    assert hashlib.sha256(RESULT.read_bytes()).hexdigest() == origin['original_inside_json_sha256']
    assert origin['original_artifact_id'] == 12015553828
    assert origin['original_github_workflow_run_id'] == 38828332256
    assert origin['original_job_id'] == 116740959988
    assert origin['original_artifact_zip_sha256'] == '26e962ef84880895b2af5b945b2c92119d21aa7f373e3ab53aef63c5f4779bce'
    assert report['status'] == 'PUBLIC_REGISTRY_EXPOSURE_SCREEN_COMPLETE_NO_UNTOUCHED_COHORT_AUTHORIZED'


def test_screen_is_not_field_cohort_or_a_posthoc_favorable_subset():
    report, origin = records()
    assert report['registered_original_units'] == 13
    assert report['candidate_pool_count'] == 9
    assert report['method_exposed_within_screened_count'] == 4
    assert report['without_explicit_method_use_in_pinned_sources_count'] == 5
    assert report['independent_confirmatory_unit_count'] == 0
    assert report['ready_for_field_assignment_count'] == 0
    assert origin['field_ready_count'] == 0
    assert report['units_without_explicit_method_use_in_pinned_sources'] == [
        'CIR03', 'CIR05', 'CIR09', 'CIR10', 'CIR11']


def test_prior_execution_exposure_is_not_confused_with_new_untouched_field_outcomes():
    report, _ = records()
    for unit in ('CIR01', 'CIR04', 'CIR07'):
        assert 'STRUCTURAL_HOLDOUT_DEVELOPMENT_EXECUTED' in report['units'][unit]['exposure_evidence']
    assert 'COASTAL_DEVELOPMENT_PUBLIC_OUTCOME_OPENED' in report['units']['CIR08']['exposure_evidence']
    assert 'STRUCTURAL_HOLDOUT_DEVELOPMENT_EXECUTED' not in report['units']['CIR08']['exposure_evidence']
    assert report['units']['CIR01']['public_historical_outcome_exposure'] == 'EXPLICITLY_DOCUMENTED'
    assert all(report['units'][u]['prospective_field_outcomes_marked_opened_in_registry'] is False for u in report['screened_units'])


def test_original_ten_source_blobs_stay_unchanged_and_claim_limited():
    report, origin = records()
    assert report['pinned_public_git_blobs'] == SOURCE_GIT_BLOBS
    assert len(SOURCE_GIT_BLOBS) == 10
    assert origin['original_source_file_git_blobs_pinned'] == 10
    assert report['development_exposed_topology_units'] == list(EXPOSED_TOPOLOGY_UNITS)
    assert report['claims']['absence_of_exposure_in_all_other_repositories_proven'] is False
    assert report['claims']['public_registry_outcome_false_implies_untouched'] is False


def test_no_field_geometry_or_unsupported_scientific_claim():
    report, origin = records()
    for u in report['screened_units']:
        entry = report['units'][u]
        assert entry['patch_status'] == 'NOT_BUILT'
        assert entry['independent_cohort_authorized'] is False
        assert entry['actual_field_assignment_authorized'] is False
        assert entry['private_patch_sha_and_membership_verified'] is False
        assert entry['candidate_schedule_frozen'] is False
    assert report['claims']['no_private_geometry_read'] is True
    assert report['claims']['field_detection_advantage_established'] is False
    assert report['claims']['prospective_field_outcomes_may_be_opened'] is False
    assert origin['fresh_field_outcomes_read'] is False
    assert origin['private_range_sector_geometries_read'] is False


def test_public_result_never_contains_exact_coordinates_or_sector_values():
    data = RESULT.read_text()
    for literal in ('"latitude"', '"longitude"', '"range_sector":', '"target_locality_id"', '"grid_row"', '"grid_col"', '青森県側の確認済み野生集団', '四国のP01対象'):
        assert literal not in data


def test_structural_baseline_cannot_be_used_as_disconnected_patch_method_confirmation():
    report, _ = records()
    x = report['units']['CIR11']
    assert x['structural_family_status'] == 'NO_FROZEN_STRUCTURAL_FAMILY_BASELINE_ONLY'
    assert x['independent_cohort_authorized'] is False
