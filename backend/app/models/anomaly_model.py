"""Isolation Forest training and raw anomaly scoring.

Higher returned scores indicate more anomalous observations. The training
pipeline separately scales these scores using its training-set quantiles.
"""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import IsolationForest


def train_isolation_forest(features, *, random_state: int = 20240601) -> IsolationForest:
    values = np.asarray(features)
    if values.ndim != 2 or len(values) == 0:
        raise ValueError("Training features must be a nonempty 2-D array")
    model = IsolationForest(
        n_estimators=150,
        max_samples=min(1024, len(values)),
        contamination="auto",
        random_state=random_state,
        n_jobs=4,
    )
    return model.fit(values)


def anomaly_scores(model: IsolationForest, features) -> np.ndarray:
    """Return negative sklearn score_samples, before normalization."""
    values = np.asarray(features)
    if values.ndim != 2 or values.shape[1] != model.n_features_in_:
        raise ValueError("Anomaly features do not match the trained model")
    return -model.score_samples(values)
