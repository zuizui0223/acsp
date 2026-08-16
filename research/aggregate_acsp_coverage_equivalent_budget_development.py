#!/usr/bin/env python3
"""Aggregate the predeclared ACSP coverage-equivalent budget development."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

EXPECTED = "c5c63afc1e5f9d3857938dd4801e33ef2cc78b26d45bd483a36a60e32f3dcdf4"
EXPECTED_COHORT_SHA256 = "fe0aa6222af28a32d3e6b76dea317a8aeb67776d4d8c9289625cfe4a45f921a1"


def canonical(path: Path) -> tuple[dict, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = str(payload.pop("protocol_fingerprint", ""))
    calculated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    if expected != calculated:
        raise ValueError("development protocol fingerprint mismatch")
    payload["protocol_fingerprint"] = expected
    return payload, calculated


def sha256_file(path: Path) -> str:
    d=hashlib.sha256()
    with path.open("rb") as h:
        for block in iter(lambda:h.read(1024*1024), b""):
            d.update(block)
    return d.hexdigest()


def bootstrap_ci(values: np.ndarray, draws: int, seed: int) -> list[float]:
    values=np.asarray(values,dtype=float)
    rng=np.random.default_rng(seed)
    means=np.empty(int(draws))
    for i in range(int(draws)):
        means[i]=rng.choice(values,size=len(values),replace=True).mean()
    return [float(np.quantile(means,.025)),float(np.quantile(means,.975))]


def exact_signflip(values: np.ndarray) -> float:
    values=np.asarray(values,dtype=float)
    nz=values[np.abs(values)>1e-15]
    if len(nz)==0: return 1.0
    observed=float(nz.sum())
    sums=np.zeros(1)
    for value in nz:
        sums=np.concatenate([sums+value,sums-value])
    return float(np.mean(sums>=observed-1e-12))


def inference(values: np.ndarray, draws: int, seed: int) -> dict:
    values=np.asarray(values,dtype=float)
    if not len(values): return {"n":0}
    return {
        "n":int(len(values)),
        "mean":float(values.mean()),
        "bootstrap_95ci":bootstrap_ci(values,draws,seed),
        "exact_one_sided_sign_flip_p":exact_signflip(values),
        "positive":int((values>0).sum()),
        "negative":int((values<0).sum()),
        "ties":int((values==0).sum()),
    }


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--development-protocol",type=Path,required=True)
    p.add_argument("--cohort",type=Path,required=True)
    p.add_argument("--results-root",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    protocol,fp=canonical(a.development_protocol)
    if fp!=EXPECTED: raise ValueError(f"unexpected development protocol {fp}")
    if sha256_file(a.cohort)!=EXPECTED_COHORT_SHA256: raise ValueError("cohort checksum mismatch")
    cohort=pd.read_csv(a.cohort)

    pair_paths=sorted(a.results_root.glob("**/pair_results.csv"))
    curve_paths=sorted(a.results_root.glob("**/coverage_curve_results.csv"))
    summary_paths=sorted(a.results_root.glob("**/island_summary.json"))
    pairs=pd.concat([pd.read_csv(x) for x in pair_paths],ignore_index=True) if pair_paths else pd.DataFrame()
    curves=[]
    for path in curve_paths:
        try: curves.append(pd.read_csv(path))
        except pd.errors.EmptyDataError: pass
    curves=pd.concat(curves,ignore_index=True) if curves else pd.DataFrame()
    island_summaries=[json.loads(x.read_text()) for x in summary_paths]

    declared=set(cohort.pair_id.astype(int))
    observed=set(pairs.get("pair_id",pd.Series(dtype=int)).dropna().astype(int))
    missing=sorted(declared-observed)
    infrastructure=[x for s in island_summaries for x in s.get("infrastructure_failures",[])]
    completed=pairs[pairs.get("status",pd.Series(dtype=str)).eq("ok")].copy()
    values=completed.get("mean_auc_lift",pd.Series(dtype=float)).to_numpy(float)
    draws=int(protocol["development_estimands"]["bootstrap_draws"])
    primary=inference(values,draws,20260821)
    gate=protocol["development_estimands"]["primary_gate"]
    primary_pass=bool(
        not missing and not infrastructure and len(values)>0
        and primary["mean"]>float(gate["mean_auc_lift_gt"])
        and primary["bootstrap_95ci"][0]>float(gate["bootstrap_95ci_lower_gt"])
        and primary["exact_one_sided_sign_flip_p"]<float(gate["exact_one_sided_sign_flip_p_lt"])
    )

    target_results={}
    targets=[float(x) for x in protocol["budget"]["target_land_grid_coverage_fractions"]]
    for i,target in enumerate(targets):
        token=str(target).replace(".","p")
        lift_col=f"mean_lift_c{token}"
        ss=f"mean_support_sites_c{token}"; cs=f"mean_control_sites_c{token}"
        sr=f"mean_support_recall_c{token}"; cr=f"mean_control_recall_c{token}"
        if lift_col not in completed: continue
        sub=completed.dropna(subset=[lift_col]).copy()
        target_results[str(target)]={
            "lift":inference(sub[lift_col].to_numpy(float),draws,20260830+i),
            "mean_support_sites":float(sub[ss].mean()) if ss in sub else None,
            "mean_control_sites":float(sub[cs].mean()) if cs in sub else None,
            "mean_site_count_difference":float((sub[ss]-sub[cs]).mean()) if ss in sub and cs in sub else None,
            "mean_support_recall":float(sub[sr].mean()) if sr in sub else None,
            "mean_control_recall":float(sub[cr].mean()) if cr in sub else None,
            "mean_support_recall_per_site":float((sub[sr]/sub[ss]).replace([np.inf,-np.inf],np.nan).mean()) if sr in sub and ss in sub else None,
            "mean_control_recall_per_site":float((sub[cr]/sub[cs]).replace([np.inf,-np.inf],np.nan).mean()) if cr in sub and cs in sub else None,
        }

    island_effects={}
    for island,frame in completed.groupby("island_id"):
        island_effects[str(island)]={
            "pairs":int(len(frame)),
            "mean_auc_lift":float(frame["mean_auc_lift"].mean()),
        }
    stratum_effects={}
    for stratum,frame in completed.groupby("record_count_stratum"):
        stratum_effects[str(int(stratum))]=inference(frame["mean_auc_lift"].to_numpy(float),draws,20260900+int(stratum))

    deployment_rate=float(pairs.get("deployment_information_adequate",pd.Series(dtype=bool)).fillna(False).astype(bool).mean()) if len(pairs) else 0.0
    benchmark_rate=float(pairs.get("benchmark_evaluable",pd.Series(dtype=bool)).fillna(False).astype(bool).mean()) if len(pairs) else 0.0
    summary={
        "status":"development_complete" if not missing and not infrastructure else "development_incomplete_infrastructure",
        "development_protocol_fingerprint":fp,
        "cohort_sha256":EXPECTED_COHORT_SHA256,
        "declared_pairs":int(len(cohort)),
        "pair_rows":int(len(pairs)),
        "deployment_information_adequate_pairs":int(pairs.get("deployment_information_adequate",pd.Series(dtype=bool)).fillna(False).astype(bool).sum()) if len(pairs) else 0,
        "deployment_information_adequacy_rate":deployment_rate,
        "benchmark_evaluable_pairs":int(pairs.get("benchmark_evaluable",pd.Series(dtype=bool)).fillna(False).astype(bool).sum()) if len(pairs) else 0,
        "benchmark_evaluable_rate":benchmark_rate,
        "completed_auc_pairs":int(len(completed)),
        "primary_auc_lift":primary,
        "primary_gate_pass":primary_pass,
        "coverage_targets":target_results,
        "island_effects":island_effects,
        "record_stratum_effects":stratum_effects,
        "missing_pair_results":missing,
        "infrastructure_failures":infrastructure,
        "confirmation_24_reused":False,
        "frozen_192_consumed":False,
        "decision": (
            "retain_q10_and_proceed_to_route_time_development" if primary_pass
            else "drop_q10_from_transferable_operational_core_and_retain_geometry_only_coverage"
        ),
    }
    a.out.mkdir(parents=True,exist_ok=True)
    pairs.sort_values("pair_id").to_csv(a.out/"pair_results.csv",index=False)
    curves.to_csv(a.out/"coverage_curve_results.csv",index=False)
    (a.out/"development_summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps(summary,indent=2))

if __name__=="__main__": main()
