#!/usr/bin/env python3
"""Open the frozen pair-level ACSP outcome only after the E8 balance gate passes."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd

def wmean(v,w): return float(np.sum(v*w)/np.sum(w))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--gate",type=Path,required=True)
    ap.add_argument("--weights",type=Path,required=True)
    ap.add_argument("--pair-results",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    gate=json.loads(args.gate.read_text())
    if gate.get("status")!="observation_architecture_balance_gate_passed":
        raise RuntimeError("outcome opening not authorized by observation-architecture gate")
    weights=pd.read_csv(args.weights)
    outcomes=pd.read_csv(args.pair_results)[["pair_id","mean_lift"]]
    x=weights.merge(outcomes,on="pair_id",how="inner",validate="one_to_one")
    if len(x)!=len(weights):
        raise RuntimeError("authorized metadata rows do not all map to pair outcomes")
    animal=x.taxon_group.eq("animal").to_numpy()
    raw=float(x.loc[animal,"mean_lift"].mean()-x.loc[~animal,"mean_lift"].mean())
    weighted=wmean(x.loc[animal,"mean_lift"].to_numpy(float),x.loc[animal,"stabilized_ipw"].to_numpy(float))-wmean(x.loc[~animal,"mean_lift"].to_numpy(float),x.loc[~animal,"stabilized_ipw"].to_numpy(float))
    out={
      "schema":"acsp.e8_observation_architecture_adjusted.result.v1",
      "authorized_by_gate":True,
      "taxa":int(len(x)),
      "raw_animal_minus_plant_mean_lift":raw,
      "ipw_animal_minus_plant_mean_lift":weighted,
      "interpretation":"retrospective observation-architecture-adjusted diagnostic; not a preregistered taxonomic effect"
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps(out,indent=2))

if __name__=="__main__":
    main()
