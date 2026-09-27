#!/usr/bin/env python3
"""Fetch count-only GBIF observation-architecture metadata for the frozen ACSP E8 cohort."""
from __future__ import annotations
import argparse, json, math, time
from pathlib import Path
import numpy as np
import pandas as pd
import requests

ENDPOINT="https://api.gbif.org/v1/occurrence/search"

def rectangle_wkt(row):
    w,s,e,n=(float(row[x]) for x in ("west","south","east","north"))
    return f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))"

def request_json(params, retries=4):
    last=None
    for attempt in range(retries):
        try:
            r=requests.get(ENDPOINT,params=params,timeout=45,headers={"User-Agent":"acsp-e8-observation-diagnostic/1.0"})
            if r.status_code==200:
                return r.json()
            last=RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        except Exception as exc:
            last=exc
        time.sleep(1.5*(attempt+1))
    raise RuntimeError(str(last))

def count(base, **extra):
    p=dict(base); p.update(extra); p["limit"]=0
    return int(request_json(p).get("count",0))

def dataset_concentration(base,total):
    p=dict(base); p.update({"limit":0,"facet":"datasetKey","facetLimit":50})
    js=request_json(p)
    facets=js.get("facets") or []
    counts=[]
    for f in facets:
        if not isinstance(f,dict): continue
        for item in f.get("counts") or []:
            try: counts.append(int(item["count"]))
            except Exception: pass
    return (max(counts)/total if total>0 and counts else float("nan"))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--cohort",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    frame=pd.read_csv(args.cohort)
    if len(frame)!=96:
        raise RuntimeError(f"expected 96 frozen taxa, found {len(frame)}")
    rows=[]
    for row in frame.sort_values("pair_id").itertuples(index=False):
        base={
            "taxonKey":int(row.speciesKey),
            "geometry":rectangle_wkt(row._asdict()),
            "hasCoordinate":"true",
            "hasGeospatialIssue":"false",
            "occurrenceStatus":"PRESENT",
        }
        rec={"pair_id":int(row.pair_id),"scientific_name":str(row.scientific_name),
             "taxon_group":str(row.taxon_group),"region_name":str(row.region_name),
             "record_count_stratum":int(row.record_count_stratum),"status":"complete","error":""}
        try:
            total=count(base)
            human=count(base,basisOfRecord="HUMAN_OBSERVATION")
            machine=count(base,basisOfRecord="MACHINE_OBSERVATION")
            specimen=count(base,basisOfRecord="PRESERVED_SPECIMEN")
            recent=count(base,year="2021,2025")
            rec.update({
                "current_coordinate_record_count":total,
                "log1p_current_coordinate_record_count":float(math.log1p(total)),
                "human_observation_fraction":float(human/total) if total else float("nan"),
                "machine_observation_fraction":float(machine/total) if total else float("nan"),
                "preserved_specimen_fraction":float(specimen/total) if total else float("nan"),
                "recent_2021_2025_fraction":float(recent/total) if total else float("nan"),
                "top_dataset_share":float(dataset_concentration(base,total)),
            })
        except Exception as exc:
            rec["status"]="metadata_failed"
            rec["error"]=f"{type(exc).__name__}: {exc}"
        rows.append(rec)
    out=pd.DataFrame(rows)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    out.to_csv(args.output,index=False)
    print(out["status"].value_counts(dropna=False).to_string())
    print(json.dumps({"rows":len(out),"complete":int(out.status.eq("complete").sum()),
                      "row_level_occurrences_opened":False},indent=2))

if __name__=="__main__":
    main()
