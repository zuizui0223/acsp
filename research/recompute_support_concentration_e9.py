#!/usr/bin/env python3
"""Recompute the exploratory E9 support-concentration closeout from frozen ACSP artifacts."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--fold-results",type=Path,required=True)
    ap.add_argument("--cohort",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()

    folds=pd.read_csv(args.fold_results)
    cohort=pd.read_csv(args.cohort)
    primary=folds[
        np.isclose(pd.to_numeric(folds["support_fraction"],errors="coerce"),0.025)
        & np.isclose(pd.to_numeric(folds["radius_km"],errors="coerce"),10.0)
    ].copy()
    primary=primary[
        (pd.to_numeric(primary["selected_cells"],errors="coerce")>=2)
        & (pd.to_numeric(primary["patch_count"],errors="coerce")>=1)
    ].copy()
    primary["concentration"]=(primary["selected_cells"]-primary["patch_count"])/(primary["selected_cells"]-1)

    pair=(primary.groupby(["pair_id","scientific_name","taxon_group","region_name"],as_index=False)
          .agg(evaluable_folds=("repeat","count"),
               concentration=("concentration","mean"),
               mean_lift=("lift_over_random","mean")))
    pair=pair[pair["evaluable_folds"]>=3].merge(
        cohort[["pair_id","record_count_stratum"]],on="pair_id",how="left",validate="one_to_one"
    )
    wide=pair.pivot_table(index=["region_name","record_count_stratum"],
                          columns="taxon_group",values="concentration",aggfunc="first").dropna()
    diff=(wide["animal"]-wide["plant"]).to_numpy(float)

    rng=np.random.default_rng(20260927)
    boot=np.asarray([rng.choice(diff,size=len(diff),replace=True).mean() for _ in range(30000)])
    rng=np.random.default_rng(20260928)
    draws=300000
    extreme=0
    for _ in range(draws//10000):
        signs=rng.choice((-1.0,1.0),size=(10000,len(diff)))
        extreme += int(np.sum((signs*diff).mean(axis=1)>=float(diff.mean())))
    p=(1+extreme)/(draws+1)

    result={
        "matched_cells":int(len(diff)),
        "mean_animal_minus_plant":float(diff.mean()),
        "median_animal_minus_plant":float(np.median(diff)),
        "bootstrap_95_ci":[float(np.quantile(boot,0.025)),float(np.quantile(boot,0.975))],
        "one_sided_sign_flip_p":float(p),
        "positive":int(np.sum(diff>0)),
        "negative":int(np.sum(diff<0)),
        "ties":int(np.sum(diff==0)),
        "eligible_pairs":int(len(pair)),
        "spearman_concentration_vs_lift":float(pair[["concentration","mean_lift"]].corr(method="spearman").iloc[0,1]),
        "interpretation":"exploratory animal-greater-than-plant concentration hypothesis not supported"
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))

if __name__=="__main__":
    main()
