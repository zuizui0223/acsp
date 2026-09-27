#!/usr/bin/env python3
"""Apply the frozen E8 observation-architecture overlap gate without reading recovery outcomes."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

FEATURES=[
"log1p_current_coordinate_record_count",
"human_observation_fraction",
"machine_observation_fraction",
"preserved_specimen_fraction",
"recent_2021_2025_fraction",
"top_dataset_share",
]

def weighted_mean(x,w):
    return float(np.sum(x*w)/np.sum(w))

def weighted_var(x,w,mu):
    return float(np.sum(w*(x-mu)**2)/np.sum(w))

def smd(x,g,w):
    xa=x[g==1]; wa=w[g==1]; xp=x[g==0]; wp=w[g==0]
    ma=weighted_mean(xa,wa); mp=weighted_mean(xp,wp)
    va=weighted_var(xa,wa,ma); vp=weighted_var(xp,wp,mp)
    den=((va+vp)/2)**0.5
    return 0.0 if den==0 else float((ma-mp)/den)

def ess(w):
    return float((w.sum()**2)/(np.square(w).sum())) if np.square(w).sum()>0 else 0.0

def compute_weights(work):
    X=work[FEATURES].to_numpy(float)
    g=work["taxon_group"].eq("animal").astype(int).to_numpy()
    z=StandardScaler().fit_transform(X)
    model=LogisticRegression(C=1.0,penalty="l2",solver="lbfgs",max_iter=2000)
    model.fit(z,g)
    e=model.predict_proba(z)[:,1]
    clipped=np.clip(e,0.05,0.95)
    pa=float(g.mean())
    w=np.where(g==1,pa/clipped,(1-pa)/(1-clipped))
    cap=float(np.quantile(w,0.99))
    w=np.minimum(w,cap)
    for val in (0,1):
        idx=g==val
        w[idx]=w[idx]/w[idx].mean()
    return g,e,w

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--metadata",type=Path,required=True)
    ap.add_argument("--contract",type=Path,required=True)
    ap.add_argument("--gate-output",type=Path,required=True)
    ap.add_argument("--weights-output",type=Path,required=True)
    args=ap.parse_args()
    c=json.loads(args.contract.read_text())
    md=pd.read_csv(args.metadata)
    work=md[md.status.eq("complete")].copy()
    work=work.dropna(subset=FEATURES).reset_index(drop=True)
    minimum=int(c["pre_outcome_overlap_gate"]["minimum_complete_metadata_taxa"])
    complete_ok=len(work)>=minimum
    result={"schema":"acsp.e8_observation_architecture_gate.result.v1",
            "metadata_complete_taxa":int(len(work)),"minimum_complete_metadata_taxa":minimum,
            "outcome_opened":False}
    if len(work)<4 or work.taxon_group.nunique()!=2:
        result.update({"status":"observation_architecture_not_balanceable_in_current_cohort",
                       "reason":"insufficient complete two-group metadata"})
    else:
        g,e,w=compute_weights(work)
        lo,hi=c["pre_outcome_overlap_gate"]["propensity_overlap_interval"]
        overlap=float(np.mean((e>=float(lo))&(e<=float(hi))))
        ess_a=ess(w[g==1]); ess_p=ess(w[g==0])
        smds={f:abs(smd(work[f].to_numpy(float),g,w)) for f in FEATURES}
        result.update({
            "propensity_min":float(e.min()),"propensity_max":float(e.max()),
            "fraction_inside_overlap":overlap,
            "effective_sample_size":{"animal":ess_a,"plant":ess_p},
            "postweight_absolute_smd":smds,
            "max_postweight_absolute_smd":float(max(smds.values())),
        })
        gate_cfg=c["pre_outcome_overlap_gate"]
        checks={
            "metadata_complete":complete_ok,
            "overlap_fraction":overlap>=float(gate_cfg["minimum_fraction_inside_overlap"]),
            "animal_ess":ess_a>=float(gate_cfg["minimum_effective_sample_size_each_group"]),
            "plant_ess":ess_p>=float(gate_cfg["minimum_effective_sample_size_each_group"]),
            "all_smd":max(smds.values())<=float(gate_cfg["maximum_absolute_postweight_smd_each_nuisance_metric"]),
        }
        result["checks"]=checks
        passed=all(checks.values())
        result["status"]="observation_architecture_balance_gate_passed" if passed else "observation_architecture_not_balanceable_in_current_cohort"
        work["observation_propensity_animal"]=e
        work["stabilized_ipw"]=w
        args.weights_output.parent.mkdir(parents=True,exist_ok=True)
        work.to_csv(args.weights_output,index=False)
    args.gate_output.parent.mkdir(parents=True,exist_ok=True)
    args.gate_output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))

if __name__=="__main__":
    main()
