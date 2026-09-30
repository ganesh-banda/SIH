"""Isolation Forest anomaly model.

The raw sklearn ``score_samples`` output is kept as-is and is NOT presented
as a 0-100 risk number. Any transformation is decided during calibration.
TODO(dataset).
"""


def train_isolation_forest(*args, **kwargs):
    raise NotImplementedError("Pending dataset features.")


def anomaly_scores(*args, **kwargs):
    raise NotImplementedError("Pending trained model.")
