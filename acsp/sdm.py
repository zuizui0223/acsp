"""SDM validation and reporting helpers shared by the app and packages."""

from __future__ import annotations

from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd


def choose_spatial_partition(n_occurrences: int, geographic_span_degrees: Optional[float] = None) -> tuple[str, str]:
    """Choose a validation design from occurrence count and geographic spread."""
    n = int(n_occurrences)
    span = float(geographic_span_degrees) if geographic_span_degrees is not None else None
    if n < 15:
        return "jackknife", f"Jackknife was selected because only {n} presence records were available."
    if n < 30 or (span is not None and span < 2.0):
        spread = f" and the minimum extent span was {span:.2f} degrees" if span is not None and span < 2.0 else ""
        return "random holdout", f"Random 75/25 holdout was selected because {n} records{spread} could leave spatial folds empty."
    if n < 50:
        return "random k-fold", f"Random five-fold cross-validation was selected for {n} records, below the spatial-block threshold."
    return "block", f"Four-quadrant spatial block cross-validation was selected for {n} records to test geographic transferability."


def model_performance_table(metrics: pd.DataFrame, model_names: Optional[Iterable[str]] = None) -> pd.DataFrame:
    """Summarize validation AUC and identify the best individual ensemble member."""
    names = list(model_names or [])
    if metrics is None or metrics.empty:
        return pd.DataFrame(columns=["algorithm", "validation_auc", "ensemble_weight", "model_role"])
    work = metrics.copy()
    work["auc"] = pd.to_numeric(work.get("auc"), errors="coerce")
    if not names:
        names = work.get("algorithm", pd.Series(dtype=str)).dropna().astype(str).unique().tolist()
    rows = []
    for name in names:
        subset = work[work["algorithm"].astype(str).eq(str(name))]
        preferred = subset[subset.get("fold", pd.Series(index=subset.index, dtype=object)).astype(str).isin(["mean", "diagnostic"])]
        values = preferred["auc"].dropna() if not preferred.empty else subset["auc"].dropna()
        warning_source = preferred if not preferred.empty else subset
        warnings = [
            value for value in warning_source.get("warning", pd.Series(dtype=str)).dropna().astype(str).unique().tolist()
            if value
        ]
        rows.append({
            "algorithm": str(name),
            "validation_auc": float(values.mean()) if not values.empty else np.nan,
            "validation_warning": "; ".join(warnings),
        })
    out = pd.DataFrame(rows)
    finite = out["validation_auc"].replace([np.inf, -np.inf], np.nan)
    best = out.loc[finite.idxmax(), "algorithm"] if finite.notna().any() else "not available"
    out["ensemble_weight"] = round(1.0 / max(1, len(out)), 4)
    out["model_role"] = out["algorithm"].apply(lambda name: "best individual model; ensemble member" if name == best else "ensemble member")
    return out


def sdm_method_record(
    *,
    n_source_records: int,
    n_qc_excluded: int,
    n_presence_used: int,
    n_background: int,
    partition_method: str,
    partition_reason: str,
    variables: Iterable[str],
    performance: pd.DataFrame,
    environment_source: str,
    prediction_extent: str,
) -> dict[str, Any]:
    """Create a manuscript-ready, machine-readable SDM method record."""
    perf = performance if performance is not None else pd.DataFrame()
    best_rows = perf[perf.get("model_role", pd.Series(index=perf.index, dtype=str)).astype(str).str.startswith("best individual")]
    best_model = str(best_rows.iloc[0]["algorithm"]) if not best_rows.empty else "not available"
    best_auc = float(best_rows.iloc[0]["validation_auc"]) if not best_rows.empty and pd.notna(best_rows.iloc[0]["validation_auc"]) else np.nan
    algorithms = perf.get("algorithm", pd.Series(dtype=str)).astype(str).tolist()
    validation_caution = "; ".join(
        dict.fromkeys(value for value in perf.get("validation_warning", pd.Series(dtype=str)).dropna().astype(str) if value)
    )
    variables_list = list(variables)
    method_text = (
        f"The SDM used {n_presence_used} presence records after excluding {n_qc_excluded} spatial-QC records "
        f"from {n_source_records} source records, with {n_background} background points. "
        f"Validation used {partition_method} ({partition_reason}). "
        f"Predictors were {', '.join(variables_list)} from {environment_source}. "
        f"Final suitability was the equal-weight mean of {', '.join(algorithms)}; "
        f"the best individual model was {best_model} (validation AUC={best_auc:.3f})."
        if np.isfinite(best_auc) else
        f"The SDM used {n_presence_used} presence records after spatial QC and {partition_method} validation. "
        f"Final suitability was the equal-weight mean of {', '.join(algorithms)}."
    )
    if validation_caution:
        method_text += f" Validation caution: {validation_caution}."
    return {
        "source_occurrence_records": int(n_source_records),
        "qc_excluded_records": int(n_qc_excluded),
        "presence_records_used": int(n_presence_used),
        "background_points": int(n_background),
        "partition_method": partition_method,
        "partition_reason": partition_reason,
        "environment_variables": ", ".join(variables_list),
        "environment_source": environment_source,
        "prediction_extent": prediction_extent,
        "ensemble_method": "equal-weight mean classifier probability used as relative suitability; not calibrated occupancy probability",
        "ensemble_algorithms": ", ".join(algorithms),
        "best_individual_model": best_model,
        "best_individual_auc": round(best_auc, 3) if np.isfinite(best_auc) else np.nan,
        "validation_caution": validation_caution,
        "methods_text": method_text,
    }
