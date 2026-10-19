"""Supplementary observer integration: no change to original selected sample or source."""
import sys
import types
import numpy as np
import pandas as pd

from research.cir02_angle_operators import AngleProbe
from research.run_cir02_angle_operators import SupplementaryCallback


def test_callback_opt_in_preserves_original_3_chunks_24_ids_and_full_native_magnitudes(monkeypatch,tmp_path):
    x = np.linspace(.05,5.2, 80*50, dtype=np.float32).reshape(80,50)
    y = np.zeros_like(x)
    full_magnitude = np.sqrt(x*x + y*y)
    degrees = np.degrees(np.arctan(full_magnitude))
    ids=['CIR02_test_%03d'%i for i in range(24)]
    rr = np.array([i*2 for i in range(24)],dtype=np.int64)
    cc = np.array([i for i in range(24)],dtype=np.int64)
    component=pd.DataFrame({'candidate_cell_id':ids,'longitude':[140.0]*24,'latitude':[37.0]*24})
    sampled=pd.DataFrame({'candidate_cell_id':ids,'slope100':degrees[rr,cc]})
    stage={'gradient_dx':x,'gradient_dy':y,'instantaneous_slope':degrees,'slope100':degrees}

    def fake_generate(_): return stage, 'frozen-synthetic-fingerprint'
    def fake_coords(_locations, _path, shape):
        assert shape == degrees.shape
        return rr,cc
    def fake_complete(_sampled): return list(ids)
    names={
        'research.audit_cirsium_slope_kernel_synthetic_two_run': {'generate_stage_arrays':fake_generate},
        'research.audit_cirsium_fresh_sentinel_v2_real_dem_slope_stages': {'_surface_coordinates':fake_coords},
        'research.audit_cirsium_fresh_sentinel_v2_same_mosaic_numerical_replay': {'_source_complete_candidates':fake_complete},
    }
    for name, attrs in names.items():
        monkeypatch.setitem(sys.modules,name,types.SimpleNamespace(**attrs))

    source=tmp_path/'opaque.tif'
    source.write_bytes(b'public synthetic source with no sites')
    for capture in [False,True]:
        probe=SupplementaryCallback.__new__(SupplementaryCallback)
        probe.parent=lambda *a,**k:None  # checks unchanged event payload, no upstream sample needed
        probe.operators=AngleProbe()
        probe.capture_same_worker_magnitude=capture
        probe._private_magnitudes=[]
        for chunk in (0,88,176):
            ids=[f'CIR02_test_{chunk:03d}_{i:03d}' for i in range(24)]
            component=pd.DataFrame({'candidate_cell_id':ids,'longitude':[140.0]*24,'latitude':[37.0]*24})
            sampled=pd.DataFrame({'candidate_cell_id':ids,'slope100':degrees[rr,cc]})
            before=sampled.copy(deep=True)
            probe(chunk,177,component,sampled,source)
            assert sampled.equals(before)
        assert probe.operators.summary()['status']=='CIR02_ANGLE_SUBSTAGES_COMPLETE'
        assert len(probe._private_magnitudes)==(3 if capture else 0)
        for chunk,xp in zip((0,88,176), probe._private_magnitudes):
            assert xp['chunk_index']==chunk
            assert xp['ids']==[f'CIR02_test_{chunk:03d}_{i:03d}' for i in range(24)]
            assert np.array_equal(xp['rows'],rr)
            assert np.array_equal(xp['cols'],cc)
            assert xp['magnitude'].dtype==np.dtype('float32')
            assert xp['magnitude'].shape==degrees.shape
            assert np.array_equal(xp['magnitude'],full_magnitude,equal_nan=True)
