#!/usr/bin/env python3
"""Export five frozen spatial folds for an activated E8 48-taxon matched cohort."""
from __future__ import annotations

import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd

from benchmark_general_random_taxa_regions import fetch_occurrences

def coord_cols(frame):
    for lat,lon in (("latitude","longitude"),("_latitude","_longitude"),("decimalLatitude","decimalLongitude"),("lat","lon")):
        if lat in frame.columns and lon in frame.columns:return lat,lon
    raise ValueError("no coordinate columns")

def write_fold(path,training,heldout,row,repeat,status,reason=""):
    path.mkdir(parents=True,exist_ok=True)
    training.to_csv(path/"training_occurrences.csv",index=False)
    heldout.to_csv(path/"held_out_occurrences.csv",index=False)
    meta={
      "taxon_id":int(row.taxon_id),
      "repeat":int(repeat),
      "status":status,
      "failure_reason":reason,
      "training_records":len(training),
      "heldout_records":len(heldout),
      "provenance":{
        "scientific_name":str(row.scientific_name),
        "taxon_group":str(row.taxon_group),
        "region_name":str(row.region_name),
        "geographic_stratum":str(row.geographic_stratum),
        "speciesKey":int(row.speciesKey),
        "west":float(row.west),"south":float(row.south),"east":float(row.east),"north":float(row.north),
        "match_pair_within_region":int(row.match_pair_within_region),
      }
    }
    (path/"fold_manifest.json").write_text(json.dumps(meta,indent=2)+"\n")

def run(cohort_path,output,seed_base=20260823,repeats=5,cap=150):
    cohort=pd.read_csv(cohort_path).copy()
    if len(cohort)!=48 or cohort.scientific_name.astype(str).nunique()!=48:
        raise ValueError("E8 confirmation requires 48 unique taxa")
    if cohort.groupby(["region_name","match_pair_within_region"]).ngroups!=24:
        raise ValueError("E8 matched-pair denominator changed")
    if cohort.taxon_group.value_counts().to_dict()!={"animal":24,"plant":24}:
        raise ValueError("E8 taxon-group balance changed")
    cohort=cohort.sort_values(["region_name","match_pair_within_region","taxon_group","scientific_name"],kind="mergesort").reset_index(drop=True)
    cohort.insert(0,"taxon_id",range(1,49))
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    cohort.to_csv(output/"activated_cohort.csv",index=False)
    status=[]
    empty=pd.DataFrame(columns=["latitude","longitude"])
    for row in cohort.itertuples(index=False):
        try:
            occ=fetch_occurrences(pd.Series(row._asdict()),cap).copy().reset_index(drop=True)
            lat,lon=coord_cols(occ)
            occ["latitude"]=pd.to_numeric(occ[lat],errors="coerce")
            occ["longitude"]=pd.to_numeric(occ[lon],errors="coerce")
            occ=occ.dropna(subset=["latitude","longitude"]).reset_index(drop=True)
            if len(occ)<4:raise ValueError(f"fewer than four usable occurrence rows: {len(occ)}")
            occ["spatial_block"]=(np.floor(occ.latitude/.1).astype(int).astype(str)+":"+np.floor(occ.longitude/.1).astype(int).astype(str))
            blocks=occ.spatial_block.drop_duplicates().to_numpy()
            if len(blocks)<2:raise ValueError("fewer than two spatial blocks")
            hold=min(len(blocks)-1,max(1,int(round(len(blocks)*.2))))
            rng=np.random.default_rng(int(seed_base)+int(row.taxon_id))
            for rep in range(1,repeats+1):
                held=set(rng.choice(blocks,size=hold,replace=False).tolist())
                test=occ[occ.spatial_block.isin(held)].drop(columns=["spatial_block"]).reset_index(drop=True)
                train=occ[~occ.spatial_block.isin(held)].drop(columns=["spatial_block"]).reset_index(drop=True)
                if train.empty or test.empty:raise ValueError(f"repeat {rep} empty partition")
                write_fold(output/f"taxon_{row.taxon_id:03d}"/f"fold_{rep:03d}",train,test,row,rep,"ready")
            status.append({"taxon_id":row.taxon_id,"scientific_name":row.scientific_name,"status":"complete","occurrence_rows":len(occ),"blocks":len(blocks)})
        except Exception as exc:
            for rep in range(1,repeats+1):
                write_fold(output/f"taxon_{row.taxon_id:03d}"/f"fold_{rep:03d}",empty,empty,row,rep,"failed_placeholder",f"{type(exc).__name__}: {exc}")
            status.append({"taxon_id":row.taxon_id,"scientific_name":row.scientific_name,"status":"failed_retained_as_zero","occurrence_rows":0,"blocks":0,"reason":str(exc)})
    pd.DataFrame(status).to_csv(output/"taxon_export_status.csv",index=False)
    manifests=list(output.glob("taxon_*/fold_*/fold_manifest.json"))
    if len(manifests)!=240:raise RuntimeError(f"expected 240 folds, found {len(manifests)}")
    result={"status":"e8_folds_exported","taxa":48,"declared_folds":240,"outcome_scoring_run":False}
    (output/"export_result.json").write_text(json.dumps(result,indent=2)+"\n")
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument("--cohort",required=True);p.add_argument("--output",required=True)
    a=p.parse_args();print(json.dumps(run(a.cohort,a.output),indent=2))
if __name__=="__main__":main()
