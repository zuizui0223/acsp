#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from acsp.taxon_patches import RAW_TERRAIN_FEATURES, ROBUST_TERRAIN_FEATURES, _prototype_coordinates, _with_robust_features
from acsp.validated_robust import VALIDATED_ROBUST_PRIMARY_RADIUS_KM, VALIDATED_ROBUST_SUPPORT_FRACTION, validated_robust_candidate_patches
from country_framed_robust_integration import fetch_country_occurrences
from geoboundaries_v6_provider import fetch_geoboundaries_country_geometry
from regional_country_lattice import LATTICE_STEP_DEG, POINTS_PER_REGIONAL_TILE, build_regional_country_surface
from run_country_framed_integration_development_v1_1 import fetch_recent_country_occurrences, recovery_fraction, same_size_random_recovery, taxon_bootstrap_mean_ci, _finite_mean, _geometry_digest_from_source_version

ROOT=Path(__file__).resolve().parents[1]
PROTOCOL_PATH=ROOT/"validation"/"acsp_country_framed_robust_integration_development_v2.json"
EXPECTED_PROTOCOL_FINGERPRINT="7535e749d3cc04c8d49db13957da53685a5050eec7d1e9e2d6624348332a56f9"


def _protocol():
    payload=json.loads(PROTOCOL_PATH.read_text(encoding="utf-8")); stored=str(payload.pop("protocol_fingerprint","")); calc=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    if stored!=EXPECTED_PROTOCOL_FINGERPRINT or calc!=EXPECTED_PROTOCOL_FINGERPRINT: raise ValueError("v2 protocol fingerprint mismatch")
    payload["protocol_fingerprint"]=stored; return payload


def regional_terrain_inputs(occurrences: pd.DataFrame, geometry):
    from gbif_fieldmap_builder_app import extract_environment
    geometry_surface,lattice_audit=build_regional_country_surface(geometry,points_per_tile=POINTS_PER_REGIONAL_TILE)
    enriched=extract_environment(geometry_surface,list(RAW_TERRAIN_FEATURES),"latitude","longitude","2.5m")
    surface=_with_robust_features(enriched)
    surface=surface.loc[surface[list(ROBUST_TERRAIN_FEATURES)].notna().all(axis=1)].copy().reset_index(drop=True)
    if surface.empty: raise ValueError("regional lattice has no complete terrain surface points")
    proto_points=_prototype_coordinates(occurrences)
    prototypes=extract_environment(proto_points,list(RAW_TERRAIN_FEATURES),"latitude","longitude","2.5m")
    prototypes=_with_robust_features(prototypes)
    prototypes=prototypes.loc[prototypes[list(ROBUST_TERRAIN_FEATURES)].notna().all(axis=1)].copy().drop_duplicates(list(ROBUST_TERRAIN_FEATURES)).reset_index(drop=True)
    if len(prototypes)<5: raise ValueError(f"fewer than five unique complete historical terrain prototypes: {len(prototypes)}")
    return surface,prototypes,lattice_audit


def evaluate(declarations: pd.DataFrame):
    protocol=_protocol(); gate=protocol["development_gate"]; evalcfg=protocol["evaluation"]
    if len(declarations)!=24 or declarations.speciesKey.nunique()!=24: raise ValueError("v2 requires exactly 24 unique frozen declarations")
    radius=float(evalcfg["primary_recovery_radius_km"]); reps=int(evalcfg["random_baseline_repetitions"]); seedbase=int(evalcfg["random_seed"])
    if radius!=10.0 or radius!=float(VALIDATED_ROBUST_PRIMARY_RADIUS_KM): raise ValueError("v2 radius drift")
    rows=[]; patch_frames=[]
    for r in declarations.itertuples(index=False):
        base=r._asdict(); key=int(base["speciesKey"]); code=str(base.get("selected_country_code") or "").upper(); declaration=str(base.get("declaration_status") or "")
        cstatus="not_attempted_declaration_failed"; creason=""; tstatus="not_attempted_no_declared_country"; treason=""; hist_n=recent_n=tiles=geom_n=complete_n=proto_n=patch_n=0; robust=random_mean=random_q025=random_q975=lift=float("nan"); verified=""; patches=pd.DataFrame(); surface=pd.DataFrame(); recent=pd.DataFrame(columns=["latitude","longitude"])
        if declaration=="declared" and code:
            try:
                geom=fetch_geoboundaries_country_geometry(code); verified=_geometry_digest_from_source_version(geom.source_version)
                if verified!=str(base.get("geometry_canonical_sha256") or "").lower(): raise ValueError("frozen country geometry digest mismatch")
                historical=fetch_country_occurrences(key,code); hist_n=len(historical)
                surface,prototypes,audit=regional_terrain_inputs(historical,geom); tiles=int(audit.intersecting_tile_count); geom_n=int(audit.total_geometry_points); complete_n=len(surface); proto_n=len(prototypes)
                patches,support_audit=validated_robust_candidate_patches(surface,prototypes,feature_columns=ROBUST_TERRAIN_FEATURES,area_col="survey_area_id")
                patch_n=len(patches)
                if patch_n<=0: raise ValueError("frozen robust core returned zero candidate patches")
                cstatus="generated"; p=patches.copy(); p["integration_pair_id"]=int(base["integration_pair_id"]); p["speciesKey"]=key; p["scientific_name"]=str(base["scientific_name"]); p["taxon_group"]=str(base["taxon_group"]); p["framing_country_code"]=code; patch_frames.append(p)
            except Exception as exc:
                cstatus="candidate_generation_failed"; creason=f"{type(exc).__name__}: {exc}"
            try:
                recent=fetch_recent_country_occurrences(key,code,years=(2021,2025),cap=300); recent_n=len(recent); tstatus="evaluated" if recent_n>0 else "zero_recent_country_records"
            except Exception as exc:
                tstatus="recent_provider_failed"; treason=f"{type(exc).__name__}: {exc}"
            if cstatus=="generated" and tstatus=="evaluated":
                robust=recovery_fraction(recent,patches,radius); token=f"{seedbase}|{key}|{code}".encode(); rs=int(hashlib.sha256(token).hexdigest()[:16],16)%(2**32-1)
                random_mean,random_q025,random_q975=same_size_random_recovery(recent,surface,selected_count=patch_n,radius_km=radius,repetitions=reps,seed=rs); lift=float(robust-random_mean)
        rows.append({**base,"candidate_generation_status":cstatus,"candidate_generation_failure_reason":creason,"temporal_status":tstatus,"temporal_failure_reason":treason,"historical_training_occurrence_rows":hist_n,"recent_heldout_occurrence_rows":recent_n,"regional_tile_count":tiles,"geometry_surface_points":geom_n,"complete_terrain_surface_points":complete_n,"prototype_rows":proto_n,"candidate_patch_count":patch_n,"verified_geometry_canonical_sha256":verified,"primary_radius_km":radius,"robust_recall":robust,"random_recall_mean":random_mean,"random_recall_q025":random_q025,"random_recall_q975":random_q975,"robust_minus_random_recall":lift})
    results=pd.DataFrame(rows); patches=pd.concat(patch_frames,ignore_index=True) if patch_frames else pd.DataFrame()
    cs=results.candidate_generation_status.eq("generated"); te=results.temporal_status.eq("evaluated"); integrated=cs & te & pd.to_numeric(results.robust_minus_random_recall,errors="coerce").notna(); lifts=pd.to_numeric(results.loc[integrated,"robust_minus_random_recall"],errors="coerce").to_numpy(float)
    mean,low,high=taxon_bootstrap_mean_ci(lifts,repetitions=int(gate["bootstrap_repetitions"]),seed=int(gate["bootstrap_seed"])); plant=_finite_mean(results.loc[integrated & results.taxon_group.eq("plant"),"robust_minus_random_recall"]); animal=_finite_mean(results.loc[integrated & results.taxon_group.eq("animal"),"robust_minus_random_recall"]); cr=float(cs.mean()); tr=float(te.mean())
    checks={"declared_taxa":len(results)==24,"candidate_generation_success_rate":cr>=float(gate["candidate_generation_success_rate_min"]),"temporal_evaluability_rate":tr>=float(gate["temporal_evaluability_rate_min"]),"mean_lift_positive":bool(np.isfinite(mean) and mean>0),"bootstrap_lower_positive":bool(np.isfinite(low) and low>0),"plant_mean_nonnegative":bool(np.isfinite(plant) and plant>=float(gate["plant_mean_lift_min"])),"animal_mean_nonnegative":bool(np.isfinite(animal) and animal>=float(gate["animal_mean_lift_min"]))}
    summary={"status":"country_framed_robust_integration_development_v2_complete","protocol_fingerprint":EXPECTED_PROTOCOL_FINGERPRINT,"declared_taxa":24,"candidate_generation_success_taxa":int(cs.sum()),"candidate_generation_success_rate":cr,"temporally_evaluable_taxa":int(te.sum()),"temporal_evaluability_rate":tr,"integrated_evaluable_taxa":int(integrated.sum()),"lattice_step_deg":LATTICE_STEP_DEG,"points_per_regional_tile":POINTS_PER_REGIONAL_TILE,"primary_support_fraction":float(VALIDATED_ROBUST_SUPPORT_FRACTION),"primary_radius_km":radius,"random_baseline_repetitions":reps,"mean_robust_minus_random_recall":mean,"taxon_bootstrap_95pct_ci":[low,high],"plant_mean_robust_minus_random_recall":plant,"animal_mean_robust_minus_random_recall":animal,"gate_checks":checks,"development_gate_passed":all(checks.values()),"method_change_from_v1_1":"regional_lattice_only","candidate_generation_preceded_recent_outcome_fetch":True,"retuned_after_outcome_opening":False,"country_representation_changed":False,"country_geometry_provider_changed":False,"robust_core_changed":False,"v1_or_v1_1_taxa_reused":False,"confirmation_v1_taxa_consumed":False,"development_only":True,"global_candidate_generation_validated":False}
    return results,patches,summary


def main(argv: Sequence[str] | None=None):
    p=argparse.ArgumentParser(); p.add_argument("--declarations",type=Path,required=True); p.add_argument("--output",type=Path,required=True); a=p.parse_args(argv); a.output.mkdir(parents=True,exist_ok=True); results,patches,summary=evaluate(pd.read_csv(a.declarations)); results.to_csv(a.output/"taxon_country_results.csv",index=False); patches.to_csv(a.output/"integrated_candidate_patches.csv",index=False); (a.output/"development_summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n",encoding="utf-8"); print(json.dumps(summary,indent=2,ensure_ascii=False)); return 0

if __name__=="__main__": raise SystemExit(main())
