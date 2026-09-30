"""Load persisted models and optional model metadata without retraining."""

from __future__ import annotations

import logging
import json
from pathlib import Path
import joblib
from xgboost import XGBClassifier

from app.models.base import ModelMetadata

logger = logging.getLogger(__name__)


def load_trained_bundle(models_dir: Path) -> dict:
    """Load persisted artifacts only; API startup never retrains."""
    directory=Path(models_dir)
    required=("feature_schema.json","xgboost_model.json",
              "preprocessing_pipeline.joblib","logistic_baseline.joblib",
              "isolation_forest.joblib")
    missing=[name for name in required if not (directory/name).is_file()]
    if missing:
        raise FileNotFoundError("Missing trained model artifacts: "+", ".join(missing))
    schema=json.loads((directory/"feature_schema.json").read_text(encoding="utf-8"))
    features=schema.get("features")
    if not isinstance(features,list) or not features or not all(isinstance(f,str) for f in features):
        raise ValueError("feature_schema.json must contain a nonempty feature-name list")
    if len(features)!=len(set(features)):
        raise ValueError("feature_schema.json contains duplicate feature names")
    classifier=XGBClassifier()
    classifier.load_model(directory/"xgboost_model.json")
    bundle={"classifier":classifier,
            "imputer":joblib.load(directory/"preprocessing_pipeline.joblib"),
            "baseline":joblib.load(directory/"logistic_baseline.joblib"),
            "isolation_forest":joblib.load(directory/"isolation_forest.joblib"),
            "schema":schema}
    for name in ("classifier","imputer","baseline","isolation_forest"):
        if bundle[name].n_features_in_!=len(features):
            raise ValueError(f"{name} expects {bundle[name].n_features_in_} features; schema lists {len(features)}")
    return bundle


def list_model_metadata(models_dir: Path) -> list[ModelMetadata]:
    found: list[ModelMetadata] = []
    for meta_file in sorted(Path(models_dir).glob("*.meta.json")):
        try:
            found.append(ModelMetadata.load(meta_file))
        except (ValueError, TypeError) as exc:
            logger.warning("Skipping unreadable model metadata %s: %s", meta_file.name, exc)
    return found
