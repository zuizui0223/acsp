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
            r=requests.get(GBIF,params=params,timeout=45,headers={"User-Agent":"acsp-e8-fresh-cohort/1.0"})
            if r.status_code==200:return r.json()
            last=RuntimeError(f"HTTP {r.status_code}")
        except Exception as e:last=e
        time.sleep(1.2*(k+1))
    raise RuntimeError(str(last))

def count(base,**extra):
    p=dict(base);p.update(extra);p["limit"]=0
    return int(get_json(p).get("count",0))

def top_dataset_share(base,total):
    p=dict(base);p.update({"limit":0,"facet":"datasetKey","facetLimit":50})
    js=get_json(p); vals=[]
    for f in js.get("facets") or []:
        for item in f.get("counts") or []:
            try:vals.append(int(item["count"]))
            except Exception:pass
    return float(max(vals)/total) if total>0 and vals else float("nan")

def metrics(row):
    base={"taxonKey":int(row.speciesKey),"geometry":rectangle_wkt((float(row.west),float(row.south),float(row.east),float(row.north))),
          "hasCoordinate":"true","hasGeospatialIssue":"false","occurrenceStatus":"PRESENT"}
    total=count(base)
    vals={
      "current_coordinate_record_count":total,
      "log1p_current_coordinate_record_count":math.log1p(total),
      "human_observation_fraction":count(base,basisOfRecord="HUMAN_OBSERVATION")/total if total else np.nan,
      "machine_observation_fraction":count(base,basisOfRecord="MACHINE_OBSERVATION")/total if total else np.nan,
      "preserved_specimen_fraction":count(base,basisOfRecord="PRESERVED_SPECIMEN")/total if total else np.nan,
      "recent_2021_2025_fraction":count(base,year="2021,2025")/total if total else np.nan,
      "top_dataset_share":top_dataset_share(base,total),
    }
    return vals

def exclusions(contract,prior):
    names=set(prior["scientific_name"].dropna().astype(str))
    for p in contract["exclusions"]["repository_exclusion_files"]:
        path=Path(p)
        if path.exists():
            try:
                x=pd.read_csv(path)
                if "scientific_name" in x:names.update(x.scientific_name.dropna().astype(str))
            except Exception:pass
    return names

def deterministic_candidates(frame,n):
    f=frame.sort_values(["coordinate_records","scientific_name"],kind="mergesort").reset_index(drop=True)
    if len(f)<=n:return f
    idx=np.unique(np.round(np.linspace(0,len(f)-1,n)).astype(int))
    return f.iloc[idx].reset_index(drop=True)

def scale_region(frame):
    z=frame.copy()
    for f in FEATURES:
        x=z[f].to_numpy(float); med=float(np.nanmedian(x))
        q1,q3=np.nanquantile(x,[.25,.75]); scale=max(float(q3-q1),0.10)
        z[f+"_z"]=(x-med)/scale
    return z

def choose_two(frame,max_dist):
    a=frame[frame.taxon_group.eq("animal")].reset_index(drop=True)
    p=frame[frame.taxon_group.eq("plant")].reset_index(drop=True)
    if len(a)<2 or len(p)<2:return None
    best=None
    for ai in itertools.combinations(range(len(a)),2):
      for pi in itertools.combinations(range(len(p)),2):
        for order in (pi,pi[::-1]):
          ds=[]
          pairs=[]
          for x,y in zip(ai,order):
            va=a.loc[x,[f+"_z" for f in FEATURES]].to_numpy(float)
            vp=p.loc[y,[f+"_z" for f in FEATURES]].to_numpy(float)
            d=float(np.linalg.norm(va-vp));ds.append(d);pairs.append((x,y,d))
          key=(sum(ds),max(ds),tuple((str(a.loc[x,"scientific_name"]),str(p.loc[y,"scientific_name"])) for x,y,_ in pairs))
          if max(ds)<=max_dist and (best is None or key<best[0]):best=(key,pairs)
    if best is None:return None
    out=[]
    for rank,(x,y,d) in enumerate(best[1],1):
      for side,row in (("animal",a.loc[x]),("plant",p.loc[y])):
        rec=row.to_dict();rec["match_pair_within_region"]=rank;rec["match_distance"]=d;out.append(rec)
    return pd.DataFrame(out)

def smd(x,g):
    a=x[g==1];p=x[g==0]
    den=math.sqrt((np.var(a,ddof=1)+np.var(p,ddof=1))/2)
    return 0.0 if den==0 else float((np.mean(a)-np.mean(p))/den)

def gate(matched,contract):
    g=matched.taxon_group.eq("animal").astype(int).to_numpy()
    X=matched[FEATURES].to_numpy(float)
    z=StandardScaler().fit_transform(X)
    m=LogisticRegression(C=1,solver="lbfgs",max_iter=2000).fit(z,g)
    e=m.predict_proba(z)[:,1]
    ess={}
    for v,name in ((1,"animal"),(0,"plant")):
      ev=np.clip(e[g==v],.05,.95); pa=float(g.mean())
      w=(pa/ev) if v==1 else ((1-pa)/(1-ev))
      ess[name]=float((w.sum()**2)/(w@w))
    smds={f:abs(smd(matched[f].to_numpy(float),g)) for f in FEATURES}
    cfg=contract["freeze_gate"]
    checks={
      "regions":matched.region_name.nunique()==cfg["exact_regions_with_two_pairs"],
      "pairs":matched.groupby(["region_name","match_pair_within_region"]).ngroups==cfg["exact_matched_pairs"],
      "taxa":len(matched)==cfg["exact_taxa"],
      "unique_taxa":matched["scientific_name"].astype(str).nunique()==cfg["exact_unique_scientific_names"],
      "max_smd":max(smds.values())<=cfg["maximum_global_absolute_smd"],
      "overlap":float(np.mean((e>=.10)&(e<=.90)))>=cfg["minimum_group_propensity_overlap_fraction_0_10_0_90"],
      "ess_animal":ess["animal"]>=cfg["minimum_propensity_ess_each_group"],
      "ess_plant":ess["plant"]>=cfg["minimum_propensity_ess_each_group"],
    }
    return {"checks":checks,"passed":all(checks.values()),"max_absolute_smd":max(smds.values()),
            "absolute_smd":smds,"propensity_min":float(e.min()),"propensity_max":float(e.max()),
            "overlap_fraction":float(np.mean((e>=.10)&(e<=.90))),"ess":ess}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--contract",type=Path,required=True);ap.add_argument("--prior-cohort",type=Path,required=True);ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args(); c=json.loads(args.contract.read_text()); prior=pd.read_csv(args.prior_cohort)
    exc=exclusions(c,prior); prefixes=tuple(c["exclusions"]["excluded_name_prefixes"]); rows=[]; matched=[]; used_final_names=set()
    n=int(c["fresh_design"]["candidate_taxa_per_region_group"])
    for geo,region,w,s,e,north in REGION_CELLS:
      region_rows=[]
      for group,kingdom in TAXON_GROUPS.items():
        f=taxon_frame((w,s,e,north),kingdom,int(c["fresh_design"]["facet_limit"]),int(c["fresh_design"]["minimum_coordinate_records"]))
        if f.empty:continue
        f=f[~f.scientific_name.astype(str).isin(exc)]
        f=f[~f.scientific_name.astype(str).str.startswith(prefixes)].copy()
        f=deterministic_candidates(f,n)
        for rr in f.itertuples(index=False):
          rec={"taxon_group":group,"geographic_stratum":geo,"region_name":region,"west":w,"south":s,"east":e,"north":north,
               "speciesKey":int(rr.speciesKey),"scientific_name":str(rr.scientific_name),"sampling_frame_coordinate_records":int(rr.coordinate_records)}
          try:rec.update(metrics(pd.Series(rec)));rec["metadata_status"]="complete"
          except Exception as ex:rec["metadata_status"]="failed";rec["error"]=str(ex)
          rows.append(rec);region_rows.append(rec)
      rf=pd.DataFrame(region_rows)
      rf=rf[rf.metadata_status.eq("complete")].dropna(subset=FEATURES).reset_index(drop=True)
      rf=rf[~rf["scientific_name"].astype(str).isin(used_final_names)].reset_index(drop=True)
      if not rf.empty:
        sel=choose_two(scale_region(rf),float(c["matching"]["maximum_pair_distance"]))
        if sel is not None:
          chosen=set(sel["scientific_name"].astype(str))
          if len(chosen)!=4 or chosen & used_final_names:
            raise RuntimeError("global scientific-name uniqueness violated before cohort freeze")
          used_final_names.update(chosen)
          matched.append(sel)
    cand=pd.DataFrame(rows); m=pd.concat(matched,ignore_index=True) if matched else pd.DataFrame()
    g=gate(m,c) if len(m) else {"passed":False,"checks":{}}
    args.output.mkdir(parents=True,exist_ok=True);cand.to_csv(args.output/"candidate_metadata.csv",index=False)
    if len(m):m.to_csv(args.output/"frozen_matched_cohort.csv",index=False)
    result={"schema":"acsp.e8_fresh_observation_balanced_cohort.result.v2","candidate_metadata_rows":len(cand),
            "complete_candidate_metadata":int(cand.metadata_status.eq("complete").sum()),"matched_taxa":len(m),
            "outcomes_opened":False,"acsp_candidate_generation_run":False,"gate":g,
            "status":"cohort_frozen_balance_passed" if g.get("passed") else "stop_observation_balance_not_achieved"}
    (args.output/"cohort_result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
if __name__=="__main__":main()
