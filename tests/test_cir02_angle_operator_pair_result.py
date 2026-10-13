"""Post-observation public-safety and claim boundary for real CIR02 operator pair."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / 'validation/coverage_then_fine_structure_fresh_sentinel_v2_cir02_real_angle_operator_pair_result_v1.json'


def load():
    return json.loads(RESULT.read_text(encoding='utf-8'))


def test_named_original_provenance_and_source_recovery_preserved():
    row = load()
    assert row['source_issue'] == 253 and row['source_pr'] == 270
    assert row['supplementary_source_workflow_run'] == 38219363976
    p = row['source_provenance']
    assert p['A']['initial_job_id'] == 114711688727
    assert p['A']['initial_conclusion'] == 'failed_closed_original_source_world_identity_mismatch'
    assert p['A']['successful_single_retry_job_id'] == 115317402801
    assert p['B']['original_success_job_id'] == 114711688652
    assert p['A']['artifact_id'] != p['B']['artifact_id']
    assert p['source_retry_count_for_A'] == 1
    assert p['replicas_are_distinct_GitHub_jobs'] is True
    assert p['replicas_are_distinct_workflow_run_ids'] is False
    assert p['original_A_failure_retained_not_silently_substituted'] is True


def test_original_source_and_sampled_parent_boundaries_are_strict():
    row = load()
    w = row['original_world']
    assert w['candidate_grid_rows'] == 464633
    assert w['gsi_source_complete_rows'] == 383460
    assert w['source_selected_mosaic_chunks'] == 177
    assert len(w['original_grid_sha256']) == 64
    assert len(w['original_selected_dem_content_sequence_sha256']) == 64
    assert w['source_world_bindings_equal'] is True
    assert all(w['input_sample_identity_and_gradient_gates'].values())
    assert row['sampled_stage_protocol']['original_source_chunks'] == [0,88,176]
    assert row['sampled_stage_protocol']['complete_cells_per_chunk'] == 24
    assert row['sampled_stage_protocol']['sampled_complete_cells'] == 72
    assert row['sampled_stage_protocol']['all_177_chunk_intermediate_values_compared'] is False


def test_earliest_real_operator_difference_and_historical_modes():
    row = load()
    obs = row['comparisons']
    assert obs['first_differing_exact_operator'] == 'arctan_radians'
    assert obs['first_differing_decimal8_operator'] == 'arctan_radians'
    assert obs['first_differing_decimal2_operator'] is None
    for name in ('dx_squared','dy_squared','squared_sum','gradient_magnitude'):
        assert all(obs['six_angle_operators'][name].values())
    for name in ('arctan_radians','instantaneous_slope'):
        assert obs['six_angle_operators'][name] == {'exact':False,'decimal2':True,'decimal8':False}
    assert obs['previous_nine_stages_A_matches_historical_second_run'] is True
    assert obs['previous_nine_stages_B_matches_historical_first_run'] is True
    assert obs['dx_and_dy_squares_parallel_inputs'] is True


def test_cpu_dispatch_recorded_but_causal_claim_not_promoted():
    row = load()
    v = row['runtime']
    assert v['python_A'] == v['python_B'] == '3.11.17'
    assert v['numpy_A'] == v['numpy_B'] == '2.4.6'
    assert v['numpy_extension_sha_equal'] is True
    assert v['float32_arctan_selected_loop_A'] == 'baseline(X86_V2)'
    assert v['float32_arctan_selected_loop_B'] == 'X86_V4'
    assert v['multiply_loop_equal'] is True
    assert v['add_loop_equal'] is True
    assert v['sqrt_loop_equal'] is True
    assert v['degree_loop_reported_by_numpy'] is False
    assert row['claim_boundary']['arctan_dispatch_difference_is_an_observed_covariate'] is True
    assert row['claim_boundary']['within_same_worker_CPU_dispatch_intervention_on_original_real_DEM_done'] is False
    assert row['claim_boundary']['arctan_CPU_dispatch_causal_effect_established_on_original_real_DEM'] is False


def test_no_private_site_raw_dem_or_biological_selector_promotion():
    row = load()
    assert 'POST_OBSERVATION' in row['status']
    assert row['original_world']['private_coordinates_or_cell_ids_exported'] is False
    assert row['original_world']['prospective_field_outcomes_opened'] is False
    for k in ('real_slope_difference_magnitude_quantified','whole_177_chunk_numerical_replay_established',
              'full_structural_rank_swap_count_measured','field_discovery_efficiency_or_occupancy_validated',
              'local_structural_selector_validated','main_validated_Japan_product_modified',
              'frozen_2p5pct_or_1km_rule_changed'):
        assert row['claim_boundary'][k] is False
    text = RESULT.read_text(encoding='utf-8')
    for forbidden in ('"latitude"','"longitude"','"candidate_cell_id"','"raster_path"','"tile_path"'):
        assert forbidden not in text
