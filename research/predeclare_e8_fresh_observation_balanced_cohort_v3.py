#!/usr/bin/env python3
from __future__ import annotations

import argparse, itertools, json, math, time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from benchmark_general_random_taxa_regions import REGION_CELLS, TAXON_GROUPS, taxon_frame, rectangle_wkt

FEATURES=[
"log1p_current_coordinate_record_count",
"human_observation_fraction",
"machine_observation_fraction",
"preserved_specimen_fraction",
"recent_2021_2025_fraction",
"top_dataset_share",
]
GBIF="https://api.gbif.org/v1/occurrence/search"

def get_json(params,retries=4):
    last=None
    for k in range(retries):
        try:
            r=requests.get(GBIF,params=params,timeout=45,headers={"User-Agent":"acsp-e8-fresh-v3/1.0"})
            if r.status_code==200:
                return r.json()
            last=RuntimeError(f"HTTP {r.status_code}: {r.text[:160]}")
        except Exception as e:
            last=e
        time.sleep(1.2*(k+1))
    raise RuntimeError(str(last))

def count(base,**extra):
    p=dict(base); p.update(extra); p["limit"]=0
    return int(get_json(p).get("count",0))

def top_dataset_share(base,total):
    p=dict(base); p.update({"limit":0,"facet":"datasetKey","facetLimit":50})
    js=get_json(p); vals=[]
    for f in js.get("facets") or []:
        if not isinstance(f,dict): continue
        for item in f.get("counts") or []:
            try: vals.append(int(item["count"]))
            except Exception: pass
    return float(max(vals)/total) if total>0 and vals else float("nan")

def metadata(rec):
    base={
      "taxonKey":int(rec["speciesKey"]),
      "geometry":rectangle_wkt((float(rec["west"]),float(rec["south"]),float(rec["east"]),float(rec["north"]))),
      "hasCoordinate":"true","hasGeospatialIssue":"false","occurrenceStatus":"PRESENT",
    }
    total=count(base)
    return {
      "current_coordinate_record_count":total,
      "log1p_current_coordinate_record_count":float(math.log1p(total)),
      "human_observation_fraction":count(base,basisOfRecord="HUMAN_OBSERVATION")/total if total else np.nan,
      "machine_observation_fraction":count(base,basisOfRecord="MACHINE_OBSERVATION")/total if total else np.nan,
      "preserved_specimen_fraction":count(base,basisOfRecord="PRESERVED_SPECIMEN")/total if total else np.nan,
      "recent_2021_2025_fraction":count(base,year="2021,2025")/total if total else np.nan,
      "top_dataset_share":top_dataset_share(base,total),
    }

def add_exclusion_frame(frame,names,keys):
    if frame is None or frame.empty: return
    if "scientific_name" in frame:
        names.update(frame["scientific_name"].dropna().astype(str))
    for col in ("speciesKey","species_key","taxonKey"):
        if col in frame:
            keys.update(pd.to_numeric(frame[col],errors="coerce").dropna().astype(int))

def exclusions(contract, prior, v1, v2):
    names=set(); keys=set()
    add_exclusion_frame(prior,names,keys)
    add_exclusion_frame(v1,names,keys)
    add_exclusion_frame(v2,names,keys)
    for p in contract["exclusions"]["repository_exclusion_files"]:
        path=Path(p)
        if not path.exists(): continue
        try: frame=pd.read_csv(path)
        except Exception: continue
        add_exclusion_frame(frame,names,keys)
    return names,keys

def deterministic_candidates(frame,n):
    f=frame.sort_values(["coordinate_records","scientific_name"],kind="mergesort").reset_index(drop=True)
    if len(f)<=n:return f
    idx=np.unique(np.round(np.linspace(0,len(f)-1,n)).astype(int))
    return f.iloc[idx].reset_index(drop=True)

def scale_region(frame,weights):
    z=frame.copy()
    for f in FEATURES:
        x=z[f].to_numpy(float)
        med=float(np.nanmedian(x)); q1,q3=np.nanquantile(x,[.25,.75])
        scale=max(float(q3-q1),0.10)
        z[f+"_z"]=(x-med)/scale*float(weights[f])
    return z

def choose_two(frame,max_dist):
    a=frame[frame.taxon_group.eq("animal")].reset_index(drop=True)
    p=frame[frame.taxon_group.eq("plant")].reset_index(drop=True)
    if len(a)<2 or len(p)<2:return None
    cols=[f+"_z" for f in FEATURES]
    A=a[cols].to_numpy(float); P=p[cols].to_numpy(float)
    D=np.linalg.norm(A[:,None,:]-P[None,:,:],axis=2)
    best=None
    for ai in itertools.combinations(range(len(a)),2):
      for pi in itertools.combinations(range(len(p)),2):
        for order in (pi,pi[::-1]):
          ds=[float(D[ai[k],order[k]]) for k in range(2)]
          if max(ds)>max_dist: continue
          names=tuple((str(a.iloc[ai[k]]["scientific_name"]),str(p.iloc[order[k]]["scientific_name"])) for k in range(2))
          key=(sum(ds),max(ds),names)
          if best is None or key<best[0]:
            best=(key,[(ai[k],order[k],ds[k]) for k in range(2)])
    if best is None:return None
    out=[]
    for rank,(x,y,d) in enumerate(best[1],1):
      for row in (a.iloc[x],p.iloc[y]):
        rec=row.to_dict(); rec["match_pair_within_region"]=rank; rec["match_distance"]=d; out.append(rec)
    return pd.DataFrame(out)

def smd(x,g):
    a=x[g==1]; p=x[g==0]
    den=math.sqrt((np.var(a,ddof=1)+np.var(p,ddof=1))/2)
    return 0.0 if den==0 else float((np.mean(a)-np.mean(p))/den)

def gate(matched,contract):
    cfg=contract["freeze_gate"]
    g=matched.taxon_group.eq("animal").astype(int).to_numpy()
    X=matched[FEATURES].to_numpy(float)
    z=StandardScaler().fit_transform(X)
    model=LogisticRegression(C=1,solver="lbfgs",max_iter=2000).fit(z,g)
    e=model.predict_proba(z)[:,1]
    ess={}
    for v,name in ((1,"animal"),(0,"plant")):
      ev=np.clip(e[g==v],.05,.95); pa=float(g.mean())
      w=(pa/ev) if v==1 else ((1-pa)/(1-ev))
      ess[name]=float((w.sum()**2)/(w@w))
    smds={f:abs(smd(matched[f].to_numpy(float),g)) for f in FEATURES}
    checks={
      "regions":matched.region_name.nunique()==cfg["exact_regions_with_two_pairs"],
      "pairs":matched.groupby(["region_name","match_pair_within_region"]).ngroups==cfg["exact_matched_pairs"],
      "taxa":len(matched)==cfg["exact_taxa"],
      "unique_taxa":matched.scientific_name.astype(str).nunique()==cfg["exact_unique_scientific_names"],
      "max_smd":max(smds.values())<=cfg["maximum_global_absolute_smd"],
      "overlap":float(np.mean((e>=.10)&(e<=.90)))>=cfg["minimum_group_propensity_overlap_fraction_0_10_0_90"],
      "ess_animal":ess["animal"]>=cfg["minimum_propensity_ess_each_group"],
      "ess_plant":ess["plant"]>=cfg["minimum_propensity_ess_each_group"],
      "pair_distance":float(matched.match_distance.max())<=cfg["maximum_pair_distance"],
    }
    return {"checks":checks,"passed":all(checks.values()),"max_absolute_smd":max(smds.values()),
            "absolute_smd":smds,"propensity_min":float(e.min()),"propensity_max":float(e.max()),
            "overlap_fraction":float(np.mean((e>=.10)&(e<=.90))),"ess":ess,
            "maximum_pair_distance_observed":float(matched.match_distance.max())}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--contract",type=Path,required=True)
    ap.add_argument("--prior-cohort",type=Path,required=True)
    ap.add_argument("--v1-candidates",type=Path,required=True)
    ap.add_argument("--v2-candidates",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    c=json.loads(args.contract.read_text())
    prior=pd.read_csv(args.prior_cohort); v1=pd.read_csv(args.v1_candidates); v2=pd.read_csv(args.v2_candidates)
    excluded_names,excluded_keys=exclusions(c,prior,v1,v2)
    prefixes=tuple(c["exclusions"]["excluded_name_prefixes"])
    weights=c["matching_rule_frozen_from_consumed_v1_metadata_only"]["feature_weights"]
    max_dist=float(c["matching_rule_frozen_from_consumed_v1_metadata_only"]["maximum_pair_distance"])
    n=int(c["fresh_design"]["candidate_taxa_per_region_group"])
    rows=[]; matched=[]; used_names=set()

    for geo,region,w,s,e,north in REGION_CELLS:
      region_rows=[]
      for group,kingdom in TAXON_GROUPS.items():
        f=taxon_frame((w,s,e,north),kingdom,int(c["fresh_design"]["facet_limit"]),int(c["fresh_design"]["minimum_coordinate_records"]))
        if f.empty: continue
        f=f[
          ~f.scientific_name.astype(str).isin(excluded_names)
          & ~pd.to_numeric(f.speciesKey,errors="coerce").isin(excluded_keys)
        ].copy()
        f=f[~f.scientific_name.astype(str).str.startswith(prefixes)].copy()
        f=deterministic_candidates(f,n)
        for rr in f.itertuples(index=False):
          rec={"taxon_group":group,"geographic_stratum":geo,"region_name":region,
               "west":w,"south":s,"east":e,"north":north,
               "speciesKey":int(rr.speciesKey),"scientific_name":str(rr.scientific_name),
               "sampling_frame_coordinate_records":int(rr.coordinate_records)}
          try: rec.update(metadata(rec)); rec["metadata_status"]="complete"; rec["error"]=""
          except Exception as ex: rec["metadata_status"]="failed"; rec["error"]=f"{type(ex).__name__}: {ex}"
          rows.append(rec); region_rows.append(rec)
      rf=pd.DataFrame(region_rows)
      if rf.empty: continue
      rf=rf[rf.metadata_status.eq("complete")].dropna(subset=FEATURES).reset_index(drop=True)
      rf=rf[~rf.scientific_name.astype(str).isin(used_names)].reset_index(drop=True)
      if rf.empty: continue
      sel=choose_two(scale_region(rf,weights),max_dist)
      if sel is None: continue
      chosen=set(sel.scientific_name.astype(str))
      if len(chosen)!=4 or chosen & used_names:
        raise RuntimeError("global scientific-name uniqueness violation")
      used_names.update(chosen); matched.append(sel)

    cand=pd.DataFrame(rows)
    m=pd.concat(matched,ignore_index=True) if matched else pd.DataFrame()
    result_gate=gate(m,c) if len(m) else {"passed":False,"checks":{}}
    args.output.mkdir(parents=True,exist_ok=True)
    cand.to_csv(args.output/"candidate_metadata_v3.csv",index=False)
    if len(m): m.to_csv(args.output/"frozen_matched_cohort_v3.csv",index=False)

    prior_names=set(prior.scientific_name.astype(str)); prior_keys=set(pd.to_numeric(prior.speciesKey,errors="coerce").dropna().astype(int))
    old_names=set(v1.scientific_name.astype(str))|set(v2.scientific_name.astype(str))
    old_keys=set(pd.to_numeric(v1.speciesKey,errors="coerce").dropna().astype(int))|set(pd.to_numeric(v2.speciesKey,errors="coerce").dropna().astype(int))
    cand_names=set(cand.scientific_name.astype(str)); cand_keys=set(pd.to_numeric(cand.speciesKey,errors="coerce").dropna().astype(int))

    result={"schema":"acsp.e8_fresh_observation_balanced_cohort.result.v3",
      "candidate_metadata_rows":int(len(cand)),
      "complete_candidate_metadata":int(cand.metadata_status.eq("complete").sum()) if len(cand) else 0,
      "matched_taxa":int(len(m)),
      "overlap_with_validated96_names":len(cand_names&prior_names),
      "overlap_with_validated96_keys":len(cand_keys&prior_keys),
      "overlap_with_e8_v1_v2_candidate_names":len(cand_names&old_names),
      "overlap_with_e8_v1_v2_candidate_keys":len(cand_keys&old_keys),
      "outcomes_opened":False,"acsp_candidate_generation_run":False,
      "gate":result_gate,
      "status":"cohort_frozen_balance_passed" if result_gate.get("passed") else "stop_observation_balance_not_achieved"}
    (args.output/"cohort_result_v3.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))

if __name__=="__main__": main()
