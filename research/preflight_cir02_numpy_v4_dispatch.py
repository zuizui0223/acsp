#!/usr/bin/env python3
"""CPU-only NumPy 2.4.6 X86_V4 runtime flag feasibility before any new real GSI experiment.

No site, DEM, observation, geographic input or external dataset is accessed.
Process-scoped environment variables are set BEFORE each child imports NumPy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
CONTRACT=ROOT/'validation/coverage_then_fine_structure_fresh_sentinel_v2_cir02_numpy24_x86v4_preflight_v1.json'
MODES=('original','x86_v4_disabled')


def validate_contract() -> dict:
    contract=json.loads(CONTRACT.read_text(encoding='utf-8'))
    required={'status':'FROZEN_BEFORE_NUMPY_2_4_NATIVE_X86_V4_CPU_PREFLIGHT',
              'source_kind':'SYNTHETIC_CPU_ONLY_NO_GSI',
              'numpy_version':'2.4.6','python_version':'3.11.17',
              'disable_only_feature':'X86_V4','repeats_per_mode':2}
    if any(contract.get(k)!=v for k,v in required.items()):
        raise ValueError('NumPy native V4 preflight contract changed')
    for name in ('forbid_real_dem_or_field_records', 'v1_avx512f_source_result_is_immutable',
                 'selected_loop_must_actually_change_before_next_real_dem_acquisition',
                 'do_not_require_numerical_effect_on_synthetic_values_for_hardware_eligibility',
                 'no_positive_outcome_based_hardware_resampling'):
        if contract.get(name) is not True:
            raise ValueError('unsafe native V4 preflight contract')
    return contract


def classify_original_and_disabled(original:dict,disabled:dict)->dict:
    if original.get('mode')!='original' or disabled.get('mode')!='x86_v4_disabled':
        raise ValueError('wrong original or disabled mode')
    for name in ('python','numpy','binary_sha256','source_sha256'):
        if original.get(name)!=disabled.get(name):
            raise ValueError('synthetic source/runtime mismatch in preflight: '+name)
    if original.get('python')!='3.11.17' or original.get('numpy')!='2.4.6':
        raise ValueError('native preflight must use the original Python 3.11.17 and NumPy 2.4.6')
    first,second=original.get('arctan_loop'),disabled.get('arctan_loop')
    if not first or not second or first=='not_reported' or second=='not_reported':
        status='DISPATCH_LOOP_NOT_REPORTED'
    elif first!='X86_V4':
        status='NATIVE_WORKER_NOT_RUNNING_X86_V4'
    elif second=='X86_V4':
        status='NATIVE_X86_V4_OVERRIDE_UNEFFECTIVE'
    else:
        status='NATIVE_X86_V4_DISPATCH_SWITCH_CONFIRMED'
    return {'readout':status,'loop_changed':bool(first and second and first!=second),
            'synthetic_arctan_exact_equal':
                original.get('arctan_exact_sha256')==disabled.get('arctan_exact_sha256'),
            'eligible_for_separately_frozen_original_source_trial':
                status=='NATIVE_X86_V4_DISPATCH_SWITCH_CONFIRMED'}


def run_child(mode:str)->dict:
    if mode not in MODES:
        raise ValueError('unsupported native preflight mode')
    expected=None if mode=='original' else 'X86_V4'
    if (os.environ.get('NPY_DISABLE_CPU_FEATURES') or None)!=expected:
        raise ValueError('CPU override differs from prospective X86_V4 intervention')
    # First NumPy import in the child process occurs AFTER the above process env check.
    import numpy as np
    import numpy._core._multiarray_umath as native
    from numpy.lib.introspect import opt_func_info
    if np.__version__!='2.4.6' or sys.version_info[:3]!=(3,11,17):
        raise ValueError('native NumPy/Python versions do not match prospective protocol')
    x=np.linspace(np.float32(1e-5),np.float32(10.0),100000,dtype=np.float32)
    if x.dtype!=np.dtype('float32') or x.size!=100000:
        raise ValueError('synthetic fixed input changed')
    y=np.arctan(x)
    if y.dtype!=np.float32:
        raise ValueError('native float32 arctan unexpectedly promoted dtype')
    loops=opt_func_info(func_name='^arctan$',signature='float32')
    selected=loops.get('arctan',{}).get('ff',{}).get('current','not_reported')
    digest=lambda data:hashlib.sha256(data).hexdigest()
    return {
        'mode':mode,'python':f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}',
        'numpy':np.__version__,
        'binary_sha256':digest(Path(native.__file__).read_bytes()),
        'source_sha256':digest(x.tobytes()),
        'arctan_exact_sha256':digest(y.tobytes()),
        'arctan_loop':selected,
    }


def run_preflight()->dict:
    validate_contract()
    mode_data={}
    for mode in MODES:
        env=os.environ.copy();env.pop('NPY_DISABLE_CPU_FEATURES',None)
        if mode=='x86_v4_disabled':env['NPY_DISABLE_CPU_FEATURES']='X86_V4'
        replays=[]
        for _ in range(2):
            proc=subprocess.run([sys.executable,'-m','research.preflight_cir02_numpy_v4_dispatch',
                                 '--child',mode],cwd=str(ROOT),env=env,
                                capture_output=True,text=True,timeout=120,check=False)
            if proc.returncode:
                raise ValueError('native V4 child failed (private process details not exported)')
            try:replays.append(json.loads(proc.stdout))
            except json.JSONDecodeError as exc:
                raise ValueError('native V4 child did not report a valid JSON summary') from exc
        if replays[0]!=replays[1]:
            raise ValueError('two repeats in one CPU mode did not reproduce exactly')
        mode_data[mode]=replays[0]
    conclusion=classify_original_and_disabled(mode_data['original'],mode_data['x86_v4_disabled'])
    return {'schema_version':'cirsium-numpy24-x86-v4-dispatch-preflight-result-v1',
            'status':'NATIVE_CPU_ONLY_PREFLIGHT_COMPLETE','source_kind':'SYNTHETIC_CPU_ONLY_NO_GSI',
            'modes':mode_data,'comparison':conclusion,
            'same_worker_fresh_processes':True,
            'same_mode_repeats_exact':True,
            'intervention_flag':'X86_V4',
            'real_original_gsi_input_used':False,
            'scientific_claim':'native CPU dispatch feasibility only, not a real CIR02 numerical effect'}


def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--child',choices=MODES)
    group.add_argument('--out-json',type=Path)
    args=parser.parse_args()
    if args.child:
        print(json.dumps(run_child(args.child),sort_keys=True))
        return 0
    if args.out_json.exists() or args.out_json.is_symlink():
        raise ValueError('refusing to overwrite a preflight result')
    report=run_preflight()
    args.out_json.parent.mkdir(parents=True,exist_ok=True)
    args.out_json.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'comparison':report['comparison']}))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
