"""Discover model metadata on disk.

Model *loading* (XGBoost booster, joblib IsolationForest) is added together
with the models themselves. TODO(dataset).
"""

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
    schema=json.loads((directory/"feature_schema.json").read_text(encoding="utf-8"))
    classifier=XGBClassifier()
    classifier.load_model(directory/"xgboost_model.json")
    return {"classifier":classifier,
            "imputer":joblib.load(directory/"preprocessing_pipeline.joblib"),
            "baseline":joblib.load(directory/"logistic_baseline.joblib"),
            "isolation_forest":joblib.load(directory/"isolation_forest.joblib"),
            "schema":schema}


def list_model_metadata(models_dir: Path) -> list[ModelMetadata]:
    found: list[ModelMetadata] = []
    for meta_file in sorted(Path(models_dir).glob("*.meta.json")):
        try:
            found.append(ModelMetadata.load(meta_file))
        except (ValueError, TypeError) as exc:
            logger.warning("Skipping unreadable model metadata %s: %s", meta_file.name, exc)
    return found
