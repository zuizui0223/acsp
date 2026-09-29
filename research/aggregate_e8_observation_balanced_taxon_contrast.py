#!/usr/bin/env python3
"""Aggregate the pre-frozen E8 matched animal-plant taxon contrast."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

def bootstrap(values,draws,seed):
    rng=np.random.default_rng(int(seed))
    means=np.empty(int(draws),dtype=float)
    for i in range(int(draws)):
        means[i]=rng.choice(values,size=len(values),replace=True).mean()
    return float(np.quantile(means,.025)),float(np.quantile(means,.975))

def signflip(values,draws,seed):
    observed=float(values.mean())
    rng=np.random.default_rng(int(seed))
    extreme=0
    for _ in range(int(draws)):
        null=float((values*rng.choice((-1.0,1.0),size=len(values))).mean())
        extreme += int(null>=observed)
    return float((1+extreme)/(int(draws)+1))

def run(cohort_path,pair_results_path,contract_path):
    c=json.loads(Path(contract_path).read_text())
    cohort=pd.read_csv(cohort_path)
    results=pd.read_csv(pair_results_path)
    if len(cohort)!=48 or cohort["scientific_name"].astype(str).nunique()!=48:
        raise ValueError("confirmation requires exact frozen 48-taxon cohort")
    key=["region_name","match_pair_within_region"]
    if cohort.groupby(key).ngroups!=24:
        raise ValueError("confirmation requires 24 matched pairs")
    wanted={"scientific_name","mean_lift"}
    if wanted-set(results.columns):
        raise ValueError("pair results missing scientific_name/mean_lift")
    merged=cohort.merge(results[["scientific_name","mean_lift"]],on="scientific_name",how="left",validate="one_to_one")
    if merged["mean_lift"].isna().any():
        raise ValueError("every frozen taxon must retain an intention-to-evaluate lift")
    wide=merged.pivot(index=key,columns="taxon_group",values="mean_lift")
    if set(wide.columns)!={"animal","plant"} or len(wide)!=24:
        raise ValueError("matched animal-plant denominator changed")
    diff=(wide["animal"]-wide["plant"]).to_numpy(float)
    inf=c["primary_inference"]
    lo,hi=bootstrap(diff,inf["paired_bootstrap_replicates"],inf["paired_bootstrap_seed"])
    p=signflip(diff,inf["sign_flip_draws"],inf["sign_flip_seed"])
    mean=float(diff.mean())
    passed=bool(
      mean>=float(inf["minimum_practical_mean_difference"])
      and lo>float(inf["required_bootstrap_95_lower_bound"])
      and p<float(inf["required_one_sided_sign_flip_p_below"])
    )
    return {
      "schema":"acsp.e8_observation_balanced_taxon_contrast.result.v1",
      "matched_pairs":24,
      "animal_mean_lift":float(wide["animal"].mean()),
      "plant_mean_lift":float(wide["plant"].mean()),
      "mean_animal_minus_plant":mean,
      "median_animal_minus_plant":float(np.median(diff)),
      "positive_pairs":int(np.sum(diff>0)),
      "negative_pairs":int(np.sum(diff<0)),
      "ties":int(np.sum(diff==0)),
      "paired_bootstrap_95_ci":[lo,hi],
      "one_sided_sign_flip_p":p,
      "primary_gate_passed":passed,
      "decision":"taxonomic_lift_difference_supported" if passed else "taxonomic_lift_difference_not_supported",
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cohort",required=True)
    p.add_argument("--pair-results",required=True)
    p.add_argument("--contract",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    result=run(a.cohort,a.pair_results,a.contract)
    Path(a.output).parent.mkdir(parents=True,exist_ok=True)
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))

if __name__=="__main__":
    main()
