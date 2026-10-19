#!/usr/bin/env python3
"""Demonstrate that frozen component-count summaries do not identify site-choice q.

The only coordinate pairs in this file are tiny, explicitly fabricated integer
lattice examples, never actual study sites. Original published data enters only
via exact Git blob SHA-1 fingerprints of existing public summary JSONs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from research.design_cirsium_patch_connectivity_field_trial_v1 import (
    choose_counterfactual_sites,
    connected_components,
)

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_SOURCE_BLOBS = {
    'research/design_cirsium_patch_connectivity_field_trial_v1.py': '7a010f45b7ab0802611389fd0f584f300eabe0ee',
    'validation/coverage_then_fine_structure_patch_connectivity_field_trial_design_v1.json': 'ec18c79b126b994a47c9680e5098548e655f88c9',
    'validation/coverage_then_fine_structure_fresh_sentinel_v2_patch_topology_component_gap_v1.json': '06b7dbd6e1152e8187a7ecd31ee6ab4b5778d0f6',
}
# Fictitious unit-grid masks only. Each consists of three 8-neighbour-connected
# cells and one isolated cell; the first geometry chooses the SAME medoid,
# the second chooses a DIFFERENT original retained-cell medoid.
SYNTHETIC_MASKS: dict[str, frozenset[tuple[int,int]]] = {
    'IDENTICAL_SITE_CHOICE': frozenset(((0,0),(0,1),(0,2),(4,1))),
    'DISTINCT_SITE_CHOICE': frozenset(((0,0),(0,1),(0,2),(4,4))),
}
UNITS = ('CIR02','CIR06','CIR12','CIR13')


def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b'blob '+str(len(data)).encode('ascii')+b'\0'+data).hexdigest()


def _source_locked_json() -> dict[str, Any]:
    for path, sha in ORIGINAL_SOURCE_BLOBS.items():
        target = ROOT/path
        if target.is_symlink() or not target.is_file() or _git_blob_sha(target.read_bytes()) != sha:
            raise ValueError('original source git blob drifted: '+path)
    original = json.loads((ROOT/'validation/coverage_then_fine_structure_fresh_sentinel_v2_patch_topology_component_gap_v1.json').read_text(encoding='utf-8'))
    contract = json.loads((ROOT/'validation/coverage_then_fine_structure_patch_connectivity_field_trial_design_v1.json').read_text(encoding='utf-8'))
    if original.get('status') != 'POSTHOC_DESCRIPTIVE_SYNTHESIS_OF_PREVIOUSLY_FROZEN_TOPOLOGY' or set(original.get('units',{}))!=set(UNITS):
        raise ValueError('original topology source status/cohort changed')
    if (contract.get('status') != 'METHOD_DESIGN_FROZEN_BEFORE_NEW_COHORT_SELECTION_NO_OUTCOMES'
            or contract.get('cohort_identity_frozen') is not False
            or contract.get('field_schedule_frozen') is not False
            or contract.get('outcomes_may_be_opened') is not False):
        raise ValueError('original design was unexpectedly promoted')
    if (original['source'].get('support_fraction') != 0.025
            or original['source'].get('patch_complete_link_diameter_m') != 1000
            or contract['sampling'].get('grid_spacing_m') != 100):
        raise ValueError('original support/geometry scales changed')
    return original


def _synthetic_signature(points: frozenset[tuple[int,int]]) -> dict[str,int]:
    comps = connected_components(set(points))
    if len(points)!=4 or len(comps)!=2 or sorted(map(len,comps))!=[1,3]:
        raise ValueError('synthetic disconnected fragment signature drifted')
    if max((a[0]-b[0])**2+(a[1]-b[1])**2 for a in points for b in points)>100:
        raise ValueError('synthetic patch exceeds frozen 1-km / 100m grid bound')
    return {
        'retained_support_cells':len(points),
        'complete_link_patch_count':1,
        'disconnected_patch_count':1,
        'global_mask_component_count':len(comps),
        'within_patch_component_total':len(comps),
        'extra_within_patch_components':len(comps)-1,
        'maximum_components_per_patch':len(comps),
        'singleton_patch_count':0,
        'largest_component_size':max(map(len,comps)),
    }


def generate_report() -> dict[str, Any]:
    original = _source_locked_json()
    examples=[]
    for label,points in SYNTHETIC_MASKS.items():
        unit='SYNTHETIC_ONLY'
        private={'cohort_unit_id':unit,'patch_ref':label,
                 'member_ids':[f'{unit}_r{r}_c{c}' for r,c in sorted(points)]}
        selected=choose_counterfactual_sites(private)
        if selected['eligible_disconnected'] is not True:
            raise ValueError('fictitious grid example is not disconnected')
        examples.append({
            'synthetic_example_label':label,
            'synthetic_topology_signature':_synthetic_signature(points),
            'site_choice_discordance_q':int(not selected['counterfactual_site_shared']),
            'actual_field_outcome_used':False,
        })
    if examples[0]['synthetic_topology_signature']!=examples[1]['synthetic_topology_signature']:
        raise ValueError('counterexamples do not preserve their aggregate signatures')
    if [a['site_choice_discordance_q'] for a in examples] != [0,1]:
        raise ValueError('selected medoids no longer demonstrate nonidentification')
    bounds={}
    for unit in UNITS:
        x=original['units'][unit]
        n,d=x.get('complete_link_patch_count'),x.get('disconnected_patch_count')
        if type(n) is not int or type(d) is not int or n<1 or not 0<=d<=n:
            raise ValueError('original frozen count invalid')
        bounds[unit]={
            'original_patch_count':n,
            'internally_disconnected_patch_count':d,
            'unconditional_q_lower_bound':0.0,
            'unconditional_q_upper_bound':d/n,
            'eligible_disconnected_only_q_interval':[0.0,1.0] if d>0 else None,
            'actual_site_choice_discordance_q':None,
            'original_units_are_method_development_not_new_independent_confirmation':True,
        }
    return {
        'schema_version':'cirsium-site-choice-aggregate-nonidentifiability-v1',
        'status':'SOURCE_BOUND_SYNTHETIC_SITE_CHOICE_NOT_IDENTIFIED',
        'original_source_blobs':dict(ORIGINAL_SOURCE_BLOBS),
        'proof_scope':'two fabricated 100m lattice patches; same 1km complete-link bound and same graph summaries but q=0 vs q=1',
        'synthetic_counterexamples':examples,
        'original_development_aggregate_envelopes':bounds,
        'mathematical_readout':{
            'nonidentification':'published component/patch counts alone cannot generally recover medoid-site discordance q',
            'all_patch_population_bound':'0 <= q_all_patches <= fraction(internally disconnected original patches)',
            'disconnected_only_population_bound':'if any disconnected patches exist: 0 <= q_eligible_only <= 1',
            'why':'connected patches yield identical two medoids, but disconnected patch topology counts do not determine representative cell identity',
            'bounds_are_not_measured_q':True,
            'full_historical_four_unit_q_inferred':False,
            'real_new_cohort_q_inferred':False,
        },
        'future_independent_trial':{
            'actual_new_cohort_q':None,
            'source_complete_private_patch_memberships_verified':False,
            'field_eligibility_authorized':False,
            'prospective_outcomes_opened':False,
        },
        'scientific_limits':{
            'new_independent_biological_confirmation':False,
            'validated_2p5percent_1km_robust_core_changed':False,
            'frozen_three_arm_field_protocol_changed':False,
            'sampled_original_private_candidate_geometry':False,
            'real_field_discovery_effect_estimated':False,
        },
    }


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    a=p.add_mutually_exclusive_group(required=True)
    a.add_argument('--out-json',type=Path)
    a.add_argument('--verify-saved',type=Path)
    args=p.parse_args()
    obj=generate_report()
    if args.verify_saved:
        if json.loads(args.verify_saved.read_text(encoding='utf-8')) != obj:
            raise ValueError('saved nonidentification result is not reproduced from frozen sources')
        print(json.dumps({'status':'FROZEN_NONIDENTIFICATION_RESULT_REPRODUCED','unit_count':4}))
    else:
        if args.out_json.exists() or args.out_json.is_symlink():
            raise ValueError('refusing to overwrite a synthetic-only result')
        args.out_json.parent.mkdir(parents=True,exist_ok=True)
        args.out_json.write_text(json.dumps(obj,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
        print(json.dumps({'status':obj['status'],'synthetic_examples':2,'original_development_units':4}))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
