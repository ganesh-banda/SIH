"""Supervised transaction classifier and positive-class inference."""

from __future__ import annotations

import numpy as np
from xgboost import XGBClassifier


def train_xgboost(
    features,
    labels,
    validation_features=None,
    validation_labels=None,
    *,
    random_state: int = 20240601,
) -> XGBClassifier:
    """Fit the same XGBoost configuration used by the persisted pipeline."""
    x = np.asarray(features)
    y = np.asarray(labels)
    if x.ndim != 2 or not len(x) or len(x) != len(y):
        raise ValueError("Training features must be a nonempty 2-D array matching labels")
    if set(np.unique(y)) != {0, 1}:
        raise ValueError("Training labels must contain both binary classes (0 and 1)")
    if (validation_features is None) != (validation_labels is None):
        raise ValueError("Validation features and labels must be supplied together")

    model = XGBClassifier(
        n_estimators=180,
        max_depth=4,
        learning_rate=.05,
        subsample=.85,
        colsample_bytree=.85,
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=random_state,
        n_jobs=4,
        scale_pos_weight=float((y == 0).sum() / (y == 1).sum()),
    )
    fit_options = {}
    if validation_features is not None:
        xv, yv = np.asarray(validation_features), np.asarray(validation_labels)
        if xv.ndim != 2 or xv.shape[1] != x.shape[1] or len(xv) != len(yv):
            raise ValueError("Validation features must match training columns and labels")
        fit_options["eval_set"] = [(xv, yv)]
    model.fit(x, y, verbose=False, **fit_options)
    return model


def predict_proba(model: XGBClassifier, features) -> np.ndarray:
    """Return the probability of the illicit (positive) transaction label."""
    values = np.asarray(features)
    if values.ndim != 2 or values.shape[1] != model.n_features_in_:
        raise ValueError("Prediction features do not match the trained model")
    return model.predict_proba(values)[:, 1]
