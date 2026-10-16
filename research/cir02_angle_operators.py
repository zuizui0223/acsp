"""Read-only supplementary angle diagnostic; never a production replacement.

Compute on full native float32 grids before sampling. Only aggregate hashes are
returned publicly; IDs, raster indices and numeric arrays stay in-process.
"""
from __future__ import annotations
import hashlib
import importlib
import json
import platform
import struct
from pathlib import Path
from typing import Any

import numpy as np

OPERATORS = ('dx_squared', 'dy_squared', 'squared_sum', 'gradient_magnitude',
             'arctan_radians', 'instantaneous_slope')
CHUNKS = (0, 88, 176)
DECIMALS = (2, 8)


def angle_arrays(dx: np.ndarray, dy: np.ndarray,
                 expected_angle: np.ndarray) -> dict[str, np.ndarray]:
    """Split the original expression without promotion, sampling, or CPU changes."""
    if any(not isinstance(a, np.ndarray) or a.dtype != np.dtype('float32')
           for a in (dx, dy, expected_angle)):
        raise ValueError('original full float32 arrays required; never silently cast')
    if dx.ndim != 2 or dx.shape != dy.shape or dx.shape != expected_angle.shape:
        raise ValueError('original two-dimensional gradient shapes must agree')
    if any(np.isinf(a).any() for a in (dx, dy, expected_angle)):
        raise ValueError('infinite original arrays forbidden')
    # Preserve the expression tree, native dtype and full-array SIMD/tail context.
    with np.errstate(invalid='ignore', over='raise'):
        dx2 = dx * dx
        dy2 = dy * dy
        total = dx2 + dy2
        magnitude = np.sqrt(total)
        radians = np.arctan(magnitude)
        degrees = np.degrees(radians)
    if not np.array_equal(degrees, expected_angle, equal_nan=True):
        raise ValueError('six-operator mirror differs from parent instantaneous_slope')
    return dict(zip(OPERATORS, (dx2, dy2, total, magnitude, radians, degrees)))


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def runtime_metadata() -> dict[str, Any]:
    """Observe runtime loop choices; absence of introspection is not 'baseline'."""
    names = ('multiply', 'add', 'sqrt', 'arctan', 'degrees')
    result: dict[str, Any] = {
        'python': platform.python_version(), 'numpy': np.__version__,
        'machine': platform.machine(), 'libc': list(platform.libc_ver()),
        'numpy_extension_sha256': None, 'operator_dispatch': {},
        'cpu_flags_changed_by_instrument': False,
    }
    try:
        ext = importlib.import_module('numpy._core._multiarray_umath')
        result['numpy_extension_sha256'] = _sha256_file(Path(ext.__file__))
    except (ImportError, AttributeError, TypeError, OSError):
        result['numpy_extension_status'] = 'unavailable'
    try:
        introspect = importlib.import_module('numpy.lib.introspect')
        raw = introspect.opt_func_info(
            func_name='^(multiply|add|sqrt|arctan|degrees)$', signature='float32')
    except (ImportError, AttributeError, TypeError, ValueError):
        result['operator_dispatch'] = {
            n: {'status': 'unavailable', 'loops': {}} for n in names}
        return result
    for name in names:
        loops = {
            sig: {'current': str(v.get('current', '')), 'available': str(v.get('available', ''))}
            for sig, v in raw.get(name, {}).items() if isinstance(v, dict)
        }
        result['operator_dispatch'][name] = {
            'status': 'reported' if loops else 'not_reported', 'loops': loops}
    return result


class AngleProbe:
    """Strict 3x24 aggregate recorder. Caller must use original source selection.

    This class alone does not authenticate a real workflow or a candidate grid.
    The integration callback binds it to the original observer and source gates.
    """
    def __init__(self) -> None:
        self._seen: list[int] = []
        self._count = 0
        self._ids: set[str] = set()
        self._source = hashlib.sha256(b'CIR02_SELECTED_3_CHUNKS_SOURCE_CONTENT_V1\n')
        self._identities = hashlib.sha256(b'CIR02_ANGLE_SAMPLE_IDENTITIES_V1\n')
        self._exact = {n: hashlib.sha256(f'CIR02_ANGLE_{n}_EXACT_V1\n'.encode())
                       for n in OPERATORS}
        self._rounded = {n: {p: hashlib.sha256(f'CIR02_ANGLE_{n}_DECIMAL_{p}_V1\n'.encode())
                             for p in DECIMALS} for n in OPERATORS}
        self._parent_grad = {
            n: hashlib.sha256(f'CIR02_REAL_SLOPE_STAGE_{n}_EXACT_V1\n'.encode())
            for n in ('gradient_dx', 'gradient_dy')}
        self._parent_angle = hashlib.sha256(
            b'CIR02_REAL_SLOPE_STAGE_instantaneous_slope_EXACT_V1\n')

    def record(self, chunk_index: int, total_chunks: int, source_sha256: str,
               ids: list[str], rows: np.ndarray, cols: np.ndarray,
               dx: np.ndarray, dy: np.ndarray, expected_angle: np.ndarray) -> None:
        if total_chunks != 177 or len(self._seen) >= 3 or chunk_index != CHUNKS[len(self._seen)]:
            raise ValueError('original selected chunk count/order changed or duplicated')
        if (not isinstance(source_sha256, str) or len(source_sha256) != 64
                or any(c not in '0123456789abcdef' for c in source_sha256)):
            raise ValueError('original selected DEM content SHA missing')
        if (len(ids) != 24 or any(not isinstance(s, str) or not s or '\n' in s or '\t' in s for s in ids)
                or len(set(ids)) != 24 or sorted(ids) != ids or set(ids) & self._ids):
            raise ValueError('exactly 24 distinct, sorted original IDs required per chunk')
        rows, cols = np.asarray(rows), np.asarray(cols)
        if rows.shape != (24,) or cols.shape != (24,) or rows.dtype.kind not in 'iu' or cols.dtype.kind not in 'iu':
            raise ValueError('24 original integer raster indices required')
        arrays = angle_arrays(dx, dy, expected_angle)
        if not np.all((rows >= 0) & (cols >= 0) & (rows < dx.shape[0]) & (cols < dx.shape[1])):
            raise ValueError('selected cells outside original raster')
        selected = {n: a[rows, cols].astype(np.float64) for n, a in arrays.items()}
        if any(not np.isfinite(a).all() for a in selected.values()):
            raise ValueError('selected originally complete values are nonfinite')
        # Validate everything before committing any state/digest.
        self._source.update(f'chunk={chunk_index}\t{source_sha256}\n'.encode('ascii'))
        for i, ident in enumerate(ids):
            prefix = ident.encode('utf-8') + b'\t'
            self._identities.update(f'{chunk_index}\t{ident}\n'.encode())
            for n, a in selected.items():
                value = float(a[i])
                self._exact[n].update(prefix + struct.pack('<d', value) + b'\n')
                for p in DECIMALS:
                    self._rounded[n][p].update(prefix + format(value, f'.{p}f').encode('ascii') + b'\n')
            for n, a in (('gradient_dx', dx), ('gradient_dy', dy)):
                self._parent_grad[n].update(prefix + struct.pack('<d', float(a[rows[i], cols[i]])) + b'\n')
            self._parent_angle.update(prefix + struct.pack('<d', float(expected_angle[rows[i], cols[i]])) + b'\n')
        self._seen.append(chunk_index)
        self._ids.update(ids)
        self._count += 24

    def summary(self) -> dict[str, Any]:
        complete = tuple(self._seen) == CHUNKS and self._count == 72
        return {
            'schema_version': 'cir02-angle-operator-diagnostic-v1',
            'status': 'CIR02_ANGLE_SUBSTAGES_COMPLETE' if complete else 'CIR02_ANGLE_SUBSTAGES_INCOMPLETE',
            'cohort_unit_id': 'CIR02', 'source_chunk_count': 177,
            'probed_chunk_count': len(self._seen), 'source_complete_cells_probed': self._count,
            'sampling_policy': 'UNCHANGED_PARENT_0_88_176_BY24_SOURCE_COMPLETE_IDS',
            'sampling_after_full_array_arithmetic': True,
            'sampled_mosaics_content_order_sha256': self._source.hexdigest() if complete else None,
            'sampled_candidate_identity_sha256': self._identities.hexdigest() if complete else None,
            'parent_gradient_exact_float64_sha256': {n: h.hexdigest() for n,h in self._parent_grad.items()} if complete else {},
            'parent_angle_exact_float64_sha256': self._parent_angle.hexdigest() if complete else None,
            'operators_exact_float64_sha256': {n:h.hexdigest() for n,h in self._exact.items()} if complete else {},
            'operators_decimal_sha256': {n:{str(p):h.hexdigest() for p,h in pp.items()} for n,pp in self._rounded.items()} if complete else {},
            'runtime': runtime_metadata(),
            'original_nine_stage_protocol_modified': False,
            'diagnostic_designed_after_angle_discrepancy_observed': True,
            'actual_CIR02_operator_cause_identified': False,
            'full_177_chunk_intermediate_replay': False,
            'field_selector_validated': False,
            'private_values_or_ids_exported': False,
            'field_outcomes_opened': False,
        }


def bind_parent(parent: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    """Prove the added recorder used the original source/gradient/angle sample."""
    if (parent.get('status') != 'ORIGINAL_REAL_DEM_CIR02_THREE_CHUNK_STAGE_AUDIT_COMPLETE'
            or parent.get('cohort_unit_id') != 'CIR02'
            or parent.get('source_chunk_count') != 177
            or parent.get('probed_chunk_count') != 3
            or parent.get('source_complete_cells_probed') != 72
            or parent.get('all_predeclared_chunks_eligible') is not True
            or child.get('status') != 'CIR02_ANGLE_SUBSTAGES_COMPLETE'):
        raise ValueError('parent or supplementary diagnostic incomplete')
    for k in ('field_outcomes_opened', 'stage_sampled_individual_coordinates_or_ids_public',
              'individual_slope_values_public'):
        if parent.get(k) is not False:
            raise ValueError('parent privacy boundary not intact')
    if parent.get('sampled_mosaics_content_order_sha256') != child.get('sampled_mosaics_content_order_sha256'):
        raise ValueError('parent and supplementary source commitments differ')
    gradients = child['parent_gradient_exact_float64_sha256']
    old = parent.get('stages_exact_float64_sha256', {})
    if any(old.get(n) != gradients.get(n) for n in ('gradient_dx', 'gradient_dy')):
        raise ValueError('parent and supplementary gradients/sampled identities differ')
    if old.get('instantaneous_slope') != child.get('parent_angle_exact_float64_sha256'):
        raise ValueError('parent and supplementary sampled angles differ')
    return dict(child, parent_original_diagnostic_bound=True)


def compare_bound_operators(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Compare bound hashes; caller separately verifies full-grid/workflow origin.

    These arguments are the supplementary records, not full workflow receipts.
    No claim of independent runner provenance or real-world causality is made.
    """
    def sha(s: Any) -> bool:
        return isinstance(s, str) and len(s) == 64 and all(c in '0123456789abcdef' for c in s)
    for r in (a,b):
        if (r.get('status') != 'CIR02_ANGLE_SUBSTAGES_COMPLETE'
                or r.get('parent_original_diagnostic_bound') is not True
                or r.get('actual_CIR02_operator_cause_identified') is not False
                or r.get('private_values_or_ids_exported') is not False
                or r.get('field_outcomes_opened') is not False
                or r.get('source_chunk_count') != 177
                or r.get('source_complete_cells_probed') != 72
                or r.get('probed_chunk_count') != 3):
            raise ValueError('unbound, incomplete or overclaimed operator record')
        exact, rounded = r.get('operators_exact_float64_sha256'), r.get('operators_decimal_sha256')
        if not isinstance(exact,dict) or not isinstance(rounded,dict) or set(exact)!=set(OPERATORS) or set(rounded)!=set(OPERATORS):
            raise ValueError('required operator hashes missing')
        for n in OPERATORS:
            if not sha(exact[n]) or set(rounded[n])!={'2','8'} or not all(sha(x) for x in rounded[n].values()):
                raise ValueError('malformed operator fingerprint')
        if (not sha(r.get('sampled_mosaics_content_order_sha256')) or
                not sha(r.get('sampled_candidate_identity_sha256')) or
                not all(sha(r.get('parent_gradient_exact_float64_sha256',{}).get(n)) for n in ('gradient_dx','gradient_dy'))):
            raise ValueError('input fingerprints missing')
    gates = {k:a[k]==b[k] for k in ('sampled_mosaics_content_order_sha256',
             'sampled_candidate_identity_sha256','parent_gradient_exact_float64_sha256')}
    same = all(gates.values())
    per = {n:{'exact':a['operators_exact_float64_sha256'][n]==b['operators_exact_float64_sha256'][n],
              'decimal2':a['operators_decimal_sha256'][n]['2']==b['operators_decimal_sha256'][n]['2'],
              'decimal8':a['operators_decimal_sha256'][n]['8']==b['operators_decimal_sha256'][n]['8']}
           for n in OPERATORS} if same else {}
    result = {
        'status':'BOUNDED_OPERATOR_HASHES_COMPARED' if same else 'INPUTS_DIFFER_NO_OPERATOR_VERDICT',
        'input_sample_gates':gates,'per_operator':per,
        'operator_dependency_order':list(OPERATORS),
        'dx_and_dy_squares_are_parallel_inputs':True,
        'actual_CIR02_operator_cause_identified':False,
        'independent_runner_provenance_verified':False,
        'full_177_chunk_intermediate_replay':False,
        'numerical_error_magnitude_estimated':False,
    }
    for label in ('exact','decimal2','decimal8'):
        result[f'first_differing_{label}_operator'] = next((n for n in OPERATORS if not per[n][label]),None) if same else None
    return result
