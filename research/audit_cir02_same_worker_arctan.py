#!/usr/bin/env python3
"""Post-observation same-worker intervention on CIR02 original arctan float32 arrays.

Private full-array magnitudes and cell IDs never leave the job or appear in
public JSON. The sampled cells and original parent hashes are not reselected.
This is a numerical mechanism experiment, not a field/selector validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from typing import Any

import numpy as np

from research.cir02_angle_operators import CHUNKS, _sha256_file, runtime_metadata

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / 'validation/coverage_then_fine_structure_fresh_sentinel_v2_cir02_same_worker_arctan_intervention_v1.json'
MODES = ('original', 'avx512f_disabled')
OPS = ('gradient_magnitude', 'arctan_radians', 'instantaneous_slope')
PRECISIONS = (2, 8)


def validate_contract() -> dict[str, Any]:
    v = json.loads(CONTRACT.read_text(encoding='utf-8'))
    src, sample, cpu, science = (v.get(k,{}) for k in ('source_world','sample','cpu_intervention','scientific_scope'))
    if (v.get('status') != 'FROZEN_BEFORE_REAL_SAME_WORKER_CPU_INTERVENTION'
            or src.get('unit') != 'CIR02'
            or src.get('original_candidate_rows') != 464633
            or src.get('gsi_source_complete_rows') != 383460
            or src.get('selected_source_dem_chunks') != 177
            or tuple(sample.get('original_chunks',())) != CHUNKS
            or sample.get('source_complete_per_chunk') != 24
            or sample.get('total_sampled_original_cells') != 72
            or cpu.get('only_disabled_feature') != 'AVX512F'
            or cpu.get('fresh_process_repeats_per_mode') != 2
            or cpu.get('required_historical_numpy') != '2.4.6'
            or cpu.get('required_historical_python') != '3.11.17'
            or any(cpu.get(k) is not True for k in (
                'same_runner_job', 'original_mode_must_match_parent_source_observer',
                'input_arrays_sha_identical_between_modes',
                'compare_only_arctan_on_exact_same_full_float32_magnitude_file_bytes',
                'archive_only_aggregate_hashes_and_operator_loop_metadata'))
            or any(science.get(k) is not True for k in (
                'no_field_outcomes_or_exact_locations_public', 'no_raw_dem_or_private_arrays_in_artifact',
                'no_2p5pct_or_1km_selector_rule_changed',
                'diagnostic_designed_after_original_arctan_discrepancy'))
            or science.get('cpu_dispatch_causes_historical_rank_change_established') is not False):
        raise ValueError('original CIR02 same-worker intervention contract changed')
    return v


def _hashers() -> tuple[dict[str, Any], dict[str, dict[int, Any]]]:
    exact = {op: hashlib.sha256(f'CIR02_ANGLE_{op}_EXACT_V1\n'.encode()) for op in OPS}
    rounded = {op: {p: hashlib.sha256(f'CIR02_ANGLE_{op}_DECIMAL_{p}_V1\n'.encode())
                    for p in PRECISIONS} for op in OPS}
    return exact, rounded


def _valid_entries(entries: list[dict[str, Any]]) -> None:
    if len(entries) != len(CHUNKS) or tuple(x.get('chunk_index') for x in entries) != CHUNKS:
        raise ValueError('original chunk count/order changed')
    used: set[str] = set()
    for x in entries:
        ids = x.get('ids')
        rr, cc, arr = x.get('rows'), x.get('cols'), x.get('magnitude')
        if (not isinstance(ids, list) or len(ids) != 24
                or any(not isinstance(t, str) or not t or '\n' in t or '\t' in t for t in ids)
                or ids != sorted(ids) or len(set(ids)) != 24 or set(ids) & used):
            raise ValueError('24 original IDs must be unique, sorted and unchanged')
        used.update(ids)
        if (not isinstance(arr, np.ndarray) or arr.dtype != np.dtype('float32')
                or arr.ndim != 2 or not isinstance(rr, np.ndarray) or not isinstance(cc, np.ndarray)
                or rr.shape != (24,) or cc.shape != (24,)
                or rr.dtype.kind not in 'iu' or cc.dtype.kind not in 'iu'
                or not np.all((rr >= 0) & (rr < arr.shape[0]) & (cc >= 0) & (cc < arr.shape[1]))
                or not np.isfinite(arr[rr,cc]).all()):
            raise ValueError('original full float32 magnitude/raster shape or sample changed')


def evaluate_loop_change(original: dict[str, Any], disabled: dict[str, Any]) -> bool | None:
    if original.get('status') != 'reported' or disabled.get('status') != 'reported':
        return None
    orig = original.get('loops',{}).get('ff',{}).get('current')
    down = disabled.get('loops',{}).get('ff',{}).get('current')
    if not orig or not down:
        return None
    return str(orig) != str(down)


def _digest_manifest(entries: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    if mode not in MODES:
        raise ValueError('unknown intervention mode')
    expected_flag = None if mode == 'original' else 'AVX512F'
    if (os.environ.get('NPY_DISABLE_CPU_FEATURES') or None) != expected_flag:
        raise ValueError('intervention child CPU flag was not set before NumPy import')
    digesters, rounded = _hashers()
    identities = hashlib.sha256(b'CIR02_ANGLE_SAMPLE_IDENTITIES_V1\n')
    count = 0
    sha_bytes = hashlib.sha256(b'CIR02_PRIVATE_FULL_MAGNITUDE_INPUTS_V1\n')
    for x in entries:
        path = Path(x['private_full_magnitude_npy'])
        if path.is_symlink() or not path.is_file():
            raise ValueError('original ephemeral private magnitude missing')
        actual_sha = _sha256_file(path)
        if actual_sha != x['private_full_magnitude_sha256']:
            raise ValueError('original private magnitude bytes changed')
        sha_bytes.update(f"{x['chunk_index']}\t{actual_sha}\n".encode())
        original = np.load(path, allow_pickle=False, mmap_mode='r')
        if original.dtype != np.dtype('float32') or original.ndim != 2:
            raise ValueError('original full float32 magnitude changed')
        rr, cc = np.asarray(x['rows'], dtype=np.int64), np.asarray(x['cols'], dtype=np.int64)
        if (len(x['ids']) != 24 or rr.shape != (24,) or cc.shape != (24,)
                or not np.all((rr >= 0) & (rr < original.shape[0]) & (cc >= 0) & (cc < original.shape[1]))):
            raise ValueError('private original sample missing or outside fixed raster')
        radians = np.arctan(original)
        degrees = np.degrees(radians)
        arrays = (('gradient_magnitude', original), ('arctan_radians', radians),
                  ('instantaneous_slope', degrees))
        for i, ident in enumerate(x['ids']):
            if not isinstance(ident, str) or not ident or '\n' in ident or '\t' in ident:
                raise ValueError('bad original sampled ID')
            identities.update(f"{x['chunk_index']}\t{ident}\n".encode())
            prefix = ident.encode('utf-8') + b'\t'
            for op, arr in arrays:
                numeric = float(arr[rr[i],cc[i]])
                if not np.isfinite(numeric):
                    raise ValueError('nonfinite originally complete numerical sample')
                digesters[op].update(prefix + struct.pack('<d',numeric) + b'\n')
                for p in PRECISIONS:
                    rounded[op][p].update(prefix + format(numeric, f'.{p}f').encode('ascii') + b'\n')
        count += len(x['ids'])
    if count != 72:
        raise ValueError('original sampled 3x24 denominator changed')
    native = runtime_metadata()
    native['disabled_cpu_features'] = expected_flag
    native['cpu_flags_changed_by_instrument'] = expected_flag is not None
    return {
        'mode':mode,'sampled_cells':count,
        'full_magnitude_byte_sequence_sha256':sha_bytes.hexdigest(),
        'sampled_candidate_identity_sha256':identities.hexdigest(),
        'operators_exact_float64_sha256':{k:v.hexdigest() for k,v in digesters.items()},
        'operators_decimal_sha256':{k:{str(p):h.hexdigest() for p,h in pp.items()}
                                      for k,pp in rounded.items()},
        'runtime':native,
    }


def run_intervention(entries: list[dict[str,Any]], parent: dict[str,Any]) -> dict[str,Any]:
    validate_contract()
    _valid_entries(entries)
    if os.environ.get('NPY_DISABLE_CPU_FEATURES'):
        raise ValueError('parent CPU feature flags are already overridden')
    if (parent.get('status') != 'CIR02_ANGLE_SUBSTAGES_COMPLETE'
            or parent.get('source_complete_cells_probed') != 72
            or parent.get('parent_original_diagnostic_bound') is not True):
        raise ValueError('original parent operator record unbound or incomplete')
    with tempfile.TemporaryDirectory(prefix='acsp-cir02-private-arctan-') as temp:
        private = []
        for row in entries:
            target = Path(temp) / f"full-magnitude-{row['chunk_index']}.npy"
            np.save(target, np.ascontiguousarray(row['magnitude'],dtype=np.float32),allow_pickle=False)
            target.chmod(0o600)
            private.append(dict(chunk_index=row['chunk_index'],ids=row['ids'],
                rows=row['rows'].tolist(),cols=row['cols'].tolist(),
                private_full_magnitude_npy=str(target),
                private_full_magnitude_sha256=_sha256_file(target)))
        payload=json.dumps(private)
        mode_runs={}
        for mode in MODES:
            env=os.environ.copy()
            env.pop('NPY_DISABLE_CPU_FEATURES',None)
            if mode=='avx512f_disabled': env['NPY_DISABLE_CPU_FEATURES']='AVX512F'
            results=[]
            for _ in range(2):
                p=subprocess.run([sys.executable,'-m','research.audit_cir02_same_worker_arctan',
                    '--child',mode],input=payload,text=True,capture_output=True,env=env,
                    cwd=str(Path(__file__).resolve().parents[1]),timeout=180,check=False)
                if p.returncode!=0:
                    # Do NOT echo stderr or the private manifest in public logs.
                    raise ValueError('private same-worker arctan child failed (details withheld)')
                try: result=json.loads(p.stdout)
                except (ValueError,TypeError) as exc:
                    raise ValueError('child returned invalid public aggregate') from exc
                results.append(result)
            if results[0]!=results[1]:
                raise ValueError('same-mode arctan repeats differ')
            mode_runs[mode]=results[0]
    one,two=mode_runs['original'],mode_runs['avx512f_disabled']
    for mode in mode_runs.values():
        if (mode['sampled_cells']!=72
                or mode['sampled_candidate_identity_sha256']!=parent.get('sampled_candidate_identity_sha256')):
            raise ValueError('original parent identities or sample count differ after intervention')
    if one['full_magnitude_byte_sequence_sha256']!=two['full_magnitude_byte_sequence_sha256']:
        raise ValueError('same-worker magnitude source bytes changed')
    for name in OPS:
        if one['operators_exact_float64_sha256'][name] != parent['operators_exact_float64_sha256'][name]:
            raise ValueError('original parent operator hashes differ before intervention')
        for p in ('2','8'):
            if one['operators_decimal_sha256'][name][p]!=parent['operators_decimal_sha256'][name][p]:
                raise ValueError('original parent decimal hashes differ before intervention')
    if one['runtime']['numpy_extension_sha256']!=two['runtime']['numpy_extension_sha256']:
        raise ValueError('NumPy extension binary changed between modes')
    if one['runtime']['python']!=two['runtime']['python'] or one['runtime']['numpy']!=two['runtime']['numpy']:
        raise ValueError('intervention changed Python/NumPy versions')
    if one['operators_exact_float64_sha256']['gradient_magnitude'] != two['operators_exact_float64_sha256']['gradient_magnitude']:
        raise ValueError('fixed original magnitude was numerically changed')
    a=one['runtime']['operator_dispatch']['arctan']
    b=two['runtime']['operator_dispatch']['arctan']
    changed=evaluate_loop_change(a,b)
    equal={name:one['operators_exact_float64_sha256'][name]==two['operators_exact_float64_sha256'][name]
            for name in OPS}
    if changed is True and not equal['arctan_radians']:
        readout='SAME_WORKER_ARCTAN_DISPATCH_EFFECT_ON_SAMPLED_VALUES_OBSERVED'
    elif changed is True:
        readout='DISPATCH_CHANGED_NO_SAMPLED_ARCTAN_OUTPUT_DIFFERENCE'
    else:
        readout='DISPATCH_INTERVENTION_NOT_DISTINGUISHABLE_ON_THIS_WORKER'
    return {
        'schema_version':'cir02-real-same-worker-arctan-dispatch-intervention-v1',
        'status':'SOURCE_BOUND_SAME_WORKER_ARCTAN_INTERVENTION_COMPLETED_POST_OBSERVATION',
        'sampled_cells':72,'source_chunk_count':177,'sampled_chunks':[0,88,176],
        'same_worker_source_magnitudes_fixed':True,
        'same_python_numpy_extension_for_modes':True,
        'original_mode_matches_parent_operator_hashes':True,
        'same_mode_repeats_exact':True,
        'modes':mode_runs,
        'comparison':{
            'gradient_magnitude_exact_equal':equal['gradient_magnitude'],
            'sampled_candidate_identity_sha_equal':True,
            'arctan_radians_exact_equal':equal['arctan_radians'],
            'instantaneous_slope_exact_equal':equal['instantaneous_slope'],
            'arctan_loop_changed':changed,
            'first_differing_exact_operator':'arctan_radians' if changed and not equal['arctan_radians'] else None,
            'arctan_radians_decimal8_equal':one['operators_decimal_sha256']['arctan_radians']['8']==two['operators_decimal_sha256']['arctan_radians']['8'],
            'arctan_radians_decimal2_equal':one['operators_decimal_sha256']['arctan_radians']['2']==two['operators_decimal_sha256']['arctan_radians']['2'],
        },
        'causal_readout':readout,
        'within_worker_intervention_implemented':True,
        'scope':'post-observation 3 chunks x 24 original CIR02 source-complete cells',
        'field_outcomes_opened':False,
        'full_177_chunk_numeric_replay_claimed':False,
        'original_gsi_pipeline_modified':False,
        'original_frozen_patch_selector_changed':False,
        'private_values_or_ids_exported':False,
    }


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--child',choices=MODES,required=True)
    opts=p.parse_args()
    # Important: NumPy is imported at module import, *after* the subprocess
    # environment's NPY_DISABLE_CPU_FEATURES was assigned by its parent.
    content=json.loads(sys.stdin.read())
    if not isinstance(content,list) or len(content)!=3:
        raise ValueError('private original manifest is incomplete')
    print(json.dumps(_digest_manifest(content,opts.child),allow_nan=False))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
