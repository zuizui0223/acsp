#!/usr/bin/env python3
"""Supplementary real-CIR02 recorder, using the unmodified original GSI pipeline.

Requires a checkout of the pinned original modules and original private fine grid.
This launcher has NOT been run on actual GSI inputs in the local fixture package.
It adds no candidate ranking, patch retuning, CPU override or private-data export.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import platform
from pathlib import Path
from typing import Any

from research.cir02_angle_operators import AngleProbe, CHUNKS, bind_parent, _sha256_file

ROOT = Path(__file__).resolve().parents[1]
PINNED_BLOBS = {
    'research/audit_cirsium_fresh_sentinel_v2_same_mosaic_numerical_replay.py': '0d99ad3735b784e7f4e2c79a087e823e1ba7ff1c',
    'research/campanula_microterrain_discovery.py': '63704d78c7ca52d809ddd9d3b2e94e78f31d0436',
    'research/attach_cirsium_fresh_sentinel_v2_fixed_gsi_terrain.py': 'a23609dc7c8ea190ed9b02fbccda7be8d9f36244',
    'research/audit_cirsium_fresh_sentinel_v2_real_dem_slope_stages.py': '359560b90c51addf92d1fa45848d56ca5047713b',
    'research/audit_cirsium_slope_kernel_synthetic_two_run.py': '2b825036a8e7bca8f3524cbb6298667094762353',
    'research/build_cirsium_private_alpine_local_grid_v1.py': '6c6ac37f5c1c9857ef8a54992e0d23717dda29f1',
    'research/audit_cirsium_fresh_sentinel_v2_selected_mosaic_sequence.py': '7a238002c2cd6b652dcae141729d92c7d2d1c05b',
}
FROZEN_GRID_SHA = 'c87fe4b3158a5c63253a5bb73039e18e72c288cecb7d071989cff448dbac14a5'
FROZEN_SELECTED_SHA = '7ef762da0577e94d4f94bf1f171cfe1aa6f8fc9046cd6c03ee364cd334a43ddf'


def verify_original_modules(root: Path = ROOT) -> None:
    for name, expected in PINNED_BLOBS.items():
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('required original upstream source is missing')
        raw = path.read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if actual != expected:
            raise ValueError('original upstream source changed; review and refreeze separately: ' + name)


def require_original_runtime() -> None:
    import numpy, scipy, rasterio, pandas, pyproj
    actual = (platform.python_version(), numpy.__version__, scipy.__version__,
              rasterio.__version__, pandas.__version__, pyproj.__version__, rasterio.__gdal_version__)
    expected = ('3.11.17', '2.4.6', '1.17.1', '1.4.4', '3.0.6', '3.7.2', '3.10.3')
    if actual != expected:
        raise ValueError('real diagnostic requires the declared original runtime versions')


def require_original_source_world(gsi: dict[str, Any], selected: dict[str, Any]) -> dict[str, bool]:
    """Expose only the names of failed original-input gates, never private values.

    The frozen denominator and source byte commitments remain unchanged.
    An incomplete or altered original DEM source still aborts without
    exporting a supplementary angle-stage result.
    """
    gates = {
        'candidate_rows_match_original': (
            type(gsi.get('candidate_rows')) is int
            and gsi['candidate_rows'] == 464633
        ),
        'source_complete_rows_match_original': (
            type(gsi.get('source_complete_rows')) is int
            and gsi['source_complete_rows'] == 383460
        ),
        'selected_dem_content_sequence_matches_original': (
            selected.get('selected_mosaic_content_sequence_sha256') == FROZEN_SELECTED_SHA
        ),
        'selected_dem_chunk_count_matches_original': (
            type(selected.get('selected_dem_chunks')) is int
            and selected['selected_dem_chunks'] == 177
        ),
    }
    failed = [name for name, ok in gates.items() if not ok]
    if failed:
        raise ValueError('real source world differs from frozen historical CIR02; '
                         'no operator verdict; failed public gates: ' + ', '.join(failed))
    return gates


class SupplementaryCallback:
    def __init__(self) -> None:
        from research.audit_cirsium_fresh_sentinel_v2_real_dem_slope_stages import CIR02RealDEMSlopeStageCollector
        self.parent = CIR02RealDEMSlopeStageCollector()
        self.operators = AngleProbe()

    def __call__(self, chunk_index, total_chunks, component, sampled, mosaic_path) -> None:
        from research.audit_cirsium_slope_kernel_synthetic_two_run import generate_stage_arrays
        from research.audit_cirsium_fresh_sentinel_v2_real_dem_slope_stages import _surface_coordinates
        from research.audit_cirsium_fresh_sentinel_v2_same_mosaic_numerical_replay import _source_complete_candidates
        import numpy as np
        # Parent always runs first and retains its identical original record format.
        self.parent(chunk_index, total_chunks, component, sampled, mosaic_path)
        if chunk_index not in CHUNKS:
            return
        path = Path(mosaic_path)
        before = _sha256_file(path)
        stages, _ = generate_stage_arrays(path)
        ids = _source_complete_candidates(sampled)  # the ORIGINAL selection rule
        cells = component.set_index(component['candidate_cell_id'].astype(str))
        locations = cells.loc[ids].reset_index(drop=True)
        rows, cols = _surface_coordinates(locations, path, stages['gradient_dx'].shape)
        original = sampled.set_index(sampled['candidate_cell_id'].astype(str))
        if not np.array_equal(original.loc[ids, 'slope100'].to_numpy(np.float64),
                              stages['slope100'][rows, cols].astype(np.float64), equal_nan=True):
            raise ValueError('supplementary reread disagrees with original sampled slope')
        self.operators.record(chunk_index,total_chunks,before,ids,rows,cols,
                              stages['gradient_dx'],stages['gradient_dy'],stages['instantaneous_slope'])
        if _sha256_file(path) != before:
            raise ValueError('selected original raster bytes changed during supplementary read')

    def summary(self) -> dict[str, Any]:
        parent = self.parent.summary(unit_id='CIR02', source_chunk_count=177)
        child = bind_parent(parent, self.operators.summary())
        return {'original_nine_stage_record': parent, 'supplementary_six_operator_record': child}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fine-grid-csv-gz', required=True, type=Path)
    p.add_argument('--cache-dir', required=True, type=Path)
    p.add_argument('--public-json', required=True, type=Path)
    args = p.parse_args()
    verify_original_modules()
    require_original_runtime()
    if args.public_json.exists() or args.public_json.is_symlink():
        raise ValueError('refusing to overwrite an existing diagnostic')
    if args.cache_dir.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError('private GSI cache must stay outside the repository')
    if args.fine_grid_csv_gz.is_symlink() or _sha256_file(args.fine_grid_csv_gz) != FROZEN_GRID_SHA:
        raise ValueError('original PR241 fine-grid archive identity changed')
    import pandas as pd
    from research.attach_cirsium_fresh_sentinel_v2_fixed_gsi_terrain import attach_fixed_gsi_terrain
    from research.audit_cirsium_fresh_sentinel_v2_selected_mosaic_sequence import SelectedMosaicSequence
    frame = pd.read_csv(args.fine_grid_csv_gz, low_memory=False)
    if len(frame) != 464633:
        raise ValueError('original fine-grid denominator changed')
    sequence = SelectedMosaicSequence(unit_id='CIR02', cache_dir=args.cache_dir)
    callback = SupplementaryCallback()
    # No change to sampler, builder, source priority, chunk phase or CPU settings.
    audited, gsi = attach_fixed_gsi_terrain(frame, unit_id='CIR02', cache_dir=args.cache_dir,
        selected_mosaic_observer=sequence, real_slope_stage_probe=callback)
    selected = sequence.summary(chunk_count=int(gsi['chunk_count']))
    require_original_source_world(gsi, selected)
    if _sha256_file(args.fine_grid_csv_gz) != FROZEN_GRID_SHA:
        raise ValueError('original grid archive changed during diagnostic')
    states = hashlib.sha256(b'CIR02_ANGLE_GSI_SOURCE_STATES_V1\n')
    for ident, state in zip(audited['candidate_cell_id'], audited['gsi_source_state']):
        states.update(f'{ident}\t{state}\n'.encode())
    result = callback.summary()
    result['original_source_bindings'] = {
        'private_grid_sha256': FROZEN_GRID_SHA, 'candidate_rows': 464633,
        'gsi_source_complete_rows':383460,
        'selected_mosaic_content_sequence_sha256':FROZEN_SELECTED_SHA,
        'gsi_source_state_sha256':states.hexdigest(),
    }
    result['status'] = 'SUPPLEMENTARY_REAL_CIR02_ANGLE_CAPTURE_COMPLETE_NOT_CAUSAL'
    result['actual_CIR02_operator_cause_identified'] = False
    result['field_outcomes_opened'] = False
    result['private_values_or_ids_exported'] = False
    args.public_json.parent.mkdir(parents=True,exist_ok=True)
    with args.public_json.open('x',encoding='utf-8') as f:
        json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({'status':result['status'],'recorded_cells':72,'operator_count':6}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
