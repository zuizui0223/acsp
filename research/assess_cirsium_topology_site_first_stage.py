#!/usr/bin/env python3
"""Source-bound pre-field feasibility, never a real detection or field schedule.

Two distinct site-selection methods can return the same retained 100m cell even
inside a fragmented patch. Their site-choice *first stage* is not measured by
fragmentation alone. Public aggregate previews may reveal this first stage
without disclosing any exact cell or patch ID.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE_BLOBS = {
    'validation/coverage_then_fine_structure_fresh_sentinel_v2_patch_topology_component_gap_v1.json': '06b7dbd6e1152e8187a7ecd31ee6ab4b5778d0f6',
    'validation/coverage_then_fine_structure_patch_connectivity_field_trial_design_v1.json': 'ec18c79b126b994a47c9680e5098548e655f88c9',
    'validation/cirsium_topology_new_cohort_public_exposure_screen_result_v1.json': '9eb20404c48f6b85cffc66e4d2332dc98b169471',
}
UNITS = ('CIR02','CIR06','CIR12','CIR13')
PREVIEW_FIELDS = frozenset((
    'schema_version','status','private_assignments_sha256','by_cohort',
    'assigned_patch_count','unassigned_odd_balance_reserve_count',
    'ineligible_connected_patch_count','fresh_independent_biological_validation',
    'field_outcomes_opened','field_schedule_frozen','real_candidate_geometry_used_now',
    'actual_field_effect_estimated','original_three_arm_field_protocol_changed',
))
COHORT_FIELDS = frozenset((
    'assigned_topology','assigned_geometry','shared_counterfactual_count',
    'planned_person_minutes_per_arm','balance_reserve_count',
    'ineligible_connected_patch_count','cohort_exposure',
))
STATUS = 'PRE_FIELD_FIRST_STAGE_UNKNOWN_NO_FIELD_OUTCOMES'


def _source_git_blob(path: Path) -> str:
    data=path.read_bytes()
    return hashlib.sha1(f'blob {len(data)}\0'.encode('ascii')+data).hexdigest()


def _fail_if(cond:bool,message:str)->None:
    if cond:raise ValueError(message)


def read_bound_sources() -> dict[str,Any]:
    """Require byte-unchanged *committed* public inputs; never read locations."""
    docs=[]
    for path,sha in SOURCE_BLOBS.items():
        p=ROOT/path
        if not p.is_file() or p.is_symlink() or _source_git_blob(p)!=sha:
            raise ValueError(f'original source blob differs: {path}')
        docs.append(json.loads(p.read_text(encoding='utf-8')))
    topology,trial,exposure=docs
    _fail_if(topology.get('status')!='POSTHOC_DESCRIPTIVE_SYNTHESIS_OF_PREVIOUSLY_FROZEN_TOPOLOGY', 'frozen topology source status drift')
    _fail_if(set(topology.get('units',{}))!=set(UNITS),'frozen original cohort changed')
    _fail_if(topology.get('source',{}).get('support_fraction')!=0.025 or topology.get('source',{}).get('patch_complete_link_diameter_m')!=1000,'support/patch scale changed')
    _fail_if(trial.get('status')!='METHOD_DESIGN_FROZEN_BEFORE_NEW_COHORT_SELECTION_NO_OUTCOMES' or trial.get('cohort_identity_frozen') is not False or trial.get('field_schedule_frozen') is not False or trial.get('outcomes_may_be_opened') is not False,'original downstream trial design promoted')
    effort=trial.get('effort',{})
    _fail_if((effort.get('visits_per_assigned_candidate'),effort.get('active_search_minutes_per_visit'),effort.get('observers_per_visit'),effort.get('planned_person_minutes_per_assigned_candidate'))!=(3,30,1,90),'frozen effort changed')
    _fail_if(exposure.get('candidate_pool_count')!=9 or exposure.get('ready_for_field_assignment_count')!=0 or exposure.get('independent_confirmatory_unit_count')!=0,'exposure gate altered')
    _fail_if(exposure.get('status')!='PUBLIC_REGISTRY_EXPOSURE_SCREEN_COMPLETE_NO_UNTOUCHED_COHORT_AUTHORIZED','unfrozen exposure report')
    return {'topology':topology,'trial':trial,'exposure':exposure}


def _nonnegative_int(value:Any,where:str)->int:
    if type(value) is not int or value<0 or value>2**53:
        raise ValueError(f'{where} must be a non-negative safe integer')
    return value


def summarize_public_preview(preview:dict[str,Any])->dict[str,Any]:
    """Analyze an UNAUTHENTICATED public-only design preview, not a visit plan."""
    if not isinstance(preview,dict) or set(preview)!=PREVIEW_FIELDS:
        raise ValueError('preview public-only schema unknown or contains private fields')
    if (preview.get('schema_version')!='acsp-connectivity-overlay-versus-geometry-site-trial-public-preview-v1'
        or preview.get('status')!='DESIGN_PREVIEW_ONLY_AWAITING_PRIVATE_GEOMETRY_AND_COHORT_PIN'):
        raise ValueError('not a method-design preview')
    for field in ('fresh_independent_biological_validation','field_outcomes_opened','field_schedule_frozen','real_candidate_geometry_used_now','actual_field_effect_estimated','original_three_arm_field_protocol_changed'):
        if preview.get(field) is not False:
            raise ValueError('preview must not claim field validation or opened results')
    if not isinstance(preview.get('private_assignments_sha256'),str) or re.fullmatch('[a-f0-9]{64}',preview['private_assignments_sha256']) is None:
        raise ValueError('missing opaque assignment digest')
    cohorts=preview.get('by_cohort')
    if not isinstance(cohorts,dict):raise ValueError('missing public cohort aggregates')
    aggregates={}
    sum_assigned=sum_reserved=sum_ineligible=0
    for name,values in sorted(cohorts.items()):
        if (not isinstance(name,str) or re.fullmatch('[A-Z0-9_]+',name) is None
                or not isinstance(values,dict) or set(values)!=COHORT_FIELDS):
            raise ValueError('invalid aggregate cohort schema')
        counts={k:_nonnegative_int(values[k],f'{name}.{k}') for k in COHORT_FIELDS if k!='cohort_exposure'}
        if values['cohort_exposure'] not in ('PREVIOUSLY_EXPOSED_DEVELOPMENT_ONLY','UNREGISTERED_NEW_COHORT_CONFIRMATION_NOT_YET_AUTHORIZED'):
            raise ValueError('unjustified cohort confirmation state')
        n=counts['assigned_topology']+counts['assigned_geometry']
        if counts['assigned_topology']!=counts['assigned_geometry']:
            raise ValueError('arms no longer balanced')
        if counts['planned_person_minutes_per_arm'] != counts['assigned_topology']*90:
            raise ValueError('effort mismatch in cohort')
        if counts['shared_counterfactual_count']>n:
            raise ValueError('shared counterfactual site count > assigned patches')
        if counts['balance_reserve_count']>1:
            raise ValueError('odd-patch reserve may contain at most one per cohort')
        distinct=n-counts['shared_counterfactual_count']
        ratio=distinct/n if n else None
        aggregates[name]={
            'assigned_patch_count':n,
            'distinct_site_choices':distinct,
            'identical_site_choices':counts['shared_counterfactual_count'],
            'site_choice_discordance_fraction':ratio,
            'max_abs_site_only_expected_binary_effect_if_same_site_has_equal_detection_process':ratio,
            'site_selection_first_stage':'NO_ASSIGNED_PATCHES' if n==0 else 'NONE_DIFFERENT_IN_PREVIEW' if distinct==0 else 'SOME_DIFFERENT_IN_PREVIEW',
            'planned_person_minutes_per_arm':counts['planned_person_minutes_per_arm'],
            'scheduled_active_person_hours_if_both_arms_visited':n*90/60,
            'balance_reserve_count':counts['balance_reserve_count'],
            'ineligible_connected_patch_count':counts['ineligible_connected_patch_count'],
            'cohort_exposure':values['cohort_exposure'],
        }
        sum_assigned+=n
        sum_reserved+=counts['balance_reserve_count']
        sum_ineligible+=counts['ineligible_connected_patch_count']
    for key,seen in (
        ('assigned_patch_count',sum_assigned),
        ('unassigned_odd_balance_reserve_count',sum_reserved),
        ('ineligible_connected_patch_count',sum_ineligible),
    ):
        if _nonnegative_int(preview[key],key)!=seen:
            raise ValueError(f'public aggregate total differs: {key}')
    return {
        'status':'SOURCE_UNAUTHENTICATED_DESIGN_PREVIEW_FIRST_STAGE_ONLY',
        'by_cohort':aggregates,
        'field_effect_estimated':False,
        'actual_site_source_authenticated':False,
        'independent_prospective_cohort_authorized':False,
        'field_schedule_frozen':False,
        'effect_bound_conditions':'Expected binary site-only contrast with equal observer/season/search process at identical proposed sites; NOT a bound on realized sampling noise or on field protocols with arm-specific behavior',
    }


def generate_public_report() -> dict[str,Any]:
    """Only previous historical DEVELOPMENT aggregation plus unknown future q."""
    source=read_bound_sources()
    topology=source['topology']
    rows={};total_eligible=total_visited=total_minutes=0
    for unit in UNITS:
        t=topology['units'][unit]
        eligible=_nonnegative_int(t['disconnected_patch_count'],f'{unit}.disconnected_patch_count')
        patches=_nonnegative_int(t['complete_link_patch_count'],f'{unit}.complete_link_patch_count')
        if eligible>patches:raise ValueError('historical patch count drift')
        reserve=eligible%2
        visited=eligible-reserve
        per_arm=visited//2
        person_minutes=visited*90
        rows[unit]={
            'historical_internally_disconnected_patches':eligible,
            'historical_all_patches':patches,
            'counterfactual_full_frame_assigned_patches':visited,
            'counterfactual_even_arm_sites_each':per_arm,
            'counterfactual_odd_balance_reserve':reserve,
            'planned_person_minutes_if_every_assigned_patch_searched':person_minutes,
            'planned_person_hours':person_minutes/60,
            'actual_site_selection_discordance':None,
            'source_verified_for_new_independent_trial':False,
        }
        total_eligible+=eligible
        total_visited+=visited
        total_minutes+=person_minutes
    return {
        'schema_version':'cirsium-topology-site-selection-first-stage-feasibility-v1',
        'status':STATUS,
        'sources':{str(k):v for k,v in SOURCE_BLOBS.items()},
        'historical_full_frame_counterfactual_only':{
            'units':rows,
            'total_internally_disconnected_patches':total_eligible,
            'total_unique_sites_if_all_assigned':total_visited,
            'total_person_minutes_if_all_assigned':total_minutes,
            'total_active_person_hours_if_all_assigned':total_minutes/60,
            'all_four_units_are_independent_biological_replicates':False,
            'any_actual_visits_authorized':False,
            'survey_days_cost_travel_access_or_phenology_included':False,
            'interpretation':'Hypothetical exhaustive workload for PREVIOUSLY DEVELOPED topology configurations, NOT required sample size or an authorized schedule',
        },
        'future_independent_trial':{
            'independent_cohort_count_confirmed':source['exposure']['independent_confirmatory_unit_count'],
            'field_assignments_authorized':False,
            'actual_new_taxon_sector_patch_count':None,
            'actual_new_taxon_sector_discordant_site_fraction':None,
            'effective_method_first_stage_identified':False,
            'next_input':'Authenticated source-complete private patch members, new disjoint taxon/sector registry and symmetrical permissions/access review, all BEFORE prospective outcomes',
        },
        'mathematics':{
            'assigned_site_discordance_fraction':'q = number of assigned patches whose two pre-outcome representative cells differ / number of assigned patches',
            'site_only_binary_expected_effect_bound':'absolute mean(Y_topology-Y_geometry) <= q IF equal effort and identical-site detection process have the same expected response',
            'not_an_observed_field_effect':True,
            'sampling_noise_not_bounded_by_q':True,
        },
        'claims':{
            'field_efficiency_established':False,
            'validated_patch_generator_changed':False,
            'field_outcomes_opened':False,
            'full_structural_order_replay_repaired':False,
            'retained_mask_components_equal_real_habitat':False,
            'all_patches_should_be_visited':False,
        },
    }


def write_public_json(path:Path,result:dict[str,Any])->None:
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:
        json.dump(result,f,ensure_ascii=False,indent=2,sort_keys=True)
        f.write('\n')


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out-json',type=Path)
    p.add_argument('--verify-saved',type=Path)
    p.add_argument('--synthetic-public-preview',type=Path,
                   help='optional synthetic-only design preview; no actual site/field authority')
    a=p.parse_args()
    result=generate_public_report()
    if a.synthetic_public_preview is not None:
        # Avoid giving real preview data a falsely authoritative filename here:
        if a.synthetic_public_preview.name!='synthetic_topology_site_preview.json':
            raise ValueError('only a clearly labeled synthetic preview is permitted')
        result['example_synthetic_preview']=summarize_public_preview(json.loads(a.synthetic_public_preview.read_text()))
    if a.verify_saved is not None:
        saved=json.loads(a.verify_saved.read_text(encoding='utf-8'))
        if saved!=result:raise ValueError('saved result differs from original frozen source computations')
    if a.out_json is not None:
        write_public_json(a.out_json,result)
    print(json.dumps({'status':result['status'],
                      'historical_hypothetical_person_hours':result['historical_full_frame_counterfactual_only']['total_active_person_hours_if_all_assigned'],
                      'independent_cohort_ready':False},sort_keys=True))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
