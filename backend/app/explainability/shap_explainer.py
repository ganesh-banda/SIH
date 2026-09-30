"""SHAP explanations for the XGBoost model (TreeExplainer).

SHAP values explain contributions to the MODEL OUTPUT (log-odds by default
for XGBoost), not percentages of the final risk score, and are presented
that way. TODO(dataset): pending trained model. Needs requirements-ml.txt.
"""


def explain_rows(*args, **kwargs):
    raise NotImplementedError("Pending trained XGBoost model.")
