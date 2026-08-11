#!/usr/bin/env python3
"""Evaluate the frozen local-anchor + learned-rescue development policy."""
from __future__ import annotations

import argparse
import json
import math
import platform
from pathlib import Path
import re

import numpy as np
import pandas as pd
import sklearn
from sklearn.model_selection import GroupKFold

from acsp.practical_rescue import (
    PRACTICAL_RESCUE_PROTOCOL_FINGERPRINT,
    RESCUE_CATEGORICAL_FEATURES,
    RESCUE_NUMERIC_FEATURES,
    build_rescue_features,
    local_order,
    make_rescue_estimator,
    prepare_rescue_candidates,
    protocol_fingerprint,
    select_local_anchor_rescue,
)

EARTH_RADIUS_KM = 6_371.0088


def _safe_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _ids(value: object) -> set[str]:
    if value is None or pd.isna(value):
        return set()
    return {item for item in str(value).split(";") if item and item.lower() != "nan"}


def _recovery_from_id_columns(candidates: pd.DataFrame, selected_ids: list[str]) -> float:
    if candidates.empty:
        return 0.0
    all_ids: set[str] = set()
    for value in candidates.get("all_heldout_ids", pd.Series(dtype=str)).dropna():
        all_ids |= _ids(value)
    if not all_ids:
        return 0.0
    id_col = "candidate_id" if "candidate_id" in candidates.columns else "site_id"
    chosen = candidates[candidates[id_col].astype(str).isin(set(map(str, selected_ids)))]
    recovered: set[str] = set()
    for value in chosen.get("covered_heldout_ids", pd.Series(dtype=str)).dropna():
        recovered |= _ids(value)
    return len(recovered & all_ids) / len(all_ids)


def _haversine_cross_km(a_lat, a_lon, b_lat, b_lon) -> np.ndarray:
    alat=np.radians(np.asarray(a_lat,float))[:,None]; alon=np.radians(np.asarray(a_lon,float))[:,None]
    blat=np.radians(np.asarray(b_lat,float))[None,:]; blon=np.radians(np.asarray(b_lon,float))[None,:]
    dlat=alat-blat; dlon=alon-blon
    x=np.sin(dlat/2)**2+np.cos(alat)*np.cos(blat)*np.sin(dlon/2)**2
    return 2*EARTH_RADIUS_KM*np.arcsin(np.sqrt(np.clip(x,0,1)))


def _recovery_from_heldout_coordinates(selected: pd.DataFrame, heldout: pd.DataFrame, radius_km: float = 10.0) -> float:
    if selected.empty or heldout.empty:
        return 0.0
    lat_col = "_latitude" if "_latitude" in heldout.columns else "latitude"
    lon_col = "_longitude" if "_longitude" in heldout.columns else "longitude"
    hlat=pd.to_numeric(heldout[lat_col],errors="coerce"); hlon=pd.to_numeric(heldout[lon_col],errors="coerce")
    valid=hlat.notna()&hlon.notna(); hlat=hlat[valid].to_numpy(float); hlon=hlon[valid].to_numpy(float)
    if len(hlat)==0: return 0.0
    d=_haversine_cross_km(pd.to_numeric(selected.latitude,errors="coerce"),pd.to_numeric(selected.longitude,errors="coerce"),hlat,hlon)
    return float(np.mean(np.min(d,axis=0)<=float(radius_km)))


def _standard_folds(roots: list[Path]) -> list[dict[str, object]]:
    folds=[]; pattern=re.compile(r"pair_(\d+)/fold_(\d+)/candidates\.csv$")
    for root in roots:
        result_files=list(root.rglob("fold_method_comparison.csv"))
        if len(result_files)!=1: raise ValueError(f"expected one fold_method_comparison.csv under {root}, found {len(result_files)}")
        results=pd.read_csv(result_files[0])
        cohort="mixed" if "mixed" in str(root).lower() else "plants"
        for path in sorted(root.rglob("candidates.csv")):
            match=pattern.search(str(path).replace("\\","/"))
            if not match: continue
            pair_id,repeat=map(int,match.groups())
            local=results[(results.pair_id==pair_id)&(results.repeat==repeat)&(results.decision_method=="local_evidence_top_k")]
            if local.empty: raise ValueError(f"missing local baseline {cohort} pair {pair_id} repeat {repeat}")
            candidates=_safe_csv(path)
            folds.append({
                "source":"model_selection_48","group_id":f"{cohort}_{pair_id}","pair_id":pair_id,"repeat":repeat,
                "taxon_group":str(local.taxon_group.iloc[0]),"scientific_name":str(local.scientific_name.iloc[0]),
                "region_name":str(local.region_name.iloc[0]),"candidates":candidates,"heldout":None,
                "local_recall":float(local.heldout_recall.iloc[0]) if str(local.status.iloc[0])=="ok" else 0.0,
            })
    return folds


def _sdm_extension_folds(root: Path) -> list[dict[str, object]]:
    folds=[]
    for manifest_path in sorted(root.rglob("pair_manifest.json")):
        pair_root=manifest_path.parent; manifest=json.loads(manifest_path.read_text())
        pair_id=int(manifest["pair_id"]); group_id=f"sdm_{pair_id}"
        for repeat in range(1,6):
            fold_root=pair_root/f"fold_{repeat:03d}"
            candidates=_safe_csv(fold_root/"candidate_pool_pre_outcome.csv")
            heldout=_safe_csv(fold_root/"held_out_occurrences.csv")
            result=_safe_csv(fold_root/"fold_result.csv")
            local=result[result.decision_method.eq("local_evidence_top_k")] if not result.empty else pd.DataFrame()
            local_recall=float(local.heldout_recall.iloc[0]) if not local.empty and str(local.method_status.iloc[0])=="ok" else 0.0
            folds.append({
                "source":"locked_extension_24","group_id":group_id,"pair_id":pair_id,"repeat":repeat,
                "taxon_group":str(manifest["taxon_group"]),"scientific_name":str(manifest["scientific_name"]),
                "region_name":str(manifest["region_name"]),"candidates":candidates,"heldout":heldout,
                "local_recall":local_recall,
            })
    return folds


def _feature_table_and_target(fold: dict[str, object]) -> pd.DataFrame:
    candidates=fold["candidates"]
    if not isinstance(candidates,pd.DataFrame) or candidates.empty: return pd.DataFrame()
    eligible=prepare_rescue_candidates(candidates)
    if eligible.empty: return pd.DataFrame()
    features=build_rescue_features(candidates,str(fold["taxon_group"]))
    order=local_order(eligible); anchor=int(order[0])
    all_ids:set[str]=set()
    for value in eligible.get("all_heldout_ids",pd.Series(dtype=str)).dropna(): all_ids|=_ids(value)
    anchor_ids=_ids(eligible.iloc[anchor].get("covered_heldout_ids"))
    residual=all_ids-anchor_ids; denominator=max(len(all_ids),1)
    target=[]
    for _,row in eligible.iterrows(): target.append(len(_ids(row.get("covered_heldout_ids"))&residual)/denominator)
    out=features[[*RESCUE_NUMERIC_FEATURES,*RESCUE_CATEGORICAL_FEATURES,"_source_index"]].copy()
    out["target_residual_fraction"]=target
    out["group_id"]=str(fold["group_id"]); out["repeat"]=int(fold["repeat"])
    return out


def _fit_predict_crossfit(model_folds: list[dict[str, object]]) -> tuple[pd.DataFrame, object]:
    tables=[_feature_table_and_target(fold) for fold in model_folds]
    training=pd.concat([t for t in tables if not t.empty],ignore_index=True)
    groups=training["group_id"].astype(str)
    predictions=np.full(len(training),np.nan,float)
    X=training[[*RESCUE_NUMERIC_FEATURES,*RESCUE_CATEGORICAL_FEATURES]]; y=training.target_residual_fraction
    for train_index,test_index in GroupKFold(n_splits=8).split(X,y,groups=groups):
        estimator=make_rescue_estimator(); estimator.fit(X.iloc[train_index],y.iloc[train_index]); predictions[test_index]=estimator.predict(X.iloc[test_index])
    if not np.isfinite(predictions).all(): raise RuntimeError("incomplete cross-fitted rescue predictions")
    training["prediction"]=predictions
    final_estimator=make_rescue_estimator(); final_estimator.fit(X,y)
    return training,final_estimator


def _select_with_predictions(fold: dict[str, object], predictions: np.ndarray) -> tuple[float,str]:
    candidates=fold["candidates"]
    if not isinstance(candidates,pd.DataFrame) or candidates.empty: return 0.0,""
    eligible=prepare_rescue_candidates(candidates)
    selected=select_local_anchor_rescue(candidates,predictions)
    ids_col="candidate_id" if "candidate_id" in selected.columns else "site_id"
    selected_ids=selected[ids_col].astype(str).tolist()
    if fold["source"]=="model_selection_48":
        recall=_recovery_from_id_columns(eligible,selected_ids)
    else:
        recall=_recovery_from_heldout_coordinates(selected,fold["heldout"],10.0)
    return recall,";".join(selected_ids)


def _pair_inference(pair: pd.DataFrame, source: str|None=None) -> dict[str,object]:
    work=pair if source is None else pair[pair.source.eq(source)]
    difference=(work.local_anchor_rescue-work.local_evidence_top_k).to_numpy(float)
    if len(difference)==0: return {"pairs":0}
    rng=np.random.default_rng(20260812); draws=30000
    bootstrap=rng.choice(difference,size=(draws,len(difference)),replace=True).mean(axis=1)
    null=(rng.choice(np.array([-1.,1.]),size=(draws,len(difference)))*difference).mean(axis=1)
    observed=abs(float(difference.mean()))
    return {
      "pairs":int(len(difference)),"mean_difference":float(difference.mean()),
      "bootstrap_95ci_low":float(np.quantile(bootstrap,.025)),"bootstrap_95ci_high":float(np.quantile(bootstrap,.975)),
      "sign_flip_p":float((1+np.sum(np.abs(null)>=observed))/(draws+1)),
      "positive_pairs":int(np.sum(difference>1e-12)),"negative_pairs":int(np.sum(difference< -1e-12)),"tied_pairs":int(np.sum(np.abs(difference)<=1e-12)),
      "difference_sd":float(np.std(difference,ddof=1)) if len(difference)>1 else 0.0,
    }


def run(standard_roots:list[Path],sdm_root:Path|None,protocol_path:Path,output:Path)->dict[str,object]:
    protocol=json.loads(protocol_path.read_text()); actual=protocol_fingerprint(protocol)
    if actual!=PRACTICAL_RESCUE_PROTOCOL_FINGERPRINT or protocol.get("protocol_fingerprint")!=actual: raise ValueError("rescue protocol fingerprint mismatch")
    expected_runtime = protocol.get("software_contract", {})
    actual_runtime = {
        "python": platform.python_version(),
        "scikit_learn": sklearn.__version__,
        "pandas": pd.__version__,
        "numpy": np.__version__,
    }
    for key in ("python", "scikit_learn", "pandas", "numpy"):
        if str(expected_runtime.get(key)) != str(actual_runtime[key]):
            raise ValueError(
                f"frozen rescue runtime mismatch for {key}: "
                f"expected {expected_runtime.get(key)!r}, got {actual_runtime[key]!r}"
            )
    model_folds=_standard_folds(standard_roots)
    if len(model_folds)!=240 or len({f['group_id'] for f in model_folds})!=48: raise ValueError("expected 48 pairs / 240 model-selection folds")
    training,final_estimator=_fit_predict_crossfit(model_folds)
    lookup={(str(g),int(r)):d.copy() for (g,r),d in training.groupby(["group_id","repeat"])}
    rows=[]
    for fold in model_folds:
        candidates=fold["candidates"]
        if isinstance(candidates,pd.DataFrame) and not candidates.empty:
            pred_table=lookup[(str(fold['group_id']),int(fold['repeat']))].sort_values("_source_index")
            recall,selected_ids=_select_with_predictions(fold,pred_table.prediction.to_numpy(float))
        else: recall,selected_ids=0.0,""
        rows.append({**{k:fold[k] for k in ['source','group_id','pair_id','repeat','taxon_group','scientific_name','region_name']},"local_anchor_rescue":recall,"local_evidence_top_k":float(fold['local_recall']),"selected_ids":selected_ids})

    # Reproduce and verify the 48-pair model-selection snapshot before any
    # locked-extension outcome is loaded or scored. This ordering keeps runtime
    # corrections auditable and independent of the 24-pair extension values.
    model_fold_table = pd.DataFrame(rows)
    model_pair = model_fold_table.groupby(
        ["source", "group_id", "taxon_group"], as_index=False
    )[["local_anchor_rescue", "local_evidence_top_k"]].mean()
    model_inf = _pair_inference(model_pair, "model_selection_48")
    expected=protocol.get('development_design',{}).get('model_selection_result',{})
    if expected:
        if not math.isclose(model_inf['mean_difference'],float(expected['mean_difference']),abs_tol=5e-4):
            raise ValueError(f"48-pair rescue snapshot changed: {model_inf['mean_difference']}")

    extension_folds=[]
    if sdm_root is not None:
        extension_folds=_sdm_extension_folds(sdm_root)
        if len(extension_folds)!=120 or len({f['group_id'] for f in extension_folds})!=24: raise ValueError(f"expected 24 pairs / 120 extension folds, found {len(extension_folds)}")
        for fold in extension_folds:
            candidates=fold['candidates']
            if isinstance(candidates,pd.DataFrame) and not candidates.empty:
                features=build_rescue_features(candidates,str(fold['taxon_group']))
                X=features[[*RESCUE_NUMERIC_FEATURES,*RESCUE_CATEGORICAL_FEATURES]]
                predictions=final_estimator.predict(X)
                recall,selected_ids=_select_with_predictions(fold,predictions)
            else: recall,selected_ids=0.0,""
            rows.append({**{k:fold[k] for k in ['source','group_id','pair_id','repeat','taxon_group','scientific_name','region_name']},"local_anchor_rescue":recall,"local_evidence_top_k":float(fold['local_recall']),"selected_ids":selected_ids})

    fold_table=pd.DataFrame(rows)
    pair=fold_table.groupby(["source","group_id","taxon_group"],as_index=False)[["local_anchor_rescue","local_evidence_top_k"]].mean()
    extension_inf=_pair_inference(pair,"locked_extension_24") if extension_folds else {"pairs":0}
    combined_inf=_pair_inference(pair,None)
    gate=(combined_inf['pairs']==72 and combined_inf['mean_difference']>=.015 and combined_inf['bootstrap_95ci_low']>0 and combined_inf['sign_flip_p']<.05) if extension_folds else False
    output.mkdir(parents=True,exist_ok=True); fold_table.to_csv(output/'fold_method_comparison.csv',index=False); pair.to_csv(output/'pair_level_comparison.csv',index=False)
    manifest={
      "status":"72_pair_development_gate_evaluated" if extension_folds else "48_pair_model_selection_reproduced",
      "protocol_fingerprint":actual,"model_selection_pairs":48,"locked_extension_pairs":24 if extension_folds else 0,"combined_pairs":int(len(pair)),
      "model_selection_inference":model_inf,"locked_extension_inference":extension_inf,"combined_inference":combined_inf,"development_gate_passed":bool(gate),
      "development_gate_rule":"combined mean >= 0.015, bootstrap lower > 0, sign-flip p < 0.05 on all 72 pairs",
      "extension_outcomes_used_for_model_or_policy_selection":False,"frozen_runtime":actual_runtime,"fresh_confirmation_required":True,
    }
    (output/'development_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


def main():
    p=argparse.ArgumentParser();p.add_argument('--standard-root',action='append',type=Path,required=True);p.add_argument('--sdm-root',type=Path);p.add_argument('--protocol',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(json.dumps(run(a.standard_root,a.sdm_root,a.protocol,a.output),indent=2))
if __name__=='__main__':main()
