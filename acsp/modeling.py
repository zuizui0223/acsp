"""Reusable model definitions for ACSP ensemble SDMs."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, GradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


DEFAULT_ENSEMBLE_ALGORITHMS = (
    "Logistic regression",
    "Random forest",
    "ExtraTrees",
    "Gradient boosting",
)


def make_classifier(name: str, random_state: int = 42):
    """Create one of the supported, probability-producing SDM classifiers."""
    if name == "Logistic regression":
        return Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", LogisticRegression(max_iter=1000, class_weight="balanced")),
        ])
    if name == "Random forest":
        return Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("model", RandomForestClassifier(
                n_estimators=300, random_state=random_state, class_weight="balanced_subsample"
            )),
        ])
    if name == "ExtraTrees":
        return Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("model", ExtraTreesClassifier(
                n_estimators=300, random_state=random_state, class_weight="balanced"
            )),
        ])
    if name == "Gradient boosting":
        return Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("model", GradientBoostingClassifier(random_state=random_state)),
        ])
    raise ValueError(f"Unsupported algorithm: {name}")


def predict_equal_weight_ensemble(models: Mapping[str, object], table: pd.DataFrame) -> np.ndarray:
    """Return the equal-weight mean probability from fitted classifiers."""
    if not models:
        raise ValueError("At least one fitted model is required.")
    probabilities = [model.predict_proba(table)[:, 1] for model in models.values()]
    return np.mean(np.vstack(probabilities), axis=0)
