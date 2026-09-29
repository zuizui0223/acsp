#!/usr/bin/env python3
"""Run frozen ACSP robust-patch recovery on an activated E8 fold set."""
from __future__ import annotations

import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd

from evaluate_robust_patches_on_dense_surface import _evaluate_fold, _zero_rows

SUPPORT=0.025
RADII=(1.0,2.0,5.0,10.0)
PRIMARY=10.0
SURFACE_POINTS=800
SURFACE_SEED_BASE=20260823
RANDOM_DRAWS=200
RANDOM_SEED_BASE=20260823

def provenance(path):
    p=json.loads((path/"fold_manifest.json").read_text())
    q=p["provenance"]
    return {
      "taxon_id":int(p["taxon_id"]),"repeat":int(p["repeat"]),
      "scientific_name":str(q["scientific_name"]),"taxon_group":str(q["taxon_group"]),
      "region_name":str(q["region_name"]),"geographic_stratum":str(q["geographic_stratum"]),
      "match_pair_within_region":int(q["match_pair_within_region"]),
      "fold_status":str(p["status"]),"fold_failure_reason":str(p.get("failure_reason","")),
    }

def run(export_root,output):
    dirs=sorted(p.parent for p in Path(export_root).glob("taxon_*/fold_*/fold_manifest.json"))
    if len(dirs)!=240:raise RuntimeError(f"expected 240 folds, found {len(dirs)}")
    rows=[]
    for d in dirs:
        meta=provenance(d);tid=meta["taxon_id"];rep=meta["repeat"]
        try:
            effective=RANDOM_SEED_BASE+tid*10000+rep*1009
            result=_evaluate_fold(
              d,tiers=(SUPPORT,),radii_km=RADII,surface_points=SURFACE_POINTS,
              random_draws=RANDOM_DRAWS,surface_seed_base=SURFACE_SEED_BASE,
              random_seed=effective-991,
            )
            if not result:
                result=_zero_rows(d,tiers=(SUPPORT,),radii_km=RADII,heldout_count=0,failure_reason=meta["fold_failure_reason"] or "no_evaluable_rows")
        except Exception as exc:
            result=_zero_rows(d,tiers=(SUPPORT,),radii_km=RADII,heldout_count=0,failure_reason=f"{type(exc).__name__}: {exc}")
        for rec in result:rows.append({**meta,**rec})
    folds=pd.DataFrame(rows)
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    folds.to_csv(output/"fold_results.csv",index=False)
    primary=folds[
      np.isclose(pd.to_numeric(folds.support_fraction,errors="coerce"),SUPPORT)
      & np.isclose(pd.to_numeric(folds.radius_km,errors="coerce"),PRIMARY)
    ].copy()
    if len(primary)!=240:raise RuntimeError("primary fold denominator changed")
    pair=(primary.groupby(["taxon_id","scientific_name","taxon_group","region_name","match_pair_within_region"],as_index=False)
      .agg(fold_count=("repeat","count"),mean_recall=("recall","mean"),
           mean_random_recall=("random_mean_recall","mean"),mean_lift=("lift_over_random","mean"),
           failed_folds=("failure_reason",lambda s:int(pd.Series(s).astype(str).str.len().gt(0).sum()))))
    if len(pair)!=48 or not pair.fold_count.eq(5).all():raise RuntimeError("taxon denominator changed")
    pair.to_csv(output/"taxon_pair_results.csv",index=False)
    result={"status":"e8_acsp_recovery_complete","taxa":48,"declared_folds":240,
            "support_fraction":SUPPORT,"primary_radius_km":PRIMARY,"retuned_after_outcome_opening":False}
    (output/"recovery_result.json").write_text(json.dumps(result,indent=2)+"\n")
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument("--export-root",required=True);p.add_argument("--output",required=True)
    a=p.parse_args();print(json.dumps(run(a.export_root,a.output),indent=2))
if __name__=="__main__":main()
