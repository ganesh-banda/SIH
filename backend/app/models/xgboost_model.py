"""Supervised XGBoost classifier.

TODO(dataset): binary vs multiclass is decided after seeing the labels. If
the dataset has no usable labels, the supervised layer is redesigned.
Requires the ML extras (requirements-ml.txt).
"""


def train_xgboost(*args, **kwargs):
    raise NotImplementedError("Pending dataset labels.")


def predict_proba(*args, **kwargs):
    raise NotImplementedError("Pending trained model.")
