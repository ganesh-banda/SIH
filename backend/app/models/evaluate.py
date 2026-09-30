"""Binary transaction classification metrics for a held-out split."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    confusion_matrix,
    roc_auc_score,
)


def evaluate(labels, probabilities, threshold: float) -> dict:
    """Evaluate probabilities against both labelled classes.

    Threshold selection belongs on validation data; this function only
    measures a supplied threshold and never fits a model.
    """
    y = np.asarray(labels)
    p = np.asarray(probabilities, dtype=float)
    if y.ndim != 1 or p.ndim != 1 or not len(y) or len(y) != len(p):
        raise ValueError("Labels and probabilities must be nonempty equal-length vectors")
    if set(np.unique(y)) != {0, 1}:
        raise ValueError("Evaluation requires both binary classes (0 and 1)")
    if not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("Probabilities must be finite values from 0 to 1")
    if not 0 <= threshold <= 1:
        raise ValueError("Threshold must be between 0 and 1")

    predicted = (p >= threshold).astype(int)
    return {
        "threshold": float(threshold),
        "roc_auc": float(roc_auc_score(y, p)),
        "pr_auc": float(average_precision_score(y, p)),
        "confusion_matrix": confusion_matrix(y, predicted, labels=[0, 1]).tolist(),
        "classification_report": classification_report(
            y, predicted, labels=[0, 1], target_names=["licit", "illicit"],
            output_dict=True, zero_division=0,
        ),
    }
